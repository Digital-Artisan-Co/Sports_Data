from nba.schedule import normalize_espn, slate_day
from nba.model import project
from nba.slate import add_preseason_context


def test_eastern_slate_includes_after_midnight_utc():
    assert slate_day('2026-10-06T02:00:00Z')=='2026-10-05'
    assert slate_day('2026-01-06T04:00:00Z')=='2026-01-05'
    assert slate_day('2026-10-06T05:00:00Z')=='2026-10-06'


def test_exact_name_join_avoids_abbreviation_mismatch():
    roster=[{'team_id':'1','team':'AA','team_name':'Fixture A'},{'team_id':'2','team':'BB','team_name':'Fixture B'}]
    event={'id':'fixture','date':'2026-10-06T02:00Z','season':{'type':1},'competitions':[{'competitors':[
        {'homeAway':'home','team':{'displayName':'Fixture A','abbreviation':'different'}},
        {'homeAway':'away','team':{'displayName':'Fixture B','abbreviation':'other'}}]}]}
    games=normalize_espn({'events':[event]},roster,'2026-10-05')
    assert len(games)==1 and games[0]['season_type']=='Preseason'
    assert games[0]['home_id']=='1' and games[0]['game_id']=='espn:fixture'


def test_preseason_does_not_substitute_regular_minutes():
    player={'player_id':'fixture','season_type':'Preseason'}
    logs=[{'player_id':'fixture','date':f'2026-04-{i:02d}','min':38,'pts':25} for i in range(1,11)]
    output=project(player,logs,'pts','2026-10-05')
    assert output['projection'] is None
    assert output['regular_season_reference_average']==25


def test_preseason_minutes_use_prior_preseason_only():
    bundle={'players':[{'player_id':'fixture','season_type':'Preseason'}],'contexts':{}}
    logs=[{'player_id':'fixture','date':'2026-10-03','min':18,'season_type':'Pre Season'},
          {'player_id':'fixture','date':'2026-10-06','min':40,'season_type':'Pre Season'},
          {'player_id':'fixture','date':'2026-04-01','min':38,'season_type':'Regular Season'}]
    context=add_preseason_context(bundle,logs,'2026-10-05T12:00:00Z')['contexts']['fixture']
    assert context['projected_minutes']==18
    assert context['preseason_minutes_games']==1
