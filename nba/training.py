"""Chronological evaluation of baseline corrections using real completed game logs."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from .model import STATS, project, instant


def reconstruct(logs, start, end):
    """Retrospective participant-only baseline; never presented as saved predictions."""
    by_player=defaultdict(list)
    for row in logs:
        if row['date'][:10]<=end:by_player[str(row['player_id'])].append(row)
    output=[]
    for player_id, history in by_player.items():
        past=[]
        for game in sorted(history,key=lambda r:r['date']):
            day=game['date'][:10]
            if start<=day<=end and game['min']>0:
                cutoff=day+'T00:00:00+00:00'
                # Only earlier dates enter features; same-day and target outcomes excluded.
                prior=[g for g in past if g['date'][:10]<day]
                player={'player_id':player_id,'player':game.get('player',player_id),'team':game['team'],
                        'game_id':str(game['game_id']),'game_time':cutoff,'season_type':'Regular Season'}
                for stat in STATS.values():
                    prediction=project(player,prior,stat,instant(cutoff))
                    if prediction['projection'] is None:continue
                    output.append({**prediction,'actual':game[stat], 'projection_error':prediction['projection']-game[stat],
                        'result_known_at':day+'T23:59:59+00:00','recommendation':'No Play','recommendation_result':None,
                        'line':None,'source':'Retrospective baseline; actual participants only; no historical odds/injuries'})
            past.append(game)
    return output


def validate_corrections(rows, cutoff):
    # Deduplicate repeated snapshots and sportsbook offers before training.
    unique=list({(r['game_id'],r['player_id'],r['stat']):r for r in rows
        if r.get('result_known_at') and instant(r['result_known_at'])<instant(cutoff)}.values())
    dates=sorted({r['game_time'][:10] for r in unique})
    if len(dates)<10:raise ValueError('At least 10 completed game dates are needed for chronological training and validation.')
    split=dates[max(1,int(len(dates)*.7))]
    reports=[];corrections={}
    for stat in STATS.values():
        train=[r for r in unique if r['stat']==stat and r['game_time'][:10]<split]
        holdout=[r for r in unique if r['stat']==stat and r['game_time'][:10]>=split]
        if len(train)<50 or len(holdout)<20:continue
        correction=sum(r['projection_error'] for r in train)/(len(train)+20)
        before=sum(abs(r['projection_error']) for r in holdout)/len(holdout)
        after=sum(abs(max(0,r['projection']-correction)-r['actual']) for r in holdout)/len(holdout)
        # Keep only corrections that improve untouched later-date MAE.
        accepted=after<before
        if accepted:corrections[stat]=correction
        reports.append({'Stat':stat,'Training samples':len(train),'Validation samples':len(holdout),
            'Baseline MAE':before,'Corrected MAE':after,'Subtract':correction,'Accepted':accepted})
    if not reports:raise ValueError('Not enough observations: need 50 training and 20 later validation samples per stat.')
    return {'version':'stat-bias-2','trained_before':cutoff,'validation_start':split,
            'corrections':corrections,'validation':reports,'status':'candidate',
            'scope':'Regular Season only; stat-level bias correction; confidence unchanged'}
