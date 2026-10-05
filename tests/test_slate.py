from nba.slate import build_nba_slate

def test_current_roster_overrides_historical_team():
    games=[{'game_id':'g','game_time':'2026-10-20T23:00:00Z','home_id':'1','away_id':'2','home':'A','away':'B'}]
    roster=[{'player_id':'p','player':'Fixture','team_id':'1','team':'A'}]
    logs=[{'player_id':'p','team':'OLD'}]
    result=build_nba_slate(games,roster,logs)
    assert result['players'][0]['team']=='A'
    assert result['players'][0]['opponent']=='B'
    assert result['players'][0]['player_id']=='p'
    assert not result['contexts'] and not result['lines']

def test_no_invented_players():
    assert build_nba_slate([],[],[{'player_id':'p'}])['players']==[]


def test_bdl_schedule_uses_nba_roster_ids():
    from nba.slate import normalize_bdl_schedule
    roster=[{'team':'AAA','team_id':'111'},{'team':'BBB','team_id':'222'}]
    records=[{'id':42,'datetime':'2026-10-06T00:00:00Z','home_team':{'abbreviation':'AAA','id':1},'visitor_team':{'abbreviation':'BBB','id':2}}]
    games=normalize_bdl_schedule(records,roster,'2026-10-06')
    assert games[0]['home_id']=='111'
    assert games[0]['away_id']=='222'
    assert games[0]['game_id']=='bdl:42'
    assert normalize_bdl_schedule(records,roster,'2026-10-05')==[]


def test_schedule_fallback(monkeypatch):
    from nba.providers import Providers,ProviderError
    p=Providers()
    def blocked(date): raise ProviderError('HTTP 403')
    monkeypatch.setattr(p,'nba_schedule',blocked)
    monkeypatch.setattr(p,'espn_schedule',lambda date,roster:blocked(date))
    monkeypatch.setattr(p,'pages',lambda path,params:[])
    assert p.free_schedule('2026-10-05',[])==[]
    assert p.health['Schedule fallback']['status']=='Connected'


def test_unmatched_team_stops_build():
    import pytest
    from nba.slate import normalize_bdl_schedule
    record={'id':1,'datetime':'2026-10-05T20:00:00Z','home_team':{'abbreviation':'AAA'},'visitor_team':{'abbreviation':'BBB'}}
    with pytest.raises(ValueError,match='Cannot uniquely match'):
        normalize_bdl_schedule([record],[],'2026-10-05')
