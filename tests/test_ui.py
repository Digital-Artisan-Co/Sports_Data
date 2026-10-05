from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_empty_pages_render():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    assert not app.exception
    for page in ['Completed Games Audit','NBA Model Retraining','Historical Backtesting','Data Sources & Import']:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception


def test_empty_slate_offers_returned_dates():
    from datetime import date
    class Provider:
        health={}
        def nba_roster(self,season):return []
        def free_schedule(self,date,roster):return []
        def upcoming_dates(self,date,roster):return ['2026-10-20']
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    app.session_state['providers']=Provider()
    app.session_state['nba_logs']=[{'player_id':'fixture'}]
    app.session_state['slate_date']=date(2026,10,5)
    app.sidebar.radio[0].set_value('Data Sources & Import').run()
    next(b for b in app.button if b.label=='Build free NBA slate').click().run()
    assert not app.exception
    dates=next(s for s in app.selectbox if s.label=='Upcoming dates returned by the schedule provider')
    assert dates.value=='2026-10-20'
    next(b for b in app.button if b.label=='Use this slate date').click().run()
    assert app.session_state['slate_date']==date(2026,10,20)


def test_deployment_password_gate(monkeypatch):
    monkeypatch.setenv('APP_ACCESS_PASSWORD','test-only-password')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    assert not app.exception
    assert not app.sidebar.radio
    app.text_input[0].set_value('wrong')
    app.button[0].click().run()
    assert not app.sidebar.radio
    app.text_input[0].set_value('test-only-password')
    app.button[0].click().run()
    assert not app.exception
    assert app.sidebar.radio[0].value=='Player Props'
