"""Join NBA-native IDs using current roster observations, not last-season teams."""
from .model import instant

def build_nba_slate(games, roster, logs):
    if not logs: raise ValueError('Import NBA.com game logs first.')
    players=[]
    seen=set()
    for game in games:
        instant(game['game_time'])
        for p in roster:
            team=str(p['team_id'])
            if team not in (game['home_id'],game['away_id']):continue
            key=(game['game_id'],p['player_id'])
            if key in seen:continue
            seen.add(key)
            players.append({**p,'game_id':game['game_id'],'game_time':game['game_time'],
                'season_type':game.get('season_type','Unknown'),'game_status':game.get('game_status','Unknown'),'opponent':game['away'] if team==game['home_id'] else game['home']})
    return {'games':games,'players':players,'logs':logs,'lines':[],'contexts':{},'source':'NBA.com game logs and current roster; schedule: '+', '.join(sorted({g.get('source','NBA.com') for g in games}))}


def normalize_bdl_schedule(records, roster, date, timezone='UTC'):
    """Match exact team abbreviations; retain provider namespace on game IDs."""
    teams={}
    for player in roster:
        teams.setdefault(player['team'].upper(),set()).add(str(player['team_id']))
    games=[]
    for record in records:
        tip=record.get('datetime')
        if not tip:raise ValueError('Schedule has a game without a confirmed tipoff timestamp; no time was invented.')
        timestamp=instant(tip)
        from zoneinfo import ZoneInfo
        if timestamp.astimezone(ZoneInfo(timezone)).date().isoformat()!=date:continue
        home=record['home_team']['abbreviation'].upper()
        away=record['visitor_team']['abbreviation'].upper()
        if any(len(teams.get(team,set()))!=1 for team in (home,away)):
            raise ValueError(f'Cannot uniquely match schedule teams {home}/{away} to current NBA roster. No guessed match was used.')
        games.append({'game_id':'bdl:'+str(record['id']),'game_time':timestamp.isoformat(),
            'home_id':next(iter(teams[home])),'away_id':next(iter(teams[away])),
            'home':home,'away':away,'source':'BallDontLie schedule; NBA roster team mapping'})
    return games


def add_preseason_context(bundle,preseason_logs,known_at):
    """Estimate minutes only from prior preseason games; never regular-season minutes."""
    from .schedule import slate_day
    from statistics import mean
    for p in bundle['players']:
        if p.get('season_type')!='Preseason':continue
        prior=[g for g in preseason_logs if str(g['player_id'])==str(p['player_id'])
            and g.get('season_type')=='Pre Season' and g['date'][:10]<slate_day(known_at) and g['min']>0]
        prior.sort(key=lambda g:g['date'],reverse=True)
        context={'known_at':known_at,'preseason':True,'minutes_basis':'N/A — no prior preseason minutes', 'preseason_minutes_games':len(prior[:3])}
        if prior:
            context['projected_minutes']=round(mean(g['min'] for g in prior[:3]),1)
            context['minutes_basis']='Last '+str(len(prior[:3]))+' preseason games; uncertain rotation'
        bundle['contexts'][str(p['player_id'])]=context
    return bundle
