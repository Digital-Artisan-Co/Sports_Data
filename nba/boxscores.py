"""Free final ESPN box scores, matched to NBA IDs by unique normalized full names."""
import unicodedata
from collections import defaultdict
from .providers import ProviderError


def normalize_name(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value).casefold() if c.isalnum())


def final_boxscores(provider, game, known_at):
    from nba_api.stats.static.players import get_players
    if not game.get('completed') or not str(game['game_id']).startswith('espn:'):return []
    payload=provider.get('ESPN box scores','https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary',{'event':str(game['game_id']).split(':',1)[1]})
    competitions=payload.get('header',{}).get('competitions',[])
    if not competitions or not competitions[0].get('status',{}).get('type',{}).get('completed'):return []
    names=defaultdict(set)
    for player in get_players():names[normalize_name(player['full_name'])].add(str(player['id']))
    competitors={str(c['team']['id']):c.get('homeAway') for c in competitions[0]['competitors']}
    rows=[]
    for team in payload.get('boxscore',{}).get('players',[]):
        side=competitors.get(str(team['team']['id']))
        if side not in ('home','away'):continue
        for group in team.get('statistics',[]):
            labels=group.get('labels',[])
            for player in group.get('athletes',[]):
                if player.get('didNotPlay'):continue
                name=player['athlete']['displayName'];matches=names[normalize_name(name)]
                if len(matches)!=1:continue
                values=dict(zip(labels,player.get('stats',[])))
                try:
                    minutes=str(values['MIN']).split(':')
                    minutes=float(minutes[0])+(float(minutes[1])/60 if len(minutes)>1 else 0)
                    stats={s:float(values[label]) for s,label in [('pts','PTS'),('reb','REB'),('ast','AST'),('stl','STL'),('blk','BLK')]}
                    stats['fg3m']=float(values['3PT'].split('-')[0])
                except (KeyError,ValueError):continue
                rows.append({'player_id':next(iter(matches)),'player':name,'game_id':game['game_id'],
                    'team':game[side],'opponent':game['away' if side=='home' else 'home'],'game_time':game['game_time'],
                    'date':game['game_time'][:10],'min':minutes,**stats,'status':'Final','known_at':known_at,'source':'ESPN final box score'})
    if not rows:raise ProviderError('Final ESPN box score has no uniquely matched NBA player statistics yet.')
    return rows
