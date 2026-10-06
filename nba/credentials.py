"""Browser-session credentials: never write user-entered secrets to shared environment or disk."""
from .providers import Providers, KEYS
from .errors import ProviderError


def reset_imports(state):
    for key in ('date_results','date_result','bundle','review_sync','api_checks'):
        state.pop(key,None)
    state['providers']=Providers(prefer_snapshots=True,credentials=state.get('api_credentials',{}))


def apply_inputs(state):
    credentials=dict(state.get('api_credentials',{}))
    for key in KEYS.values():
        value=state.pop('input_'+key,'').strip()
        if value:credentials[key]=value
    state['api_credentials']=credentials
    reset_imports(state)
    state['keys_notice']='Keys applied to this browser session. Cached imports cleared; the selected slate will reload with these credentials.'


def check_provider(provider,name,date):
    checks=[]
    if name=='BallDontLie':
        endpoints=[('Schedule','https://api.balldontlie.io/v1/games',{'dates[]':str(date),'per_page':1}),
                   ('Player game stats','https://api.balldontlie.io/v1/stats',{'dates[]':str(date),'per_page':1}),
                   ('Injuries','https://api.balldontlie.io/v1/player_injuries',{'per_page':1})]
    elif name=='SportsDataIO':
        endpoints=[('NBA projections','https://api.sportsdata.io/v3/nba/projections/json/PlayerGameProjectionStatsByDate/'+str(date),{})]
    else:
        endpoints=[('NBA odds events','https://api.the-odds-api.com/v4/sports/basketball_nba/events',{})]
    for label,url,params in endpoints:
        try:
            result=provider.get(name,url,params)
            data=result.get('data',[]) if isinstance(result,dict) else result
            checks.append({'Feature':label,'Status':'Connected','Records returned':len(data) if isinstance(data,list) else None})
        except ProviderError as e:checks.append({'Feature':label,'Status':str(e),'Records returned':None})
    if name=='The Odds API' and checks[0]['Status']=='Connected':
        try:
            lines=provider.odds(str(date))
            checks.append({'Feature':'Player prop markets for selected date','Status':'Connected' if lines else 'No player props returned for this date','Records returned':len(lines)})
        except ProviderError as e:checks.append({'Feature':'Player props','Status':str(e),'Records returned':None})
    return checks


def render_credentials(st,provider,date):
    st.subheader('API keys & connections')
    st.caption('Enter the keys you already have. Fields are masked and never prefilled. Blank fields keep the current key. Session keys stay in this browser session’s server memory and are not saved to shared files or exported with predictions.')
    if st.session_state.get('keys_notice'):st.success(st.session_state.pop('keys_notice'))
    with st.form('api_credentials_form',clear_on_submit=True):
        for name,key in KEYS.items():
            st.text_input(name+' API key',type='password',key='input_'+key,help=key)
        st.form_submit_button('Apply keys & reload data',on_click=apply_inputs,args=(st.session_state,))
    for name,key in KEYS.items():
        source='This browser session' if st.session_state.get('api_credentials',{}).get(key) else 'Server configuration' if provider.configured(key) else 'Missing'
        st.write('**'+name+'** · '+source)
        if st.button('Test '+name,disabled=not provider.configured(key),key='test_'+key):
            with st.spinner('Checking '+name+' access…'):
                st.session_state.setdefault('api_checks',{})[name]=check_provider(provider,name,date)
        results=st.session_state.get('api_checks',{}).get(name)
        if results:st.dataframe(results,hide_index=True,width='stretch')
    st.caption('Tests make API requests and can use your provider quota. A working key does not guarantee subscription access to injuries or prop markets. SportsDataIO imports remain available through its existing manual import control.')
    def clear():
        st.session_state.pop('api_credentials',None)
        for key in KEYS.values():st.session_state.pop('input_'+key,None)
        reset_imports(st.session_state)
        st.session_state['keys_notice']='Session keys removed. Existing server credentials, if configured, remain available.'
    st.button('Remove session keys',on_click=clear)
    with st.expander('Keep keys available after closing the browser'):
        st.write('For permanent configuration, open this app’s **Manage app → Settings → Secrets** in Streamlit Community Cloud. Add your keys there using these names, then save. This requires access to the app’s Streamlit settings.')
        st.code('BALLDONTLIE_API_KEY = "your-key"\nSPORTSDATAIO_API_KEY = "your-key"\nODDS_API_KEY = "your-key"',language='toml')
        st.caption('Server credentials are shared by this deployed app. Session entry above does not change them.')
