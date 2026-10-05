"""Read-only provider adapters. No synthetic fallback and no credential logging."""
import os
import time
from datetime import datetime, timezone
import requests

KEYS={'BallDontLie':'BALLDONTLIE_API_KEY','SportsDataIO':'SPORTSDATAIO_API_KEY','The Odds API':'ODDS_API_KEY'}
class ProviderError(RuntimeError): pass

class Providers:
    def __init__(self,allow_snapshots=True,prefer_snapshots=False): self.health={}; self.allow_snapshots=allow_snapshots; self.prefer_snapshots=prefer_snapshots
    def get(self, provider, endpoint, params=None):
        key=KEYS.get(provider)
        if key and not os.getenv(key):
            self.health[provider]={'status':'UNAVAILABLE — missing API key','required_key':key,'endpoint':endpoint}
            raise ProviderError(f'UNAVAILABLE — missing API key: {key}')
        headers={}; query=dict(params or {})
        if provider=='BallDontLie': headers['Authorization']=os.environ[key]
        elif provider=='SportsDataIO': headers['Ocp-Apim-Subscription-Key']=os.environ[key]
        elif provider=='The Odds API': query['apiKey']=os.environ[key]
        try:
            r=requests.get(endpoint,params=query,headers=headers,timeout=25)
            if r.status_code!=200:
                reason='request denied by server; this does not establish a paid-subscription requirement' if provider.startswith('NBA') else 'endpoint unavailable or subscription lacks access'
                raise ProviderError(f'{provider}: HTTP {r.status_code}; {reason}')
            result=r.json()
            self.health[provider]={'status':'Connected','last_successful_sync':datetime.now(timezone.utc).isoformat(),'endpoint':endpoint}
            return result
        except (requests.RequestException,ValueError,ProviderError) as exc:
            # requests exceptions can include API keys in URLs; never expose them.
            message=str(exc) if isinstance(exc,ProviderError) else f'{provider}: request failed ({type(exc).__name__})'
            self.health[provider]={'status':message,'failed_endpoint':endpoint}
            raise ProviderError(message) from None
    def pages(self,path,params):
        output=[]; cursor=None
        for _ in range(100):
            data=self.get('BallDontLie','https://api.balldontlie.io/v1/'+path,{**params,'per_page':100,**({'cursor':cursor} if cursor else {})})
            output.extend(data['data']); next_cursor=data.get('meta',{}).get('next_cursor')
            if not next_cursor: return output
            if next_cursor==cursor: raise ProviderError('Pagination did not advance')
            cursor=next_cursor
        raise ProviderError('Import exceeded 100 pages; narrow the date range')
    def schedule(self,date): return self.pages('games',{'dates[]':date})
    def injuries(self): return self.pages('player_injuries',{})
    def logs(self,start,end):
        raw=self.pages('stats',{'start_date':start,'end_date':end})
        output=[]
        for x in raw:
            minutes=x.get('min') or '0'; parts=str(minutes).split(':'); minutes=float(parts[0] or 0)+(float(parts[1])/60 if len(parts)>1 else 0)
            output.append({'player_id':str(x['player']['id']),'player':x['player']['first_name']+' '+x['player']['last_name'],'team':x['team']['abbreviation'],'position':x['player'].get('position'),'game_id':str(x['game']['id']),'date':x['game']['date'],'season':x['game'].get('season'),'min':minutes,**{k:x.get(k,0) for k in ['pts','reb','ast','fg3m','fg3a','fga','fgm','fta','ftm','stl','blk','pf']}})
        return output
    def odds(self,date):
        events=self.get('The Odds API','https://api.the-odds-api.com/v4/sports/basketball_nba/events')
        rows=[]
        mapping={'player_points':'pts','player_rebounds':'reb','player_assists':'ast','player_threes':'fg3m','player_steals':'stl','player_blocks':'blk'}
        for event in events:
            from .schedule import slate_day
            if slate_day(event['commence_time'])!=date: continue
            data=self.get('The Odds API',f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event['id']}/odds",{'regions':'us','markets':','.join(mapping),'oddsFormat':'american'})
            for book in data.get('bookmakers',[]):
                for market in book['markets']:
                    grouped={}
                    for o in market['outcomes']:
                        key=(o.get('description'),o.get('point')); row=grouped.setdefault(key,{'player':key[0],'line':key[1],'stat':mapping.get(market['key']),'sportsbook':book['key'],'timestamp':market.get('last_update',book.get('last_update')),'game_time':event['commence_time'],'home_team':event['home_team'],'away_team':event['away_team'],'source':'The Odds API'})
                        row[o['name'].lower()+'_odds']=o['price']
                    rows.extend(grouped.values())
        return rows
    def sportsdataio(self,resource,date):
        paths={'projections':'v3/nba/projections/json/PlayerGameProjectionStatsByDate','injuries':'v3/nba/scores/json/Players','box_scores':'v3/nba/stats/json/PlayerGameStatsByDate'}
        if resource not in paths: raise ProviderError('Unsupported SportsDataIO resource')
        path=paths[resource]; suffix='' if resource=='injuries' else '/'+date
        return self.get('SportsDataIO','https://api.sportsdata.io/'+path+suffix)
    def nba_logs(self,season,season_type="Regular Season"):
        if self.allow_snapshots and getattr(self,'prefer_snapshots',False):
            from .snapshots import load_snapshot
            try:
                rows,health=load_snapshot('logs',season,season_type)
                self.health['NBA.com']=health
                return rows
            except ValueError:pass
        try:
            from nba_api.stats.endpoints import leaguegamelog
            records=leaguegamelog.LeagueGameLog(season=season,season_type_all_star=season_type,player_or_team_abbreviation='P',timeout=25).get_data_frames()[0].to_dict('records')
            output=[{'player_id':str(x['PLAYER_ID']),'player':x['PLAYER_NAME'],'team':x['TEAM_ABBREVIATION'],'game_id':str(x['GAME_ID']),'date':str(x['GAME_DATE'])[:10],'season':season,'season_type':season_type,'min':float(x['MIN']),**{k:float(x[k.upper()]) for k in ['pts','reb','ast','fg3m','fg3a','fga','fgm','fta','ftm','stl','blk','pf']}} for x in records]
            self.health['NBA.com']={'status':'Connected','last_successful_sync':datetime.now(timezone.utc).isoformat()}
            return output
        except Exception as exc:
            self.health['NBA.com']={'status':f'UNAVAILABLE — {type(exc).__name__}','failed_endpoint':'stats.nba.com/stats/leaguegamelog'}
            if self.allow_snapshots:
                from .snapshots import load_snapshot
                try:
                    rows,health=load_snapshot('logs',season,season_type)
                    self.health['NBA.com']=health
                    return rows
                except ValueError:pass
            raise ProviderError('NBA.com game logs unavailable; no usable saved snapshot for this season') from None

    def nba_schedule(self, date):
        data=self.get('NBA schedule','https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json')
        output=[]
        for day in data.get('leagueSchedule',{}).get('gameDates',[]):
            for g in day.get('games',[]):
                tip=g.get('gameDateTimeUTC')
                if not tip or tip[:10]!=date: continue
                output.append({'game_id':str(g['gameId']),'game_time':tip,
                    'home_id':str(g['homeTeam']['teamId']),'away_id':str(g['awayTeam']['teamId']),
                    'home':g['homeTeam']['teamTricode'],'away':g['awayTeam']['teamTricode']})
        return output

    def nba_roster(self, season):
        if self.allow_snapshots and getattr(self,'prefer_snapshots',False):
            from .snapshots import load_snapshot
            try:
                rows,health=load_snapshot('roster',season)
                self.health['NBA roster']=health
                return rows
            except ValueError:pass
        try:
            from nba_api.stats.endpoints import commonallplayers
            records=commonallplayers.CommonAllPlayers(is_only_current_season=1,season=season,timeout=25).get_data_frames()[0].to_dict('records')
            result=[{'player_id':str(x['PERSON_ID']),'player':x['DISPLAY_FIRST_LAST'],
                'team_id':str(x['TEAM_ID']),'team':x['TEAM_ABBREVIATION'],'team_name':str(x['TEAM_CITY'])+' '+str(x['TEAM_NAME'])} for x in records if x.get('TEAM_ID')]
            self.health['NBA roster']={'status':'Connected','last_successful_sync':datetime.now(timezone.utc).isoformat()}
            return result
        except Exception as exc:
            self.health['NBA roster']={'status':f'UNAVAILABLE — {type(exc).__name__}'}
            if self.allow_snapshots:
                from .snapshots import load_snapshot
                try:
                    rows,health=load_snapshot('roster',season)
                    self.health['NBA roster']=health
                    return rows
                except ValueError:pass
            raise ProviderError('NBA current roster unavailable; no fresh current-season snapshot available') from None

    def espn_schedule(self, date, roster):
        from .schedule import normalize_espn
        data=self.get('ESPN schedule','https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',{'dates':date.replace('-',''),'limit':1000})
        if not isinstance(data.get('events'),list):raise ProviderError('ESPN schedule response is missing events')
        return normalize_espn(data,roster,date)

    def free_schedule(self, date, roster):
        from datetime import date as Date, timedelta
        from .slate import normalize_bdl_schedule
        from .schedule import slate_day
        try:
            return self.espn_schedule(date,roster)
        except (ProviderError,ValueError) as error:
            self.health['ESPN schedule']={'status':str(error)}
        day=Date.fromisoformat(date)
        try:
            games=self.nba_schedule(date)+self.nba_schedule(str(day+timedelta(days=1)))
            return [g for g in games if slate_day(g['game_time'])==date]
        except ProviderError:
            records=self.pages('games',{'start_date':str(day),'end_date':str(day+timedelta(days=1))})
            games=normalize_bdl_schedule(records,roster,date,timezone='America/New_York')
            self.health['Schedule fallback']={'status':'Connected','source':'BallDontLie schedule; preseason coverage may be incomplete',
                'last_successful_sync':datetime.now().astimezone().isoformat()}
            return games

    def upcoming_dates(self, date, roster):
        from datetime import date as Date, timedelta
        from .schedule import slate_day
        start=Date.fromisoformat(date)
        end=start+timedelta(days=45)
        data=self.get('ESPN schedule','https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',
            {'dates':start.strftime('%Y%m%d')+'-'+end.strftime('%Y%m%d'),'limit':1000})
        return sorted({slate_day(g['date']) for g in data.get('events',[]) if g.get('date') and slate_day(g['date'])>=date})
