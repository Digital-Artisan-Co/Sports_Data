import json
import os
import hmac
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import pandas as pd
import streamlit as st
from nba.model import STATS
from nba.providers import Providers, ProviderError, KEYS
from nba.storage import Store
from nba.runtime import DATA_DIR, save_cache
from nba.slate import build_nba_slate, add_preseason_context
from nba.schedule import slate_day, SLATE_TZ
from zoneinfo import ZoneInfo
from nba.pipeline import run, validate_bundle
from nba.audit import audit, metrics, capture, train_bias

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
store=Store(); providers=st.session_state.setdefault('providers',Providers(prefer_snapshots=True))
page=st.sidebar.radio('Section',['Player Props','Completed Games Audit','NBA Model Retraining','Historical Backtesting','Data Sources & Import'],key='section')
selected_date=st.sidebar.date_input('Date',datetime.now(ZoneInfo(SLATE_TZ)).date(),key='slate_date')
cutoff=datetime.combine(selected_date,time.min,tzinfo=timezone.utc)
st.sidebar.caption('Slate dates use Eastern Time (America/New_York), including late games after midnight UTC. Stored timestamps remain UTC.')

if page=='Data Sources & Import':
    st.subheader('Data Source Health Panel')
    for provider,key in KEYS.items():
        st.write(provider, providers.health.get(provider,{'status':'Configured — not yet verified' if os.getenv(key) else 'UNAVAILABLE — missing API key','required_key':key}))
    st.write('NBA.com',providers.health.get('NBA.com',{'status':'Not yet checked; no API key required'}))
    st.info('Provider subscription tiers may restrict injuries, advanced statistics, or prop markets. Raw imports retain provider IDs; cross-provider player/game mappings require explicit matching.')
    st.subheader('Free NBA workflow — preseason included')
    st.caption('ESPN schedules include preseason games. NBA.com supplies current rosters and historical logs. The build button imports baseline logs automatically if none are cached. No API key is required for this workflow. Preseason projections require observed preseason minutes; otherwise they remain N/A.')
    if st.session_state.get('no_games_date')==str(selected_date):
        st.info('No games returned for this date. Choose an available date below, then build the slate.')
    if st.session_state.get('available_dates'):
        candidate=st.selectbox('Upcoming dates returned by the schedule provider',st.session_state['available_dates'])
        def choose_date():
            st.session_state['slate_date']=date.fromisoformat(candidate)
        st.button('Use this slate date',on_click=choose_date)
    if st.button('Build free NBA slate'):
        try:
            logs=st.session_state.get('nba_logs',[])
            if not logs and (DATA_DIR/'nba_logs.json').exists():logs=json.loads((DATA_DIR/'nba_logs.json').read_text())
            if not logs:
                year=selected_date.year if selected_date.month>=10 else selected_date.year-1
                logs=providers.nba_logs(f'{year-1}-{str(year)[-2:]}')
                save_cache('nba_logs.json',logs)
            with st.spinner('Loading NBA schedule and current rosters…'):
                year=selected_date.year if selected_date.month>=10 else selected_date.year-1
                roster=providers.nba_roster(f'{year}-{str(year+1)[-2:]}')
                games=providers.free_schedule(str(selected_date),roster)
                if not games:
                    st.info('The schedule provider returned no games for this date. This is not an API-key error.')
                    dates=providers.upcoming_dates(str(selected_date),roster)
                    st.session_state['available_dates']=dates
                    if dates:
                        st.session_state['no_games_date']=str(selected_date)
                        st.rerun()
                    else:st.info('No upcoming games returned within 45 days.')
                    st.stop()
                bundle=build_nba_slate(games,roster,logs)
                if any(g.get('season_type')=='Preseason' for g in games):
                    try:preseason_logs=providers.nba_logs(f'{year}-{str(year+1)[-2:]}','Pre Season')
                    except ProviderError:
                        preseason_logs=[]
                        st.warning('Preseason logs unavailable. Players are listed, but preseason projections remain N/A.')
                    bundle=add_preseason_context(bundle,preseason_logs,datetime.now(timezone.utc).isoformat())
                if not bundle['players']:raise ValueError('No current roster players matched this schedule.')
                st.session_state['bundle']=bundle
                DATA_DIR.mkdir(parents=True,exist_ok=True)
                bundle['provider_health']=dict(providers.health)
                save_cache('last_bundle.json',bundle)
            st.success(f"Built {len(bundle['players'])} player-game entries. Open Player Props in the sidebar.")
            st.caption(bundle['source'])
            for source,health in providers.health.items():
                if health.get('status','').startswith('CACHED'):
                    st.info(source+': using real saved NBA data retrieved '+health['retrieved_at']+' ('+str(health['age_hours'])+' hours old).')
            st.info('Baseline projections only. Injuries, advanced tracking and sportsbook lines are not supplied by this import; recommendations remain gated.')
        except (ProviderError,ValueError,KeyError) as e:st.error(str(e))
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
                st.success(f"Imported {len(logs)} records. Now click Build free NBA slate above.")
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
            DATA_DIR.mkdir(parents=True,exist_ok=True);save_cache('last_bundle.json',bundle);st.success('Snapshot loaded and cached')
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
    if not bundle and (DATA_DIR/'last_bundle.json').exists():bundle=json.loads((DATA_DIR/'last_bundle.json').read_text())
    if not bundle:
        def open_import():st.session_state['section']='Data Sources & Import'
        st.button('Load schedule and player data',on_click=open_import)
        st.info('No real player data loaded. Configure a provider or import a saved snapshot in Data Sources & Import.')
        st.warning('No current player prop lines available. Import or configure odds provider.')
    else:
        scheduled=[g for g in bundle.get('games',[]) if slate_day(g['game_time'])==str(selected_date)]
        if scheduled:
            for source,health in bundle.get('provider_health',{}).items():
                if health.get('status','').startswith('CACHED'):
                    st.caption(source+': saved NBA data retrieved '+health['retrieved_at'])
            st.subheader('Game schedule')
            st.dataframe(pd.DataFrame([{'Away':g['away'],'Home':g['home'],'Season':g.get('season_type','Unknown'),
                'Tipoff (Eastern)':datetime.fromisoformat(g['game_time'].replace('Z','+00:00')).astimezone(ZoneInfo(SLATE_TZ)).strftime('%I:%M %p'),
                'Status':g.get('game_status','Unknown')} for g in scheduled]),hide_index=True)
        scope={**bundle,'players':[p for p in bundle['players'] if slate_day(p['game_time'])==str(selected_date)]}
        now=datetime.now(timezone.utc)
        rows=run(scope,now.isoformat())
        if not rows:st.info('No upcoming games in the selected slate. View saved snapshots in Completed Games Audit.')
        else:
            df=pd.DataFrame(rows)
            if any(r.get('season_type')=='Preseason' for r in rows):
                st.warning('Preseason: rotations are uncertain. Minutes use prior preseason games only; players without those observations remain N/A. Betting recommendations are disabled by the low-confidence gate.')
            st.subheader("Today's Slate Summary")
            cols=st.columns(3);cols[0].metric('Players',df.player_id.nunique());cols[1].metric('Games',df.game_id.nunique());cols[2].metric('Props with lines',int(df.line.notna().sum()))
            choices=st.columns(4)
            filters={}
            for col,key,label in zip(choices,['team','game_id','player','sportsbook'],['Team','Game','Player','Sportsbook']):
                filters[key]=col.multiselect(label,sorted(str(x) for x in df[key].dropna().unique()))
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
            for title,subset in [('Top Prop Recommendations',view[view.recommendation.str.contains('Over|Under')]),('Top-3 Candidate Rankings by Stat',view.sort_values('top3_spike',ascending=False)),('Hidden Ceiling Watchlist',view[view.hidden_ceiling==True]),('Injury Boost Watchlist',view[view.get('injury_boost',pd.Series(index=view.index,dtype=float)).fillna(0)>1]),('Role / Minutes Volatility Watchlist',view[view.get('role_security',pd.Series(index=view.index,dtype=float)).fillna(100)<60])]:
                with st.expander(title):st.dataframe(subset.drop(columns=['recent_stats','season_stats','context'],errors='ignore'),hide_index=True)
            st.subheader('Main Player Props Table')
            st.dataframe(view.drop(columns=['recent_stats','season_stats','context'],errors='ignore'),hide_index=True)
            if df.line.isna().all():st.warning('No current player prop lines available. Import or configure odds provider.')
            st.caption('Null cells mean N/A. Missing tracking inputs lower confidence; opportunity and matchup remain unavailable until supported by observed context.')
            if st.button('Save immutable pregame snapshot'):
                try:identifier=store.save({'rows':rows,'source':scope.get('source'),'feature_cutoff':now.isoformat()});st.success('Saved '+identifier)
                except ValueError as e:st.error(str(e))
            st.download_button('Export projections',json.dumps(rows,indent=2),file_name='nba_projections.json')
else:
    rows=audit(store.snapshots(),store.results())
    st.subheader(page)
    if not rows:st.info('No matched saved predictions and final box scores. Import real data and save a pregame run first.')
    else:
        df=pd.DataFrame(rows)
        dates=st.date_input('Date range',(date.today()-timedelta(days=90),date.today()))
        if isinstance(dates,tuple) and len(dates)==2:df=df[(df.game_time.str[:10]>=str(dates[0]))&(df.game_time.str[:10]<=str(dates[1]))]
        for key in ['stat','player','team','recommendation']:
            values=st.multiselect(key,sorted(df[key].dropna().unique()))
            if values:df=df[df[key].isin(values)]
        confidence=st.slider('Confidence range',0,100,(0,100));df=df[df.confidence.between(*confidence)]
        if st.checkbox('Hidden ceiling only'):df=df[df.hidden_ceiling==True]
        filtered=df.to_dict('records')
        st.dataframe(pd.DataFrame([{'stat':stat,**metrics([r for r in filtered if r['stat']==stat])} for stat in STATS.values()]),hide_index=True)
        st.dataframe(df.drop(columns=['recent_stats','season_stats','context'],errors='ignore'),hide_index=True)
        st.subheader('Leader capture comparison')
        st.caption('Capture measures only the audited snapshot population; incomplete slate coverage cannot establish actual slate-wide leaders.')
        st.dataframe(pd.DataFrame(capture(filtered)),hide_index=True)
        if page=='NBA Model Retraining':
            st.subheader('Calibration diagnostics')
            for field in ['confidence','edge','line','top3_spike']:
                if field not in df:continue
                bins=pd.cut(df[field],10,duplicates='drop')
                table=df.groupby(bins,observed=True).agg(count=('projection_error','size'),bias=('projection_error','mean'),MAE=('projection_error',lambda x:x.abs().mean()))
                st.write(field);st.dataframe(table)
            st.warning('Bias training produces a versioned candidate only. It does not activate unvalidated coefficients.')
            if st.button('Train player/stat bias candidate'):
                artifact=train_bias(filtered,datetime.now(timezone.utc).isoformat());identifier=store.artifact(artifact);st.json(artifact);st.success('Saved candidate '+identifier)
        elif page=='Historical Backtesting':
            st.info('Snapshot replay compares immutable pregame predictions to completed results. No present-day injuries or odds are substituted. New walk-forward reconstruction requires historical feature snapshots.')
            st.download_button('Export audited backtest',df.to_csv(index=False),file_name='nba_backtest.csv')

with st.expander('Data Source Health Panel',expanded=False):
    for name,key in KEYS.items():
        status=providers.health.get(name,{'status':'Configured — not yet verified' if os.getenv(key) else 'UNAVAILABLE — missing API key','required_key':key})
        st.write(name,status)
    st.write('NBA.com',providers.health.get('NBA.com',{'status':'Not checked'}))
    for source in ('NBA roster','ESPN schedule'):
        st.write(source,providers.health.get(source,{'status':'Not checked'}))
    st.caption('Line snapshots older than six hours are stale and cannot generate a recommendation. A configured key is not proof of a successful sync.')
