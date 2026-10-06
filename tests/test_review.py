from datetime import datetime,timedelta,timezone
import pandas as pd
from nba.storage import Store
from nba.audit import audit
from nba.training import reconstruct,validate_corrections
from nba.pipeline import run


def test_automatic_saves_are_immutable_and_audit_uses_latest(tmp_path):
    store=Store(tmp_path/'db')
    row=dict(player_id='1',game_id='g',game_time='2026-01-02T20:00:00Z',stat='pts',projection=20,
             projected_minutes=30,recommendation='No Play')
    assert len(store.save_automatic([row],'test','2026-01-02T12:00:00Z'))==1
    assert store.save_automatic([row],'test','2026-01-02T12:01:00Z')==[]
    store.save_automatic([{**row,'projection':22}],'test','2026-01-02T12:11:00Z')
    assert store.snapshots()[0]['rows'][0]['projection']==20
    results={('g','1'):dict(min=30,pts=23)}
    assert len(audit(store.snapshots(),results))==1
    assert audit(store.snapshots(),results)[0]['projection_error']==-1
    assert store.save_automatic([row],'test','2026-01-03')==[]


def test_reconstruction_excludes_target_and_future_outcomes():
    logs=[dict(player_id='1',player='Fixture',team='A',game_id=str(i),date=f'2026-01-{i:02}',
               min=30,pts=20,reb=8,ast=6,fg3m=2,stl=1,blk=1) for i in range(1,16)]
    before=reconstruct(logs,'2026-01-10','2026-01-10')
    altered=[{**r,'pts':999} if r['date']>='2026-01-10' else r for r in logs]
    after=reconstruct(altered,'2026-01-10','2026-01-10')
    assert [r['projection'] for r in before]==[r['projection'] for r in after]
    assert before[0]['actual']!=after[0]['actual']


def test_holdout_does_not_determine_correction_and_artifact_persists(tmp_path):
    rows=[]
    for d in range(20):
        day=(datetime(2026,1,1)+timedelta(days=d)).date().isoformat()
        for p in range(10):
            rows.append(dict(game_id=day,player_id=str(p),stat='pts',game_time=day,
                result_known_at=day,projection=22,actual=20,projection_error=2))
    artifact=validate_corrections(rows,'2026-03-01')
    assert artifact['corrections']['pts']>0
    altered=[{**r,'actual':10,'projection_error':12} if r['game_time']>=artifact['validation_start'] else r for r in rows]
    assert validate_corrections(altered,'2026-03-01')['corrections']==artifact['corrections']
    store=Store(tmp_path/'db');store.artifact({**artifact,'status':'active'})
    assert Store(tmp_path/'db').active_calibration()['corrections']==artifact['corrections']


def test_review_page_syncs_and_displays_final_results(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from nba import sync
    def load(*args,**kwargs):
        return {'actual_rows':[dict(game_id='g',player_id='1',player='Fixture',team='A',opponent='B',
            game_time='2026-01-02T20:00:00Z',min=30,pts=20,reb=8,ast=6,fg3m=2,stl=1,blk=1,status='Final')],'warnings':[]}
    monkeypatch.setattr(sync,'load_date',load)
    def page():
        import streamlit as st
        from datetime import date
        from nba.review import render_review
        from nba.storage import Store
        from nba.providers import Providers
        render_review(st,Store(),Providers(),date(2026,1,2),'Completed Games Audit')
    app=AppTest.from_function(page).run()
    assert not app.exception
    assert any('Points' in df.value and df.value.Points.tolist()==[20] for df in app.dataframe)


def test_activated_calibration_changes_future_regular_season_only():
    logs=[dict(player_id='1',date=f'2026-01-{d:02}',min=30,pts=20,reb=8,ast=6,fg3m=2,stl=1,blk=1) for d in range(1,10)]
    player=dict(player_id='1',player='Fixture',team='A',opponent='B',game_id='g',game_time='2026-01-20T20:00:00Z',season_type='Regular Season')
    bundle={'players':[player],'logs':logs}
    calibration={'id':'candidate','trained_before':'2026-01-15','corrections':{'pts':2}}
    baseline=run(bundle,'2026-01-20T12:00:00Z')
    corrected=run(bundle,'2026-01-20T12:00:00Z',calibration=calibration)
    assert corrected[0]['projection']==baseline[0]['projection']-2
    assert corrected[1]['projection']==baseline[1]['projection']
    assert run(bundle,'2026-01-14',calibration=calibration)[0]['projection']==run(bundle,'2026-01-14')[0]['projection']
