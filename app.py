import json
import os
import hmac
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import pandas as pd
import streamlit as st
from nba.model import STATS
from nba.providers import Providers, KEYS
from nba.errors import ProviderError
from nba.storage import Store
from nba.runtime import DATA_DIR, save_cache
from nba.slate import build_nba_slate, add_preseason_context
from nba.schedule import slate_day, SLATE_TZ
from zoneinfo import ZoneInfo
from nba.pipeline import run, validate_bundle
from nba.audit import audit, metrics, capture, train_bias
from nba.sync import load_date
from nba.presentation import render_player_props, game_labels

st.set_page_config(page_title='NBA Player Props Model',layout='wide')
# Streamlit Community Cloud supplies secrets via st.secrets, not always os.environ.
# Only known application bindings are bridged; values are never displayed.
try:
    for secret_name in (*KEYS.values(),'APP_ACCESS_PASSWORD'):
        if not os.getenv(secret_name) and secret_name in st.secrets:
            os.environ[secret_name]=str(st.secrets[secret_name])
except FileNotFoundError:
    pass
if os.getenv('APP_ACCESS_PASSWORD'):
    if not st.session_state.get('access_granted'):
        with st.form('access'):
            password=st.text_input('App password',type='password')
            submitted=st.form_submit_button('Sign in')
        if submitted:
            if hmac.compare_digest(password,os.environ['APP_ACCESS_PASSWORD']):
                st.session_state['access_granted']=True
                st.rerun()
            else:st.error('Incorrect password')
        st.stop()
st.title('NBA Player Props Model')
st.caption('Auditable individual-stat projections · Baseline models are not yet historically calibrated')
pd.set_option('future.no_silent_downcasting', True)
store=Store()
# An open browser can outlive a provider module update. Replace only its client,
# preserving saved predictions, credentials and imported user data.
if type(st.session_state.get('providers')) is not Providers:
    st.session_state['providers']=Providers(prefer_snapshots=True,credentials=st.session_state.get('api_credentials',{}))
providers=st.session_state['providers']
page=st.sidebar.radio('Section',['Player Props','Completed Games Audit','NBA Model Retraining','Historical Backtesting','Data Sources & Import'],key='section')
selected_date=st.sidebar.date_input('Date',datetime.now(ZoneInfo(SLATE_TZ)).date(),key='slate_date')
cutoff=datetime.combine(selected_date,time.min,tzinfo=timezone.utc)
st.sidebar.caption('Slate dates use Eastern Time (America/New_York), including late games after midnight UTC. Stored timestamps remain UTC.')



def refresh_date():
    st.session_state.setdefault('date_results',{}).pop(str(selected_date),None)
    st.session_state.pop('lineup_cache',None)
    if hasattr(providers,'_date_import_cache'):providers._date_import_cache.clear()

st.sidebar.button('Refresh selected date',on_click=refresh_date)
if page in ('Player Props','Data Sources & Import'):
    cache=st.session_state.setdefault('date_results',{})
    key=str(selected_date)
    current=cache.get(key)
    expired=current and (datetime.now(timezone.utc)-datetime.fromisoformat(current['loaded_at'])).total_seconds()>600
    if current is None or expired:
        # Clear displayed data first; a failed new date must never show the old slate.
        st.session_state.pop('bundle',None)
        with st.status('Importing '+key+' automatically…',expanded=True) as status:
            try:
                current=load_date(providers,key,snapshots=store.snapshots(),progress=st.write)
                for actual in current['actual_rows']:store.result(actual)
                save_cache('slates/'+key+'.json',current)
                status.update(label='Loaded '+key,state='complete',expanded=False)
            except (ProviderError,ValueError,KeyError,OSError) as e:
                current={'date':key,'loaded_at':datetime.now(timezone.utc).isoformat(),'historical':False,
                         'games':[],'bundle':None,'actual_rows':[],'saved_rows':[], 'warnings':[],'stages':[],'error':str(e)}
                status.update(label='Import unavailable for '+key,state='error',expanded=True)
                st.error(str(e))
        cache[key]=current
    st.session_state['date_result']=current
    st.session_state['bundle']=current.get('bundle')
    if current.get('error'):st.error('Could not load '+key+': '+current['error']+'. Use Refresh selected date to retry.')
    elif not current['games']:st.info('No games returned for '+key+' (Eastern). Choose another date.')
    else:st.caption('Automatically loaded '+key+' · '+str(len(current['games']))+' games · '+current['loaded_at'])
    for warning in current.get('warnings',[]):st.warning(warning)

if page=='Data Sources & Import':
    from nba.credentials import render_credentials
    render_credentials(st, providers, selected_date)
    st.subheader('Data Source Health Panel')
    for provider,key in KEYS.items():
        st.write(provider, providers.health.get(provider,{'status':'Configured — not yet verified' if providers.configured(key) else 'UNAVAILABLE — missing API key','required_key':key}))
    st.write('NBA.com',providers.health.get('NBA.com',{'status':'Not yet checked; no API key required'}))
    st.info('Provider subscription tiers may restrict injuries, advanced statistics, or prop markets. Raw imports retain provider IDs; cross-provider player/game mappings require explicit matching.')
    st.info('Changing the sidebar date automatically imports the schedule, season history, roster and available configured odds/injuries. The controls below are optional diagnostics and manual imports.')
    cols=st.columns(3)
    with cols[0]:
        if st.button('Import schedule (BallDontLie)'):
            try: st.session_state['schedule']=providers.schedule(str(selected_date)); st.json(st.session_state['schedule'])
            except ProviderError as e:st.error(str(e))
        if st.button('Import injuries (BallDontLie)'):
            try:st.session_state['injuries']=providers.injuries();st.json(st.session_state['injuries'])
            except ProviderError as e:st.error(str(e))
    with cols[1]:
        start=st.date_input('Game log start',selected_date-timedelta(days=120))
        if st.button('Import game logs (BallDontLie)'):
            try:st.session_state['logs']=providers.logs(str(start),str(selected_date-timedelta(days=1)));st.success(f"Imported {len(st.session_state['logs'])} records")
            except ProviderError as e:st.error(str(e))
        season=st.text_input('NBA season','2025-26')
        if st.button('Import NBA.com game logs'):
            try:
                logs=providers.nba_logs(season)
                st.session_state['nba_logs']=logs
                DATA_DIR.mkdir(parents=True,exist_ok=True)
                save_cache('nba_logs.json',logs)
                st.success(f"Imported {len(logs)} records. Date imports run automatically.")
            except ProviderError as e:st.error(str(e))
    with cols[2]:
        if st.button('Import sportsbook lines'):
            try:st.session_state['raw_lines']=providers.odds(str(selected_date));st.json(st.session_state['raw_lines'])
            except ProviderError as e:st.error(str(e))
        resource=st.selectbox('SportsDataIO resource',['projections','box_scores','injuries'])
        if st.button('Fetch SportsDataIO'):
            try:st.json(providers.sportsdataio(resource,str(selected_date)))
            except ProviderError as e:st.error(str(e))
    st.subheader('Load normalized historical or pregame snapshot')
    st.caption('See README.md for the schema. Supply real provider observations and source provenance. Imported advanced context needs known_at; historical context without it is excluded.')
    uploaded=st.file_uploader('Snapshot JSON',type='json')
    if uploaded:
        try:
            bundle=validate_bundle(json.load(uploaded));st.session_state['bundle']=bundle
            DATA_DIR.mkdir(parents=True,exist_ok=True);save_cache('last_bundle.json',bundle)
            result=st.session_state['date_result'];result['bundle']=bundle;result['error']=None
            result['games']=bundle.get('games',result['games']);result['historical']=False
            st.success('Snapshot loaded and cached; only rows matching the selected date will display')
        except (ValueError,KeyError,TypeError) as e:st.error(str(e))
    if st.button('Build slate from BallDontLie schedule and logs'):
        games=st.session_state.get('schedule',[]);logs=st.session_state.get('logs',[])
        players={}
        for g in sorted(logs,key=lambda x:x['date']): players[str(g['player_id'])]=g
        slate=[]
        for game in games:
            tip=game.get('datetime')
            if not tip:continue
            home=game['home_team']['abbreviation'];away=game['visitor_team']['abbreviation']
            for p in players.values():
                if p['team'] in (home,away):slate.append({k:p.get(k) for k in ('player_id','player','team','position')}|{'opponent':away if p['team']==home else home,'game_id':str(game['id']),'game_time':tip})
        if slate:
            st.session_state['bundle']={'players':slate,'logs':logs,'lines':[],'contexts':{},'source':'BallDontLie; roster inferred from latest game logs'}
            st.warning('Slate assembled. Verify current roster and injury context. Lines from other providers require explicit IDs in normalized import; no fuzzy-name betting matches are made.')
        else:st.error('Import compatible schedule and game logs first; games require exact tipoff timestamps.')
    st.subheader('Import completed box scores')
    results=st.file_uploader('Final results JSON array',type='json',key='results')
    if results and st.button('Store final results'):
        try:
            data=json.load(results)
            for row in data:store.result(row)
            st.success(f'Stored {len(data)} final player box scores')
        except (ValueError,KeyError,TypeError) as e:st.error(str(e))

elif page=='Player Props':
    bundle=st.session_state.get('bundle')
    date_result=st.session_state['date_result']
    if date_result.get('games'):
        from nba.lineups import render_lineups
        render_lineups(date_result['games'],str(selected_date),date_result['loaded_at'])
    if date_result.get('historical'):
        st.subheader('Historical date: '+str(selected_date))
        if date_result['games']:
            st.dataframe(pd.DataFrame(date_result['games']).reindex(columns=['away','home','season_type','game_status']),hide_index=True)
        if date_result['actual_rows']:
            st.subheader('Completed player results')
            st.dataframe(pd.DataFrame(date_result['actual_rows']),hide_index=True)
        if date_result['saved_rows']:
            st.subheader('Saved pregame predictions')
            st.dataframe(pd.DataFrame(date_result['saved_rows']).drop(columns=['recent_stats','season_stats','context'],errors='ignore'),hide_index=True)
        else:st.info('No saved pregame predictions for this date. Actual results are not used to invent historical predictions.')
    elif not bundle:
        def open_import():st.session_state['section']='Data Sources & Import'
        st.button('Load schedule and player data',on_click=open_import)
        if date_result.get('games'):st.info('Schedule loaded, but player data is unavailable. See the source status above.')
        st.warning('No current player prop lines available. Import or configure odds provider.')
    else:
        scheduled=[g for g in bundle.get('games',[]) if slate_day(g['game_time'])==str(selected_date)]
        if scheduled:
            for source,health in bundle.get('provider_health',{}).items():
                if health.get('status','').startswith('CACHED'):
                    st.caption(source+': saved NBA data retrieved '+health['retrieved_at'])
        scope={**bundle,'players':[p for p in bundle['players'] if slate_day(p['game_time'])==str(selected_date)]}
        now=datetime.now(timezone.utc)
        rows=run(scope,now.isoformat(),calibration=store.active_calibration())
        if rows:
            store.save_automatic(rows,scope.get('source'),now.isoformat())
            st.caption('Pregame projections are saved automatically for the completed-game audit.')
        if not rows:st.info('No upcoming games in the selected slate. View saved snapshots in Completed Games Audit.')
        else:
            df=pd.DataFrame(rows)
            if any(r.get('season_type')=='Preseason' for r in rows):
                st.warning('Preseason: rotations are uncertain. Minutes use prior preseason games only; players without those observations remain N/A. Betting recommendations are disabled by the low-confidence gate.')
            st.subheader("Today's Slate Summary")
            cols=st.columns(3);cols[0].metric('Players',df.player_id.nunique());cols[1].metric('Games',df.game_id.nunique());cols[2].metric('Props with lines',int(df.line.notna().sum()))
            choices=st.columns(4)
            filters={}
            matchups=game_labels(df, scheduled)
            for col,key,label in zip(choices,['team','game_id','player','sportsbook'],['Team','Game','Player','Sportsbook']):
                filters[key]=col.multiselect(label,sorted(str(x) for x in df[key].dropna().unique()),
                    format_func=(lambda value: matchups.get(value, 'Matchup unavailable')) if key=='game_id' else str)
            stat=st.selectbox('Stat type',['All',*STATS]);minimum=st.slider('Minimum minutes projection',0,48,0)
            view=df.copy()
            for key,values in filters.items():
                if values:view=view[view[key].astype(str).isin(values)]
            if stat!='All':view=view[view.stat==STATS[stat]]
            view=view[view.projected_minutes.fillna(0)>=minimum] if 'projected_minutes' in view else view
            for label,key in [('Show only props with lines','line'),('Show only recommended plays','recommendation'),('Show only Top-3 candidates','top3_spike'),('Show Hidden Ceiling Watchlist','hidden_ceiling'),('Show injury-boost players','injury_boost')]:
                if st.checkbox(label):
                    if key=='line':view=view[view.line.notna()]
                    elif key=='recommendation':view=view[view.recommendation.str.contains('Over|Under')]
                    elif key=='top3_spike':view=view[view.top3_spike.fillna(0)>=70]
                    elif key=='injury_boost':view=view[view.get(key,pd.Series(index=view.index,dtype=float)).fillna(0)>1]
                    else:view=view[view.hidden_ceiling==True]
            from nba.watchlists import render_watchlists
            render_watchlists(st, view, df)
            st.subheader('Main Player Props Table')
            render_player_props(st, view, stat)
            if df.line.isna().all():st.warning('No current player prop lines available. Import or configure odds provider.')
            st.caption('Null cells mean N/A. Missing tracking inputs lower confidence; opportunity and matchup remain unavailable until supported by observed context.')
            if st.button('Save immutable pregame snapshot'):
                try:identifier=store.save({'rows':rows,'source':scope.get('source'),'feature_cutoff':now.isoformat()});st.success('Saved '+identifier)
                except ValueError as e:st.error(str(e))
            st.download_button('Export projections',json.dumps(rows,indent=2),file_name='nba_projections.json')
else:
    from nba.review import render_review
    render_review(st, store, providers, selected_date, page)

with st.expander('Data Source Health Panel',expanded=False):
    for name,key in KEYS.items():
        status=providers.health.get(name,{'status':'Configured — not yet verified' if providers.configured(key) else 'UNAVAILABLE — missing API key','required_key':key})
        st.write(name,status)
    st.write('NBA.com',providers.health.get('NBA.com',{'status':'Not checked'}))
    for source in ('NBA roster','ESPN schedule'):
        st.write(source,providers.health.get(source,{'status':'Not checked'}))
    st.caption('Line snapshots older than six hours are stale and cannot generate a recommendation. A configured key is not proof of a successful sync.')
