from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_empty_pages_render():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    assert not app.exception
    for page in ['Completed Games Audit','NBA Model Retraining','Historical Backtesting','Data Sources & Import']:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception


def test_date_selection_imports_once_and_clears_previous_date(monkeypatch):
    from datetime import date,datetime,timezone,timedelta
    from nba import sync
    calls=[]
    def load(provider,day,**kwargs):
        calls.append(day)
        return {'date':day,'loaded_at':datetime.now(timezone.utc).isoformat(),'historical':False,
                'games':[],'bundle':None,'actual_rows':[],'saved_rows':[],'warnings':[], 'stages':[],'error':None}
    monkeypatch.setattr(sync,'load_date',load)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    assert len(calls)==1
    next_day=app.sidebar.date_input[0].value+timedelta(days=1)
    app.sidebar.date_input[0].set_value(next_day).run()
    assert calls[-1]==str(next_day) and len(calls)==2
    app.run()
    assert len(calls)==2
    app.sidebar.date_input[0].set_value(next_day+timedelta(days=1)).run()
    assert app.session_state['date_result']['date']==str(next_day+timedelta(days=1))
    assert app.session_state['bundle'] is None
    assert not app.exception


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
