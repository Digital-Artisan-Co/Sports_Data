"""Transparent baseline models. Inputs are pregame observations, never outcomes."""
import math
import statistics as st
from datetime import datetime, timezone

STATS = {'Points':'pts', 'Rebounds':'reb', 'Assists':'ast', '3PM':'fg3m', 'Steals':'stl', 'Blocks':'blk'}
THRESHOLDS = {'pts':[25,30,35,40], 'reb':[10,12,15,18], 'ast':[8,10,12,15], 'fg3m':[4,5,6,7], 'stl':[2,3,4], 'blk':[2,3,4,5]}

def instant(value):
    d = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)

def clamp(x, lo=0, hi=100): return max(lo,min(hi,x))
def avg(xs): return st.mean(xs) if xs else None

def recommendation(r):
    if r.get('line') is None: return 'No Play'
    if r.get('projection') is None or r.get('confidence',0)<60: return 'No Play'
    if r.get('injury_status') not in ('Available','Probable'): return 'No Play'
    if not r.get('line_fresh') or r.get('role_security',0)<60: return 'No Play'
    edge=r['projection']-r['line']; stat=r['stat']; opp=r.get('opportunity'); matchup=r.get('matchup')
    if opp is None or matchup is None: return 'Pass'
    take, lean = (1.5,.75) if stat in ('pts','reb','ast') else ((.5,.25) if stat=='fg3m' else (.35,.2))
    if stat in ('stl','blk') and (r['role_security']<80 or matchup<65 or not r.get('defensive_activity')): return 'Pass'
    if stat=='fg3m' and not r.get('three_volume_support'): return 'Pass'
    if edge>=take and r['confidence']>=65 and r['role_security']>=65 and opp>=60: return 'Take Over'
    if edge<=-take and r['confidence']>=65 and (matchup<50 or r['role_security']<70): return 'Take Under'
    if edge>=lean: return 'Lean Over'
    if edge<=-lean: return 'Lean Under'
    return 'Pass'

def project(player, logs, stat, cutoff, context=None):
    context=context or {}; cutoff=instant(cutoff)
    eligible=[g for g in logs if str(g['player_id'])==str(player['player_id']) and instant(g['date'])<cutoff and instant(g.get('known_at',g['date']))<cutoff and g.get('min',0)>0]
    eligible=sorted(eligible,key=lambda g:g['date'],reverse=True)
    # Never combine seasons if a season identifier is supplied.
    if eligible and eligible[0].get('season') is not None: eligible=[g for g in eligible if g.get('season')==eligible[0]['season']]
    base={**player,'stat':stat,'projection':None,'confidence':None,'missing':[], 'model_version':'baseline-1','projected_minutes':None,'role_security':None,'opportunity':None,'matchup':None,'ceiling':None,'recent_form':None,'injury_boost':None,'injury_status':context.get('injury_status','Unknown')}
    if player.get('season_type')=='Preseason' and context.get('projected_minutes') is None:
        prior_minutes=sum(g['min'] for g in eligible)
        return {**base,'regular_season_reference_average':avg([g[stat] for g in eligible]),
            'reference_per_minute_rate':sum(g[stat] for g in eligible)/prior_minutes if prior_minutes else None,
            'missing':['Preseason minutes unavailable; regular-season workload is not substituted']}
    if len(eligible)<5: return {**base,'missing':['At least 5 prior player game logs required']}
    recent=eligible[:10]; minutes=[g['min'] for g in recent]; pm=avg(minutes[:5])*.6+avg(minutes)*.4
    if context.get('projected_minutes') is not None: pm=context['projected_minutes']
    pm=clamp(pm,0,48); total=sum(g['min'] for g in eligible); rate=sum(g[stat] for g in eligible)/total
    recent_rate=sum(g[stat] for g in recent)/sum(minutes)
    blended=.75*rate+.25*recent_rate
    missing=[]
    def factor(name):
        if context.get(name) is None: missing.append(name); return 1.0
        return clamp(float(context[name]),.65,1.35)
    pace=factor('pace_adjustment'); matchup_factor=factor(f'{stat}_matchup_adjustment')
    if stat=='pts':
        # Volume and FT changes receive distinct adjustments; efficiency remains season-shrunk.
        prediction=pm*blended*factor('usage_adjustment')*factor('shot_volume_adjustment')*factor('free_throw_adjustment')*factor('injury_adjustment')*pace*matchup_factor
    elif stat=='reb': prediction=pm*blended*factor('rebound_chance_adjustment')*factor('opponent_misses_adjustment')*factor('frontcourt_role_adjustment')*pace*matchup_factor
    elif stat=='ast':
        potential=context.get('potential_assists_per_minute'); conversion=context.get('assist_conversion')
        if potential is None or conversion is None: missing.append('potential assists / teammate conversion'); ar=blended
        else: ar=potential*conversion
        prediction=pm*ar*factor('ball_handling_adjustment')*factor('teammate_shooting_adjustment')*pace*matchup_factor
    elif stat=='fg3m':
        if any(g.get('fg3a') is None for g in eligible): return {**base,'missing':['3PA game logs required for 3PM projection']}
        attempts=sum(g.get('fg3a',0) for g in eligible); makes=sum(g['fg3m'] for g in eligible)
        recent_attempts=sum(g.get('fg3a',0) for g in recent)/sum(minutes)
        expected_pct=(makes+35)/(attempts+100) # explicit weak 35% prior, not a player observation
        prediction=pm*(.75*attempts/total+.25*recent_attempts)*expected_pct*factor('shot_quality_adjustment')*pace*matchup_factor
    elif stat=='stl': prediction=pm*blended*factor('opponent_turnover_adjustment')*factor('ball_handler_adjustment')*pace*matchup_factor
    else: prediction=pm*blended*factor('rim_contest_adjustment')*factor('opponent_rim_adjustment')*factor('rim_role_adjustment')*factor('foul_adjustment')*matchup_factor
    security=clamp(100-st.pstdev(minutes)*4-abs(avg(minutes[:3])-avg(minutes))*2)
    values=[g[stat] for g in recent]; volatility=st.pstdev(values)/max(avg(values),.3)
    confidence=clamp(45+min(len(eligible),30)*.8+security*.25-volatility*12-len(missing)*3)
    status=context.get('injury_status','Unknown')
    if status not in ('Available','Probable'): confidence-=15
    if stat in ('stl','blk'): confidence=min(confidence,69)
    if player.get('season_type')=='Preseason': confidence=min(confidence,49)
    if status in ('Out','Doubtful'): prediction=0; confidence=0
    opportunity=context.get(f'{stat}_opportunity_score'); matchup=context.get(f'{stat}_matchup_score')
    # Ceiling uses observed threshold frequencies, rather than arbitrary star labels.
    hits={str(t):sum(g[stat]>=t for g in eligible)/len(eligible) for t in THRESHOLDS[stat]}
    ceiling=clamp(40*max(hits.values())+25*min(max(g[stat] for g in eligible)/THRESHOLDS[stat][-1],1)+.2*security+.15*(opportunity if opportunity is not None else 0))
    if opportunity is None: missing.append(f'{stat}_opportunity_score')
    if matchup is None: missing.append(f'{stat}_matchup_score')
    result={**base,'projection':round(max(0,prediction),2),'projected_minutes':round(pm,1),'per_minute_rate':rate,'confidence':round(clamp(confidence)), 'role_security':round(security),'opportunity':opportunity,'matchup':matchup,'ceiling':round(ceiling),'recent_form':round(clamp(50+50*(recent_rate/max(rate,.01)-1))), 'season_high':max(g[stat] for g in eligible),'last10_high':max(values),'threshold_hit_rates':hits,'injury_status':status,'missing':missing,'sample_size':len(eligible),'recent_stats':recent,'season_stats':{'games':len(eligible),'rate':rate},'context':context,'pace':context.get('pace_adjustment'),'injury_boost':context.get('injury_adjustment'),'blowout_risk':context.get('blowout_risk'),'rest_context':context.get('rest_context')}
    return result

def rank_slate(rows):
    for stat in STATS.values():
        group=[r for r in rows if r['stat']==stat and r['projection'] is not None]
        for r in group:
            percentile=100*sum(x['projection']<r['projection'] for x in group)/max(len(group)-1,1)
            r['projection_percentile']=percentile
            r['top3_spike']=round(.35*r['opportunity']+.30*r['ceiling']+.20*percentile+.10*r['confidence']+.05*r['matchup'],1) if r['opportunity'] is not None and r['matchup'] is not None else None
            r['hidden_ceiling']=r['ceiling']>=75 and (r['opportunity'] or 0)>=50 and percentile<80
            r['explanation']='Observed ceiling and opportunity exceed median projection tier.' if r['hidden_ceiling'] else ''
    return rows
