import json
from collections import defaultdict
from datetime import datetime, timezone
from .model import STATS, instant, project, rank_slate, recommendation
from .features import enrich, classify

def validate_bundle(bundle):
    for key in ('players','logs'):
        if not isinstance(bundle.get(key),list): raise ValueError(f'{key} must be an array')
    for p in bundle['players']:
        for k in ('player_id','player','team','opponent','game_id','game_time'):
            if not p.get(k): raise ValueError(f'Player missing {k}')
        instant(p['game_time'])
    for g in bundle['logs']:
        for k in ('player_id','date','min',*STATS.values()):
            if k not in g: raise ValueError(f'Game log missing {k}')
        instant(g['date'])
        for k in ('min',*STATS.values()):
            if not isinstance(g[k],(float,int)) or g[k]<0: raise ValueError(f'Invalid {k}')
    return bundle

def run(bundle,cutoff,historical=False,calibration=None):
    validate_bundle(bundle); cutoff=instant(cutoff); rows=[]
    logs_by_player=defaultdict(list)
    for log in bundle['logs']:logs_by_player[str(log['player_id'])].append(log)
    for player in bundle['players']:
        if instant(player['game_time'])<=cutoff: continue
        # Context must explicitly have a pre-cutoff observation timestamp.
        context=bundle.get('contexts',{}).get(str(player['player_id']),{})
        if not context.get('known_at') or instant(context['known_at'])>cutoff: context={}
        context=enrich(context)
        for stat in STATS.values():
            row=project(player,logs_by_player[str(player['player_id'])],stat,cutoff,context)
            if calibration and row['projection'] is not None and player.get('season_type')=='Regular Season' and instant(calibration['trained_before'])<cutoff:
                correction=calibration.get('corrections',{}).get(stat)
                if correction is not None:
                    row['baseline_projection']=row['projection']
                    row['projection']=round(max(0,row['projection']-correction),2)
                    row['model_version']='baseline-1+'+calibration['id']
            lines=[l for l in bundle.get('lines',[]) if str(l.get('player_id'))==str(player['player_id']) and str(l.get('game_id'))==str(player['game_id']) and l.get('stat')==stat and l.get('timestamp') and instant(l['timestamp'])<=cutoff]
            for line in lines or [{}]:
                r={**row,'line':line.get('line'),'sportsbook':line.get('sportsbook'),'over_odds':line.get('over_odds'),'under_odds':line.get('under_odds'),'line_timestamp':line.get('timestamp'),'opening_line':line.get('opening_line'),'line_movement':line['line']-line['opening_line'] if line.get('opening_line') is not None else None,'line_fresh':bool(line) and (cutoff-instant(line['timestamp'])).total_seconds()<=21600,'data_source':bundle.get('source','Imported snapshot'),'feature_cutoff':cutoff.isoformat(),'historical_availability':'N/A — unavailable historically' if historical and (not context or not line) else None,'defensive_activity':context.get('defensive_activity'),'three_volume_support':context.get('three_volume_support')}
                r['edge']=r['projection']-r['line'] if r['projection'] is not None and r['line'] is not None else None
                r['recommendation']=recommendation(r); rows.append(r)
    # Rankings use unique players, not bookmaker rows.
    unique={(r['player_id'],r['stat']):dict(r) for r in rows}; rank_slate(list(unique.values()))
    for r in rows:
        for key in ('top3_spike','hidden_ceiling','projection_percentile','explanation'):r[key]=unique[(r['player_id'],r['stat'])].get(key)
    for r in rows:
        for key,kind in [('confidence','confidence'),('role_security','role'),('opportunity','opportunity'),('matchup','matchup'),('ceiling','ceiling'),('top3_spike','top3')]:
            r[key+'_class']=classify(r.get(key),kind)
    return rows
