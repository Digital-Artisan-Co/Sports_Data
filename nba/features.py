"""Stat-specific observable feature aggregation.

Each input must be supplied as a pregame percentile in the relevant NBA population,
not as an unscaled raw quantity. Missing inputs are never assigned league averages.
"""
from .model import clamp
OPPORTUNITY={
 'pts':{'usage':.20,'fga':.25,'fta':.15,'touches':.10,'drives':.10,'recent_shot_volume':.20},
 'reb':{'rebound_chances':.30,'rebound_share':.20,'dreb_rate':.15,'oreb_rate':.10,'frontcourt_minutes':.10,'opponent_misses':.15},
 'ast':{'potential_assists':.30,'passes':.10,'possession_time':.15,'touches':.10,'assist_rate':.15,'ball_handling':.20},
 'fg3m':{'three_attempts':.40,'catch_shoot_attempts':.15,'pullup_attempts':.10,'three_attempt_rate':.15,'minutes':.20},
 'stl':{'steal_rate':.25,'deflections':.30,'loose_balls':.10,'opponent_turnovers':.20,'minutes':.15},
 'blk':{'block_rate':.25,'rim_contests':.30,'opponent_rim_attempts':.20,'center_minutes':.15,'foul_safety':.10}}
MATCHUP={
 'pts':{'opponent_position_points':.25,'opponent_defensive_weakness':.25,'opponent_efg_allowed':.20,'defender_weakness':.15,'pace':.15},
 'reb':{'opponent_position_rebounds':.25,'opponent_misses':.30,'opponent_rebound_weakness':.20,'shot_profile':.10,'pace':.15},
 'ast':{'opponent_assists_allowed':.30,'help_defense_opportunity':.20,'turnover_pressure_safety':.20,'teammate_shot_quality':.15,'pace':.15},
 'fg3m':{'opponent_three_attempts_allowed':.30,'opponent_threes_allowed':.25,'opponent_three_pct_allowed':.15,'corner_opportunity':.15,'closeout_weakness':.15},
 'stl':{'opponent_turnovers':.30,'opponent_live_ball_turnovers':.30,'matchup_handler_turnovers':.25,'pace':.15},
 'blk':{'opponent_rim_attempts':.30,'opponent_paint_attempts':.20,'opponent_blocked_rate':.25,'rim_role':.15,'opponent_drives':.10}}

def weighted(features,weights):
    present={k:v for k,v in features.items() if k in weights and isinstance(v,(int,float)) and 0<=v<=100}
    coverage=sum(weights[k] for k in present)
    if coverage<.7:return None,coverage
    return round(sum(present[k]*weights[k] for k in present)/coverage,1),coverage

def enrich(context):
    result=dict(context); coverage={}
    for stat in OPPORTUNITY:
        for label,weights in [('opportunity',OPPORTUNITY[stat]),('matchup',MATCHUP[stat])]:
            values=context.get('feature_percentiles',{}).get(stat,{}).get(label,{})
            score,cov=weighted(values,weights)
            if result.get(f'{stat}_{label}_score') is None:result[f'{stat}_{label}_score']=score
            coverage[f'{stat}_{label}']=cov
    result['feature_coverage']=coverage
    return result

def classify(score,kind):
    if score is None:return 'N/A'
    labels={
      'confidence':['Elite','High','Medium-High','Medium','Low','Very Low'],
      'role':['Locked role','Very stable','Stable','Usable','Volatile','High risk'],
      'opportunity':['Elite opportunity','Very strong','Strong','Above average','Neutral','Limited','Poor'],
      'matchup':['Elite matchup','Very strong','Strong','Favorable','Neutral','Poor','Major fade'],
      'ceiling':['Elite hidden ceiling','Very strong ceiling','Strong ceiling','Sleeper ceiling','Neutral','Limited ceiling','Low ceiling'],
      'top3':['Elite Top-3 Candidate','Very Strong Top-3 Candidate','Strong Top-3 Candidate','Viable Top-3 Candidate','Neutral','Long Shot','Very Low']}
    values=labels[kind]; thresholds=[90,80,70,60,50] if len(values)==6 else [90,80,70,60,50,40]
    for threshold,label in zip(thresholds,values):
        if score>=threshold:return label
    return values[-1]
