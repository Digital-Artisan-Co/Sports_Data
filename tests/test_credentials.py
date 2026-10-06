from nba.providers import Providers
from nba.credentials import apply_inputs


def test_session_credentials_are_isolated_and_never_written_to_environment(monkeypatch):
    monkeypatch.delenv('ODDS_API_KEY',raising=False)
    import os
    captured=[]
    class Response:
        status_code=200
        def json(self):return []
    def get(url,**kwargs):captured.append(kwargs['params'].get('apiKey'));return Response()
    monkeypatch.setattr('nba.providers.requests.get',get)
    first=Providers(credentials={'ODDS_API_KEY':'test-session-one'})
    second=Providers(credentials={'ODDS_API_KEY':'test-session-two'})
    first.get('The Odds API','https://example.test')
    second.get('The Odds API','https://example.test')
    assert captured==['test-session-one','test-session-two']
    assert not os.getenv('ODDS_API_KEY')
    assert not Providers().configured('ODDS_API_KEY')
    state={'api_credentials':{'ODDS_API_KEY':'test-session-one'},'input_ODDS_API_KEY':'',
           'input_BALLDONTLIE_API_KEY':'test-bdl','date_results':{'old':{}},'bundle':{}}
    apply_inputs(state)
    assert state['api_credentials']['ODDS_API_KEY']=='test-session-one'
    assert state['providers'].configured('BALLDONTLIE_API_KEY')
    assert 'date_results' not in state and 'bundle' not in state
    assert 'input_BALLDONTLIE_API_KEY' not in state


def test_credentials_form_masks_clears_and_removes_session_keys():
    from streamlit.testing.v1 import AppTest
    def page():
        import streamlit as st
        from datetime import date
        from nba.providers import Providers
        from nba.credentials import render_credentials
        provider=st.session_state.setdefault('providers',Providers())
        render_credentials(st,provider,date(2026,10,6))
    app=AppTest.from_function(page).run()
    assert not app.exception
    app.text_input[0].set_value('test-form-key')
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['providers'].key_value('BALLDONTLIE_API_KEY')=='test-form-key'
    assert all(t.value=='' for t in app.text_input)
    next(b for b in app.button if b.label=='Remove session keys').click().run()
    assert not app.exception
    assert 'api_credentials' not in app.session_state
