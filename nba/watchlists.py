"""Readable research lists with explicit availability gates; never invent betting inputs."""
import pandas as pd
from .model import STATS, THRESHOLDS

LABELS={v:k for k,v in STATS.items()}


def unique_props(view):
    return view.drop_duplicates(['game_id','player_id','stat']).copy()


def readable(rows, columns):
    table=rows.reindex(columns=columns).rename(columns=columns).copy()
    if 'Stat' in table:table['Stat']=table.Stat.map(LABELS)
    return table


def leader_rows(view):
    rows=unique_props(view).dropna(subset=['projection'])
    rows=rows[rows.get('injury_status',pd.Series('Unknown',index=rows.index)).isin(['Out','Doubtful'])==False]
    rows=rows.sort_values(['stat','projection'],ascending=[True,False])
    rows['rank']=rows.groupby('stat').cumcount()+1
    return rows[rows['rank']<=10]


def historical_ceiling_rows(view):
    if 'season_high' not in view:return view.iloc[:0].copy()
    rows=unique_props(view).dropna(subset=['projection','season_high'])
    records=[]
    for row in rows.to_dict('records'):
        threshold=THRESHOLDS[row['stat']][1]
        hits=row.get('threshold_hit_rates') or {}
        rate=hits.get(str(threshold))
        if row.get('projection_percentile') is None or row['projection_percentile']>=80:continue
        if row['season_high']<threshold or rate is None or rate<=0:continue
        if row.get('injury_status') in ('Out','Doubtful'):continue
        records.append({**row,'threshold':f'{threshold}+','historical_hit_rate':rate*100})
    if not records:return rows.iloc[:0]
    return pd.DataFrame(records).sort_values('historical_hit_rate',ascending=False).groupby('stat',sort=False).head(5)


def render_watchlists(st, view, full):
    common={'player':'Player','team':'Team','stat':'Stat','projection':'Projected','confidence':'Confidence'}
    empty=view.empty
    with st.expander('Top Prop Recommendations'):
        plays=view[view.recommendation.fillna('').str.contains('Over|Under')]
        if not plays.empty:
            st.dataframe(readable(plays,{**common,'line':'Line','edge':'Edge','recommendation':'Pick','sportsbook':'Book'}),hide_index=True,width='stretch')
        elif empty:st.info('No players match your filters. Clear filters to see this slate.')
        else:
            st.info('No supported Over/Under recommendations for this selection.')
            if view.line.isna().all():st.write('• No sportsbook lines loaded. Configure ODDS_API_KEY or import real, timestamped prop lines in Data Sources & Import.')
            else:st.write('• Available props do not pass the model’s confidence, minutes, injury-status and opportunity gates. They remain Pass / No Play.')
            st.caption('A high projected total or a leader ranking alone is not a betting recommendation.')
    with st.expander('Top-3 Candidate Rankings by Stat'):
        leaders=leader_rows(view)
        st.caption('Ranked by projected total within the filtered slate. Rank 1–3 identifies projection leaders; it is not a calibrated probability of finishing Top 3.')
        if leaders.empty:st.info('No supported projections match your filters. Players without enough prior games or preseason minutes remain N/A.')
        else:
            if leaders.top3_spike.isna().any():
                st.info('Full Top-3 Spike Scores need observed opportunity and matchup inputs. Projection-based rankings are available below; missing scores remain N/A.')
            for stat in leaders.stat.unique():
                st.markdown('**'+LABELS[stat]+'**')
                st.dataframe(readable(leaders[leaders.stat==stat],{'rank':'Rank',**common,'top3_spike':'Spike score'}),hide_index=True,width='stretch')
    with st.expander('Hidden Ceiling Watchlist'):
        qualified=view[view.hidden_ceiling==True]
        if not qualified.empty:
            st.dataframe(readable(unique_props(qualified),{**common,'opportunity':'Opportunity','ceiling':'Ceiling','season_high':'History high','last10_high':'Last 10 high'}),hide_index=True,width='stretch')
        else:
            st.info('No fully qualified Hidden Ceiling players in this selection.')
            if not empty and view.opportunity.isna().all():st.caption('Observed opportunity scores are unavailable, so the model cannot verify the required opportunity threshold.')
            research=historical_ceiling_rows(view)
            if not research.empty:
                st.markdown('**Historical ceiling research — not qualified picks**')
                st.caption('Below the elite projection tier, with real prior games reaching the shown threshold. Historical hit rates are not tonight’s probabilities; opportunity and current role still need verification.')
                st.dataframe(readable(research,{'player':'Player','stat':'Stat','projection':'Projected','season_high':'History high','last10_high':'Last 10 high','threshold':'Threshold','historical_hit_rate':'Historical hit %'}),hide_index=True,width='stretch')
            else:st.caption('No eligible historical ceiling observations for the current selection.')
    with st.expander('Injury Boost Watchlist'):
        boosts=view[view.get('injury_boost',pd.Series(index=view.index,dtype=float)).fillna(0)>1]
        if not boosts.empty:
            st.dataframe(readable(unique_props(boosts),{**common,'injury_boost':'Usage multiplier','injury_status':'Status'}),hide_index=True,width='stretch')
        else:
            st.info('No verified injury-based usage boosts are available for this selection.')
            st.caption('A teammate injury or projected starting spot does not establish a numeric usage boost. This list requires observed role/usage adjustments; no boost is assumed.')
            statuses=view[view.injury_status.isin(['Out','Doubtful','Questionable','Probable'])].drop_duplicates(['game_id','player_id'])
            if not statuses.empty:
                st.markdown('**Reported player statuses — not boost predictions**')
                st.dataframe(readable(statuses,{'player':'Player','team':'Team','injury_status':'Status'}),hide_index=True,width='stretch')
            else:st.caption('No actionable injury statuses loaded. The starting-lineup cards are a separate source and do not automatically establish injury boosts.')
    with st.expander('Role / Minutes Volatility Watchlist'):
        risky=view[view.role_security.fillna(100)<60].drop_duplicates(['game_id','player_id'])
        if risky.empty:st.info('No players with a measured role-security score below 60 match your filters. Missing scores are not treated as safe.')
        else:
            st.dataframe(readable(risky,{'player':'Player','team':'Team','opponent':'Opponent','projected_minutes':'Minutes','role_security':'Role security','injury_status':'Status'}),hide_index=True,width='stretch')
    st.caption(f"Data coverage for this selection: {view.projection.notna().sum()} projected props · {view.line.notna().sum()} lines · {view.opportunity.notna().sum()} opportunity scores · {view.matchup.notna().sum()} matchup scores. Missing inputs are never filled with invented scores.")
