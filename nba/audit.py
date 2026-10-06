import math
from collections import defaultdict
from .model import instant

def audit(snapshots,results):
    output=[]
    # Most recent saved pregame version per offer; reruns must not multiply accuracy.
    latest={}
    for snap in sorted(snapshots,key=lambda s:s['created']):
        for r in snap['rows']:
            if instant(snap['created'])>=instant(r['game_time']):continue
            latest[(str(r['game_id']),str(r['player_id']),r['stat'],r.get('sportsbook'))]=(snap,r)
    for snap,r in latest.values():
        actual=results.get((str(r['game_id']),str(r['player_id'])))
        if not actual or r.get('projection') is None: continue
        value=actual[r['stat']]; error=r['projection']-value; line=r.get('line')
        ou=None if line is None else ('Over' if value>line else 'Under' if value<line else 'Push')
        rec=r.get('recommendation','No Play'); side='Over' if 'Over' in rec else 'Under' if 'Under' in rec else None
        driver=actual.get('observed_driver')
        if not driver:
            if abs(actual['min']-r['projected_minutes'])>=6: driver='minutes miss'
            elif r['stat'] in ('stl','blk'): driver='defensive stat variance'
            else: driver='model over-projection' if error>0 else 'model under-projection' if error<0 else 'on target'
        output.append({**r,'snapshot_id':snap['id'],'snapshot_time':snap['created'],'actual':value,'result_known_at':actual.get('known_at'),'actual_minutes':actual['min'],'projection_error':error,'ou_result':ou,'recommendation_result':None if side is None or ou is None else 'Push' if ou=='Push' else 'Win' if ou==side else 'Loss','observed_driver':driver,'driver_evidence':'reported' if actual.get('observed_driver') else 'heuristic — cause unconfirmed'})
    return output

def metrics(rows):
    if not rows:return {}
    errors=[r['projection_error'] for r in rows]; bets=[r for r in rows if r['recommendation_result'] in ('Win','Loss')]
    out={'count':len(rows),'MAE':sum(abs(e) for e in errors)/len(errors),'RMSE':math.sqrt(sum(e*e for e in errors)/len(errors)),'bias':sum(errors)/len(errors),'recommendation_accuracy':sum(r['recommendation_result']=='Win' for r in bets)/len(bets) if bets else None,'major_miss_rate':sum(abs(r['projection_error'])>=max(2,.5*r['projection']) for r in rows)/len(rows)}
    for side in ['Over','Under']:
        selected=[r for r in bets if side in r['recommendation']]
        out[side.lower()+'_hit_rate']=sum(r['recommendation_result']=='Win' for r in selected)/len(selected) if selected else None
    passes=[r for r in rows if r['recommendation'] in ('Pass','No Play')]
    out['pass_count']=len(passes)
    return out

def capture(rows):
    grouped=defaultdict(list)
    from .schedule import slate_day
    for r in rows: grouped[(slate_day(r['game_time']),r['stat'])].append(r)
    results=[]
    for (snapshot,stat),group in grouped.items():
        # One row per player per slate: books must not multiply leaders.
        unique=list({str(r['player_id']):r for r in group}.values())
        methods={'Projected Stat':lambda r:r['projection'],'Opportunity':lambda r:r.get('opportunity'),'Ceiling':lambda r:r.get('ceiling'),'Top-3 Spike':lambda r:r.get('top3_spike'),'Prop line':lambda r:r.get('line'),'Projection × Opportunity':lambda r:r['projection']*r['opportunity'] if r.get('opportunity') is not None else None,'Opportunity × Ceiling':lambda r:r['opportunity']*r['ceiling'] if r.get('opportunity') is not None and r.get('ceiling') is not None else None}
        for k in (3,5):
            if len(unique)<k: continue
            cutoff=sorted((r['actual'] for r in unique),reverse=True)[k-1]
            actual={r['player_id'] for r in unique if r['actual']>=cutoff}
            for method,key in methods.items():
                if any(key(r) is None for r in unique): continue
                predicted=sorted(unique,key=key,reverse=True)[:k]
                results.append({'snapshot':snapshot,'stat':stat,'ranking':method,'top_k':k,'capture_rate':sum(r['player_id'] in actual for r in predicted)/k,'coverage':'audited snapshot players only; ties included'})
    return results

def train_bias(rows,cutoff):
    eligible=[r for r in rows if r.get('result_known_at') and instant(r['result_known_at'])<instant(cutoff)]
    eligible=list({(r['game_id'],r['player_id'],r['stat']):r for r in eligible}.values())
    buckets=defaultdict(list)
    for r in eligible:buckets[(r['player_id'],r['stat'])].append(r['projection_error'])
    return {'version':'bias-1','trained_before':cutoff,'corrections':[{'player_id':p,'stat':s,'n':len(e),'subtract':sum(e)/(len(e)+20)} for (p,s),e in buckets.items() if len(e)>=5],'status':'candidate; held-out validation required before activation'}
