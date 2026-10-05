"""Compact player overview; sportsbook duplicates never add to projections."""
import pandas as pd
from nba.model import STATS


def game_labels(rows, games):
    """Human-readable labels while keeping provider IDs as filter values."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from nba.schedule import SLATE_TZ
    names = {r['team']: r.get('team_name') or r['team'] for r in rows.to_dict('records')}
    schedule = {str(g['game_id']): g for g in games}
    labels = {}
    for game_id, group in rows.groupby('game_id', sort=False):
        first = group.iloc[0]
        game = schedule.get(str(game_id), {})
        if game.get('away') and game.get('home'):
            matchup = f"{names.get(game['away'], game['away'])} at {names.get(game['home'], game['home'])}"
        else:
            matchup = f"{names.get(first['team'], first['team'])} vs {names.get(first['opponent'], first['opponent'])}"
        try:
            tip = datetime.fromisoformat(str(game.get('game_time') or first.get('game_time')).replace('Z', '+00:00'))
            when = tip.astimezone(ZoneInfo(SLATE_TZ)).strftime('%b %d · %I:%M %p ET') if tip.tzinfo else 'Tipoff unavailable'
        except (ValueError, TypeError):
            when = 'Tipoff unavailable'
        labels[str(game_id)] = f'{matchup} · {when}'
    return labels


def player_overview(rows, stat='All'):
    labels = STATS if stat == 'All' else {stat: STATS[stat]}
    columns = ['Player', 'Matchup', 'Minutes', *labels]
    records, identities = [], []
    for identity, group in rows.groupby(['player_id', 'game_id'], sort=False, dropna=False):
        first = group.iloc[0]
        record = {'Player': first['player'], 'Matchup': f"{first['team']} vs {first['opponent']}",
                  'Minutes': first.get('projected_minutes')}
        for label, code in labels.items():
            values = group.loc[group.stat == code, 'projection']
            record[label] = values.iloc[0] if len(values) else None
        records.append(record)
        identities.append(identity)
    return pd.DataFrame(records, columns=columns), identities


def render_player_props(st, rows, stat='All'):
    overview, identities = player_overview(rows, stat)
    if overview.empty:
        st.info('No players match these filters.')
        return
    st.caption('One row per player per game. Numbers are projected totals. A dash means unavailable or excluded by your filters. Select a player below for betting lines and model details.')
    st.dataframe(overview, hide_index=True, width='stretch', column_config={
        'Player': st.column_config.TextColumn(width='medium'),
        'Matchup': st.column_config.TextColumn(width='small'),
        **{name: st.column_config.NumberColumn(format='%.1f', width='small') for name in overview.columns[2:]},
    })
    labels = {identity: f"{overview.iloc[i]['Player']} · {overview.iloc[i]['Matchup']}" for i, identity in enumerate(identities)}
    selected = st.selectbox('Player details', identities, format_func=labels.get)
    detail = rows[(rows.player_id == selected[0]) & (rows.game_id == selected[1])].copy()
    detail['Stat'] = detail.stat.map({v: k for k, v in STATS.items()})
    st.caption('Confidence is scored out of 100. Separate sportsbook offers appear only in this detail view.')
    betting = {'Stat':'Stat', 'projection':'Projection', 'line':'Line', 'edge':'Edge',
               'confidence':'Confidence', 'recommendation':'Recommendation', 'sportsbook':'Book'}
    st.dataframe(detail.reindex(columns=betting).rename(columns=betting), hide_index=True, width='stretch',
                 column_config={k: st.column_config.NumberColumn(format='%.2f') for k in ['Projection','Line','Edge']})
    with st.expander('Opportunity, matchup and ceiling'):
        context = {'Stat':'Stat', 'role_security':'Role security', 'opportunity':'Opportunity',
                   'matchup':'Matchup', 'ceiling':'Ceiling', 'top3_spike':'Top-3 score', 'recent_form':'Recent form'}
        st.dataframe(detail.drop_duplicates('stat').reindex(columns=context).rename(columns=context), hide_index=True, width='stretch')
    with st.expander('Full stat details, odds and missing inputs'):
        code = st.selectbox('Detail stat', list(detail.stat.unique()), format_func=lambda v: {v:k for k,v in STATS.items()}.get(v,v))
        for _, row in detail[detail.stat == code].iterrows():
            st.markdown('**'+str(row.get('sportsbook') or 'No sportsbook line')+'**')
            # Vertical layout retains every model field without a wide scrolling table.
            fields = []
            for key, value in row.items():
                if key in ('player_id','team_id','game_id','Stat'): continue
                if isinstance(value, (dict,list)):
                    import json
                    value = json.dumps(value, default=str)
                elif value is None or pd.isna(value): value = 'N/A'
                fields.append({'Detail': key.replace('_',' ').capitalize(), 'Value': str(value)})
            st.dataframe(pd.DataFrame(fields), hide_index=True, width='stretch')
