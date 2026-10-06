"""Date-scoped ingestion. Never reuse a previous date's slate or current context historically."""
import os
from collections import defaultdict
from datetime import date as Date,datetime,timezone
from .model import instant
from .schedule import slate_day
from .errors import ProviderError
from .slate import build_nba_slate,add_preseason_context


def team_directory():
    from nba_api.stats.static.teams import get_teams
    return [{'team_id':str(t['id']),'team':t['abbreviation'],'team_name':t['full_name']} for t in get_teams()]


def memo_call(provider,method,*args,now):
    cache=getattr(provider,'_date_import_cache',None)
    if cache is None:cache={};provider._date_import_cache=cache
    key=(method,*args)
    entry=cache.get(key)
    if entry and 0<=(now-entry['at']).total_seconds()<600:
        if 'error' in entry:raise ProviderError(entry['error'])
        return entry['value']
    try:value=getattr(provider,method)(*args)
    except ProviderError as e:
        cache[key]={'at':now,'error':str(e)};raise
    cache[key]={'at':now,'value':value}
    return value


def attach_lines(bundle,raw):
    """Only exact names, matching team pair, and matching tipoff can join feeds."""
    def norm(s):return ' '.join(str(s or '').casefold().split())
    matched=[]
    for line in raw:
        candidates=[p for p in bundle['players'] if norm(p['player'])==norm(line.get('player'))
            and norm(p.get('team_name')) in (norm(line.get('home_team')),norm(line.get('away_team')))
            and line.get('game_time') and abs((instant(p['game_time'])-instant(line['game_time'])).total_seconds())<=300]
        if len(candidates)!=1:continue
        player=candidates[0]
        opponent_names={norm(p.get('team_name')) for p in bundle['players'] if p['game_id']==player['game_id'] and p['team']==player['opponent']}
        other=norm(line['away_team']) if norm(player.get('team_name'))==norm(line['home_team']) else norm(line['home_team'])
        if other not in opponent_names:continue
        matched.append({**line,'player_id':player['player_id'],'game_id':player['game_id']})
    bundle['lines']=matched
    return len(raw)-len(matched)


def attach_injuries(bundle,raw,known_at,source='BallDontLie'):
    count=0
    for injury in raw:
        p=injury.get('player') or {}
        if not isinstance(p,dict):continue
        name=(p.get('first_name','')+' '+p.get('last_name','')).strip().casefold()
        candidates={x['player_id']:x for x in bundle['players'] if x['player'].casefold()==name}
        if len(candidates)!=1:continue
        player=next(iter(candidates.values()))
        status=str(injury.get('status','Unknown')).title()
        if status not in ('Available','Probable','Questionable','Doubtful','Out'):status='Unknown'
        context=bundle['contexts'].setdefault(str(player['player_id']),{})
        if context.get('injury_status') not in (None,'Unknown'):continue
        context.update(known_at=known_at,injury_status=status,injury_source=source)
        count+=1
    return count


def completed_results(games,logs,date,known_at):
    grouped=defaultdict(list)
    for row in logs:
        if row['date'][:10]==date:grouped[str(row['game_id'])].append(row)
    result=[]
    for game in games:
        if not game.get('completed'):continue
        candidates=[group for group in grouped.values() if {r['team'] for r in group}=={game['home'],game['away']}]
        if len(candidates)!=1:continue
        for row in candidates[0]:
            result.append({**row,'game_id':game['game_id'],'game_time':game['game_time'],'status':'Final','known_at':known_at,
                'opponent':game['away'] if row['team']==game['home'] else game['home']})
    return result


def load_date(provider,date,now=None,snapshots=(),progress=None):
    Date.fromisoformat(date)
    now=instant(now or datetime.now(timezone.utc).isoformat());stamp=now.isoformat()
    historical=date<slate_day(stamp)
    result={'date':date,'loaded_at':stamp,'historical':historical,'games':[],'bundle':None,'saved_rows':[],
            'actual_rows':[],'warnings':[],'stages':[],'error':None}
    def stage(label):
        result['stages'].append(label)
        if progress:progress(label)
    def resource(method,*args):return memo_call(provider,method,*args,now=now)
    stage('Importing schedule for '+date+' (Eastern)')
    games=provider.free_schedule(date,team_directory());result['games']=games
    for snap in snapshots:
        for row in snap['rows']:
            if slate_day(row['game_time'])==date:
                result['saved_rows'].append({**row,'snapshot_id':snap['id'],'snapshot_time':snap['created']})
    if not games:
        result['stages'].append('No games returned for the selected date')
        return result
    year=Date.fromisoformat(date).year-(Date.fromisoformat(date).month<10)
    season=f'{year}-{str(year+1)[-2:]}'
    prior=f'{year-1}-{str(year)[-2:]}'
    preseason=any(g.get('season_type')=='Preseason' for g in games)
    if historical or any(g.get('completed') for g in games):
        stage('Importing completed game results')
        try:
            results=resource('nba_logs',season,'Pre Season' if preseason else 'Regular Season')
            result['actual_rows']=completed_results(games,results,date,stamp)
            if any(g.get('completed') for g in games) and not result['actual_rows']:
                result['warnings'].append('Completed box scores unavailable for this date; saved predictions are preserved.')
        except ProviderError as e:result['warnings'].append(str(e))
    if historical or any(g.get('completed') for g in games):
        from .boxscores import final_boxscores
        matched_games={r['game_id'] for r in result['actual_rows']}
        for game in games:
            if game.get('completed') and game['game_id'] not in matched_games:
                try:result['actual_rows'].extend(final_boxscores(provider,game,stamp))
                except ProviderError as e:result['warnings'].append(str(e))
    if historical:
        result['warnings'].append('Historical odds/injuries: N/A — unavailable historically unless recorded in a saved pregame snapshot.')
        stage('Loaded saved pregame predictions; no current roster, injuries or odds used')
        return result
    stage('Importing current roster and season history')
    roster=resource('nba_roster',season)
    logs=[]
    if not preseason:
        try:logs=resource('nba_logs',season,'Regular Season')
        except ProviderError as e:result['warnings'].append('Current-season logs unavailable: '+str(e))
    # Previous season fills players without enough current-season history, transparently.
    try:logs=logs+resource('nba_logs',prior,'Regular Season')
    except ProviderError as e:result['warnings'].append('Prior-season baseline unavailable: '+str(e))
    bundle=build_nba_slate(games,roster,logs)
    if preseason:
        stage('Importing preseason minutes history')
        try:prelogs=resource('nba_logs',season,'Pre Season')
        except ProviderError as e:prelogs=[];result['warnings'].append(str(e))
        add_preseason_context(bundle,prelogs,stamp)
    configured=getattr(provider,'configured',lambda key:bool(os.getenv(key)))
    stage('Checking free injury reports first')
    if hasattr(provider,'free_injuries'):
        try:attach_injuries(bundle,resource('free_injuries'),stamp,source='ESPN free injury report')
        except ProviderError as e:result['warnings'].append(str(e))
    def unresolved():
        return any(bundle['contexts'].get(str(p['player_id']),{}).get('injury_status') in (None,'Unknown') for p in bundle['players'])
    if unresolved() and configured('BALLDONTLIE_API_KEY'):
        stage('Filling missing injury statuses from BallDontLie')
        try:attach_injuries(bundle,resource('injuries'),stamp)
        except ProviderError as e:result['warnings'].append(str(e))
    if unresolved() and configured('SPORTSDATAIO_API_KEY'):
        stage('Filling remaining injury statuses from SportsDataIO')
        try:
            raw=resource('sportsdataio','injuries',date)
            normalized=[{'player':{'first_name':p.get('FirstName',''),'last_name':p.get('LastName','')},
                         'status':p.get('InjuryStatus') or 'Unknown'} for p in raw]
            attach_injuries(bundle,normalized,stamp,source='SportsDataIO')
        except ProviderError as e:result['warnings'].append(str(e))
    if unresolved():result['warnings'].append('Some injury statuses remain unknown. Absence from an injury report does not establish availability.')
    if configured('ODDS_API_KEY'):
        stage('Importing and matching sportsbook lines')
        try:
            unmatched=attach_lines(bundle,resource('odds',date))
            if unmatched:result['warnings'].append(f'{unmatched} odds records could not be uniquely matched; excluded.')
        except ProviderError as e:result['warnings'].append(str(e))
    else:result['warnings'].append('Player prop lines UNAVAILABLE — missing API key: ODDS_API_KEY')
    bundle['provider_health']=dict(provider.health)
    bundle['loaded_for_date']=date;bundle['loaded_at']=stamp
    result['bundle']=bundle
    stage('Imported '+str(len(bundle['players']))+' player-game entries')
    return result
