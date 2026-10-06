"""Game-specific starters when explicitly reported; otherwise labeled depth estimates."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo
import streamlit as st
from .errors import ProviderError
from .providers import Providers
from .schedule import SLATE_TZ, slate_day

POSITIONS=('pg','sg','sf','pf','c')


def projected_five(payload):
    charts=payload.get('depthchart',[])
    positions=charts[0].get('positions',{}) if charts else {}
    players=[];seen=set()
    for slot in POSITIONS:
        for athlete in positions.get(slot,{}).get('athletes',[]):
            # Conservative estimate, not an injury diagnosis or game confirmation.
            if athlete.get('injuries') or athlete.get('id') in seen:continue
            if not athlete.get('displayName'):continue
            seen.add(athlete.get('id'))
            players.append({'name':athlete['displayName'],'position':slot.upper()})
            break
    return players if len(players)==5 else []


def load_game_lineups(game, now=None, provider=None):
    now=now or datetime.now(timezone.utc)
    result={'checked_at':now.isoformat(),'teams':{},'error':None}
    provider=provider or Providers()
    try:
        if not str(game['game_id']).startswith('espn:'):raise ProviderError('Starting lineup source unavailable for this game.')
        payload=provider.get('ESPN lineups','https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary',{'event':game['game_id'].split(':')[1]})
        competitions=payload.get('header',{}).get('competitions',[])
        if not competitions:raise ProviderError('Game lineup report is not published yet.')
        competition=competitions[0]
        result['game_status']=competition.get('status',{}).get('type',{}).get('description',game.get('game_status',''))
        completed=competition.get('status',{}).get('type',{}).get('completed',False)
        boxes={str(t['team']['id']):t for t in payload.get('boxscore',{}).get('players',[])}
        for competitor in competition.get('competitors',[]):
            side=competitor.get('homeAway')
            if side not in ('home','away'):continue
            team=competitor['team'];team_id=str(team['id'])
            starters={}
            for group in boxes.get(team_id,{}).get('statistics',[]):
                for row in group.get('athletes',[]):
                    athlete=row.get('athlete',{})
                    if row.get('starter') is True and athlete.get('displayName'):
                        starters[str(athlete['id'])]={'name':athlete['displayName'],'position':athlete.get('position',{}).get('abbreviation','')}
            data={'name':team.get('displayName',game[side]),'status':'Unavailable','players':[],
                  'note':'Starting five not published.','source':'ESPN game report'}
            if len(starters)==5:
                data.update(status='Confirmed',players=list(starters.values()),note='Actual starters · final box score' if completed else 'Starters explicitly listed in the game report')
            elif not completed and slate_day(game['game_time'])>=now.astimezone(ZoneInfo(SLATE_TZ)).date().isoformat():
                try:
                    depth=provider.get('ESPN depth charts',f'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/depthcharts')
                    players=projected_five(depth)
                    if players:data.update(status='Projected',players=players,source='ESPN depth chart',note='Depth-chart estimate; injury-flagged players skipped. Not a confirmed game lineup.')
                except ProviderError:data['note']='Depth chart unavailable. No starting five inferred.'
            result['teams'][side]=data
    except (ProviderError,KeyError,TypeError,ValueError) as e:
        result['error']=str(e) if isinstance(e,ProviderError) else 'Lineup source returned an incomplete report.'
    return result


@st.fragment
def render_lineups(games, date, revision):
    st.subheader('Game schedule & starting five')
    st.caption('Projected = current depth-chart estimate. Confirmed = five starters explicitly listed by the game source. Preseason rotations may differ substantially.')
    cache=st.session_state.setdefault('lineup_cache',{})
    key=(str(date),revision)
    refresh=st.button('Refresh starting lineups',key='refresh_lineups',help='Checks lineups only; player projections and main slate imports stay unchanged.')
    if refresh or key not in cache:
        with st.spinner('Checking starting lineups…'):
            with ThreadPoolExecutor(max_workers=4) as pool:
                values=list(pool.map(load_game_lineups,games))
            cache.clear()
            cache[key]={g['game_id']:v for g,v in zip(games,values)}
    checked=cache[key]
    if checked:
        stamp=datetime.fromisoformat(next(iter(checked.values()))['checked_at']).astimezone(ZoneInfo(SLATE_TZ))
        st.caption('Last checked '+stamp.strftime('%b %d, %I:%M:%S %p ET')+' · Source: ESPN game reports / depth charts')
    columns=st.columns(2)
    for index,game in enumerate(sorted(games,key=lambda g:g['game_time'])):
        data=checked[game['game_id']]
        tip=datetime.fromisoformat(game['game_time'].replace('Z','+00:00')).astimezone(ZoneInfo(SLATE_TZ)).strftime('%I:%M %p ET')
        with columns[index%2]:
            with st.container(border=True):
                st.markdown('#### '+escape(game['away'])+' at '+escape(game['home']))
                st.caption(tip+' · '+game.get('season_type','')+' · '+data.get('game_status',game.get('game_status','')))
                if data['error']:st.info(data['error'])
                sides=st.columns(2)
                for col,side in zip(sides,('away','home')):
                    team=data['teams'].get(side,{'name':game[side],'status':'Unavailable','players':[],'note':'Starting five not published.'})
                    with col:
                        st.markdown('**'+escape(team['name'])+'**')
                        color={'Confirmed':'#166534','Projected':'#92400e','Unavailable':'#475569'}[team['status']]
                        st.markdown(f'<span style="background:{color};color:white;padding:3px 9px;border-radius:12px;font-size:12px">{team["status"]}</span>',unsafe_allow_html=True)
                        for player in team['players']:
                            st.markdown(f'<div style="padding:5px 0;border-bottom:1px solid #94a3b833"><span style="opacity:.7;font-size:12px">{escape(player["position"])}</span> {escape(player["name"])}</div>',unsafe_allow_html=True)
                        if not team['players']:st.caption('N/A — lineup unavailable')
                        st.caption(team['note'])
