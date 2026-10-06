"""Completed results, immutable prediction audits, and validated retraining UI."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from .audit import audit, metrics, capture
from .model import STATS
from .schedule import SLATE_TZ, slate_day
from .providers import ProviderError
from .training import reconstruct, validate_corrections


def render_review(st, store, providers, selected_date, page):
    from .sync import load_date
    st.subheader(page)
    today=datetime.now(ZoneInfo(SLATE_TZ)).date()
    day=min(selected_date,today-timedelta(days=1))
    dates={str(day)}
    # Fetch results for all outstanding saved games, not only the selected date.
    results=store.results()
    for snap in store.snapshots():
        for r in snap['rows']:
            d=slate_day(r['game_time'])
            if d<str(today) and (str(r['game_id']),str(r['player_id'])) not in results:dates.add(d)
    cache=st.session_state.setdefault('review_sync',{})
    if st.button('Refresh completed results'):
        cache.clear()
        if hasattr(providers,'_date_import_cache'):providers._date_import_cache.clear()
    for date in sorted(dates):
        cached=cache.get(date)
        if not cached or (datetime.now(timezone.utc)-datetime.fromisoformat(cached['at'])).total_seconds()>600:
            with st.spinner('Loading final box scores for '+date+'…'):
                try:
                    loaded=load_date(providers,date,snapshots=store.snapshots())
                    for actual in loaded['actual_rows']:store.result(actual)
                    cache[date]={'at':datetime.now(timezone.utc).isoformat(),'warnings':loaded.get('warnings',[]),'count':len(loaded['actual_rows'])}
                except (ProviderError, ValueError, KeyError, OSError) as e:
                    cache[date]={'at':datetime.now(timezone.utc).isoformat(),'warnings':[str(e)],'count':0}
        for warning in cache[date]['warnings']:st.caption(date+': '+warning)
    snapshots=store.snapshots();results=store.results();rows=audit(snapshots,results)
    cols=st.columns(3)
    cols[0].metric('Saved pregame runs',len(snapshots));cols[1].metric('Final player box scores',len(results));cols[2].metric('Matched prop predictions',len(rows))
    st.caption('Only matched final participant box scores are scored; DNPs are excluded. Final results sync automatically. Audits use the latest saved pregame prediction for each player/stat/book. Dates use Eastern Time.')
    default_start=day-timedelta(days=30)
    selected=st.date_input('Date range',(default_start,day),key='review_dates')
    start,end=(str(selected[0]),str(selected[1])) if isinstance(selected,tuple) and len(selected)==2 else (str(default_start),str(day))
    filtered=[r for r in rows if start<=slate_day(r['game_time'])<=end]
    if rows:
        stats=st.multiselect('Stat type',list(STATS))
        players=st.multiselect('Player',sorted({r['player'] for r in rows}))
        teams=st.multiselect('Team',sorted({r['team'] for r in rows}))
        recs=st.multiselect('Recommendation',sorted({r['recommendation'] for r in rows}))
        confidence=st.slider('Confidence range',0,100,(0,100))
        hidden=st.checkbox('Hidden ceiling only')
        filtered=[r for r in filtered if (not stats or r['stat'] in [STATS[s] for s in stats]) and
            (not players or r['player'] in players) and (not teams or r['team'] in teams) and
            (not recs or r['recommendation'] in recs) and confidence[0]<=r.get('confidence',0)<=confidence[1] and
            (not hidden or r.get('hidden_ceiling'))]
    if filtered:
        st.dataframe(pd.DataFrame([{'Stat':label,**metrics([r for r in filtered if r['stat']==code])} for label,code in STATS.items()]),hide_index=True)
        columns={'player':'Player','team':'Team','stat':'Stat','projection':'Projected','actual':'Actual','projection_error':'Error',
                 'line':'Line','ou_result':'O/U result','recommendation_result':'Bet result'}
        table=pd.DataFrame(filtered).reindex(columns=columns).rename(columns=columns)
        table['Stat']=table.Stat.map({v:k for k,v in STATS.items()})
        st.dataframe(table,hide_index=True,width='stretch')
        with st.expander('Miss drivers and complete audit records'):
            st.dataframe(pd.DataFrame(filtered).drop(columns=['recent_stats','season_stats','context'],errors='ignore'),hide_index=True)
        with st.expander('Leader capture comparison'):
            st.caption('Only audited players are counted; this is not full-slate coverage.')
            st.dataframe(pd.DataFrame(capture(filtered)),hide_index=True)
        st.download_button('Export audit CSV',pd.DataFrame(filtered).to_csv(index=False),file_name='nba_audit.csv')
    else:
        st.info('No matched pregame predictions in this date range. Older games cannot be audited if predictions were never saved. New available projections now save automatically before tipoff.')
    actuals=[r for r in results.values() if (r.get('game_time') or r.get('date')) and start<=slate_day(r.get('game_time') or r['date'])<=end]
    with st.expander('Completed box scores (actual results, not prediction audits)',expanded=not filtered):
        if actuals:
            cols={'player':'Player','team':'Team','opponent':'Opponent','min':'Minutes',**{v:k for k,v in STATS.items()}}
            st.dataframe(pd.DataFrame(actuals).reindex(columns=cols).rename(columns=cols),hide_index=True,width='stretch')
        else:st.info('No final box scores available in this range. Select a completed game date or refresh after the data source updates.')
    if page=='NBA Model Retraining':
        render_training(st,store,providers,filtered,today)
    with st.expander('Back up audit history'):
        st.caption('Streamlit local storage can reset on redeploy. Download history to retain a copy.')
        st.download_button('Download audit backup',json.dumps({'snapshots':snapshots,'results':list(results.values()),'artifacts':store.artifacts()},indent=2),file_name='nba_audit_backup.json')


def render_training(st,store,providers,rows,today):
    st.subheader('Train and validate model corrections')
    source=st.radio('Training data',['Real historical game logs','Saved prediction audits'])
    year=today.year-(today.month<10)
    season=st.text_input('Historical regular season',f'{year-1}-{str(year)[-2:]}') if source=='Real historical game logs' else None
    st.caption('Historical training reconstructs baselines from earlier games only, for actual participants. It cannot recover historical injuries, sportsbook lines, or a complete pregame roster. It is separate from the live audit.')
    if st.button('Train and validate'):
        try:
            with st.spinner('Training on earlier dates and testing on later dates…'):
                training=rows
                if season:
                    logs=providers.nba_logs(season,'Regular Season')
                    logs=[r for r in logs if r['date'][:10]<str(today)]
                    if not logs:raise ValueError('No completed regular-season logs available for this season.')
                    end=max(r['date'][:10] for r in logs)
                    start=(datetime.fromisoformat(end)-timedelta(days=60)).date().isoformat()
                    training=reconstruct(logs,start,end)
                artifact=validate_corrections(training,datetime.now(timezone.utc).isoformat())
                artifact['training_source']=source
                identifier=store.artifact(artifact)
                st.success('Training and chronological validation completed. Candidate saved: '+identifier)
        except (ProviderError,ValueError,KeyError) as e:st.error(str(e))
    candidates=[a for a in store.artifacts() if a.get('version')=='stat-bias-2' and a.get('status')=='candidate']
    if candidates:
        latest=candidates[-1]
        st.write('Latest training run: '+latest['created'])
        st.dataframe(pd.DataFrame(latest['validation']),hide_index=True,width='stretch')
        st.caption('Only corrections that reduced error on later, held-out dates can be activated. They affect future regular-season projections; saved predictions and confidence scores remain unchanged.')
        if latest['corrections']:
            if st.button('Activate validated corrections'):
                store.artifact({k:v for k,v in latest.items() if k not in ('id','created')}|{'status':'active','candidate_id':latest['id']})
                st.success('Validated corrections activated for future regular-season projections.')
        else:st.info('No correction improved validation accuracy. The current model is retained.')
    active=store.active_calibration()
    if active:st.success('Active calibration: '+active['created']+' · '+str(len(active['corrections']))+' stat corrections')
    else:st.info('No calibration is active yet. Run training to measure whether corrections improve later-game predictions.')
