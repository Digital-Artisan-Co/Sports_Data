"""Synthetic fixtures are test-only; never exposed as application data."""
from datetime import datetime, timedelta, timezone
import pytest
from nba.model import project, recommendation, STATS
from nba.pipeline import run
from nba.storage import Store
from nba.audit import audit, metrics

@pytest.fixture
def bundle():
    player={'player_id':'test-id','player':'Test fixture','team':'TEST','opponent':'OTHER','game_id':'test-game','game_time':'2026-01-20T20:00:00Z'}
    logs=[{'player_id':'test-id','date':f'2026-01-{i:02d}','min':30,'pts':20,'reb':8,'ast':6,'fg3m':2,'fg3a':6,'stl':1,'blk':1} for i in range(1,15)]
    return {'players':[player],'logs':logs,'source':'test fixture'}

def test_models_and_future_exclusion(bundle):
    for stat in STATS.values():
        before=project(bundle['players'][0],bundle['logs'],stat,'2026-01-20')
        future={**bundle['logs'][0],'date':'2026-01-21',stat:999}
        after=project(bundle['players'][0],bundle['logs']+[future],stat,'2026-01-20')
        assert before['projection']==after['projection']
        assert before['projection']>0
        assert before['missing']

def test_no_data_no_projection(bundle):
    result=project(bundle['players'][0],[], 'pts','2026-01-20')
    assert result['projection'] is None

def test_missing_context_no_bet(bundle):
    rows=run(bundle,'2026-01-20T12:00:00Z')
    assert len(rows)==6
    assert all(r['recommendation']=='No Play' for r in rows)
    assert all(r['top3_spike'] is None for r in rows)

def test_historical_context_and_odds_excluded(bundle):
    bundle['contexts']={'test-id':{'known_at':'2026-01-21','injury_status':'Available','pts_opportunity_score':99}}
    bundle['lines']=[{'player_id':'test-id','game_id':'test-game','stat':'pts','line':10,'timestamp':'2026-01-21'}]
    rows=run(bundle,'2026-01-20T12:00:00Z',True)
    assert rows[0]['line'] is None
    assert rows[0]['injury_status']=='Unknown'
    assert rows[0]['historical_availability']=='N/A — unavailable historically'

def test_immutable_snapshot_and_push(bundle,tmp_path):
    store=Store(str(tmp_path/'db.sqlite'));rows=run(bundle,'2026-01-20T12:00:00Z');rows[0]['line']=20;rows[0]['recommendation']='Take Over'
    identifier=store.save({'rows':rows},'2026-01-20T12:00:00Z')
    rows[0]['projection']=999
    assert store.snapshots()[0]['rows'][0]['projection']!=999
    with pytest.raises(ValueError):store.save({'rows':rows},'2026-01-21')
    actual={**bundle['logs'][0],'game_id':'test-game','status':'Final'};store.result(actual)
    results=audit(store.snapshots(),store.results())
    assert len(results)==6 and results[0]['ou_result']=='Push'
    assert results[0]['recommendation_result']=='Push'
    assert metrics(results)['recommendation_accuracy'] is None

def test_live_results_rejected(bundle,tmp_path):
    with pytest.raises(ValueError):Store(str(tmp_path/'db')).result({**bundle['logs'][0],'game_id':'x','status':'Live'})

def test_conservative_defensive_recommendation():
    r={'projection':2,'line':1,'confidence':70,'role_security':85,'opportunity':80,'matchup':70,'stat':'stl','injury_status':'Available','line_fresh':True}
    assert recommendation(r)=='Pass'
    assert recommendation({**r,'defensive_activity':True})=='Take Over'

def test_feature_coverage():
    from nba.features import enrich
    assert enrich({})['pts_opportunity_score'] is None
    context={'feature_percentiles':{'pts':{'opportunity':{'usage':80,'fga':80,'fta':80,'touches':80,'drives':80,'recent_shot_volume':80}}}}
    assert enrich(context)['pts_opportunity_score']==80
