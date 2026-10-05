from nba.sync import load_date,attach_lines
from nba.providers import ProviderError

GAME={'game_id':'g','game_time':'2026-10-06T23:00:00Z','home_id':'1','away_id':'2','home':'A','away':'B','season_type':'Preseason','completed':False}
ROSTER=[{'player_id':'p','player':'Fixture One','team_id':'1','team':'A','team_name':'Team A'},
        {'player_id':'q','player':'Fixture Two','team_id':'2','team':'B','team_name':'Team B'}]
class Provider:
    def __init__(self,games=None):self.health={};self.calls=[];self.games=[GAME] if games is None else games
    def free_schedule(self,date,teams):self.calls.append(('schedule',date));return self.games
    def nba_roster(self,season):self.calls.append(('roster',season));return ROSTER
    def nba_logs(self,season,kind):
        self.calls.append(('logs',season,kind))
        return []
    def injuries(self):self.calls.append(('injuries',));return []
    def odds(self,date):self.calls.append(('odds',date));return []


def test_no_games_stops_unnecessary_imports():
    p=Provider([])
    r=load_date(p,'2026-10-06',now='2026-10-05T12:00:00Z')
    assert r['games']==[] and p.calls==[('schedule','2026-10-06')]


def test_upcoming_date_imports_roster_history_and_configured_feeds(monkeypatch):
    monkeypatch.setenv('ODDS_API_KEY','test-only')
    monkeypatch.setenv('BALLDONTLIE_API_KEY','test-only')
    p=Provider()
    r=load_date(p,'2026-10-06',now='2026-10-05T12:00:00Z')
    assert ('roster','2026-27') in p.calls
    assert ('logs','2025-26','Regular Season') in p.calls
    assert ('logs','2026-27','Pre Season') in p.calls
    assert ('odds','2026-10-06') in p.calls and ('injuries',) in p.calls
    assert r['bundle']['loaded_for_date']=='2026-10-06'
    assert len(r['bundle']['players'])==2


def test_historical_date_never_imports_current_roster_odds_or_injuries():
    p=Provider([{**GAME,'game_time':'2026-10-04T23:00:00Z','completed':True}])
    saved={'id':'saved','created':'2026-10-04T12:00:00Z','rows':[{'game_time':'2026-10-04T23:00:00Z','projection':11}]}
    r=load_date(p,'2026-10-04',now='2026-10-05T12:00:00Z',snapshots=[saved])
    assert r['historical'] and r['bundle'] is None
    assert not any(c[0] in ('roster','odds','injuries') for c in p.calls)
    assert r['saved_rows'][0]['projection']==11


def test_optional_feed_failure_does_not_hide_players(monkeypatch):
    monkeypatch.setenv('ODDS_API_KEY','test-only')
    monkeypatch.delenv('BALLDONTLIE_API_KEY',raising=False)
    p=Provider()
    def denied(date):raise ProviderError('Odds unavailable')
    p.odds=denied
    r=load_date(p,'2026-10-06',now='2026-10-05T12:00:00Z')
    assert r['bundle']['players']
    assert 'Odds unavailable' in r['warnings']


def test_exact_odds_join_rejects_wrong_game():
    players=[{**p,'game_id':'g','game_time':GAME['game_time'],'opponent':'B' if p['team']=='A' else 'A'} for p in ROSTER]
    bundle={'players':players}
    line={'player':'Fixture One','home_team':'Team A','away_team':'Team B','game_time':GAME['game_time'],'line':10,'stat':'pts'}
    assert attach_lines(bundle,[line])==0
    assert bundle['lines'][0]['player_id']=='p'
    assert attach_lines(bundle,[{**line,'away_team':'Wrong Team'}])==1
    assert bundle['lines']==[]


def test_results_match_complete_game_and_both_teams():
    from nba.sync import completed_results
    rows=[{'date':'2026-10-06','game_id':'nba-g','team':p['team'],'player_id':p['player_id']} for p in ROSTER]
    result=completed_results([{**GAME,'completed':True}],rows,'2026-10-06','2026-10-07T12:00:00Z')
    assert len(result)==2 and all(r['game_id']=='g' for r in result)
    assert completed_results([GAME],rows,'2026-10-06','2026-10-07T12:00:00Z')==[]
