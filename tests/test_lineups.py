from datetime import datetime,timezone
from nba.lineups import projected_five,load_game_lineups,POSITIONS


def depth():
    return {'depthchart':[{'positions':{p:{'athletes':[{'id':str(i),'displayName':'Fixture '+p}]} for i,p in enumerate(POSITIONS)}}]}


def test_estimates_require_five_unique_uninjured_players():
    data=depth()
    assert len(projected_five(data))==5
    data['depthchart'][0]['positions']['pg']['athletes'][0]['injuries']=[{'status':'Out'}]
    assert projected_five(data)==[]


def test_explicit_confirmed_starters_take_priority_and_history_never_uses_current_depth():
    class Provider:
        def __init__(self,starters):self.starters=starters;self.calls=[]
        def get(self,source,url,params=None):
            self.calls.append(source)
            if source=='ESPN depth charts':return depth()
            return {'header':{'competitions':[{'competitors':[{'homeAway':'home','team':{'id':'1','displayName':'Team'}}]}]},
                'boxscore':{'players':[{'team':{'id':'1'},'statistics':[{'athletes':[
                    {'starter':self.starters,'athlete':{'id':str(i),'displayName':f'Fixture {i}'}} for i in range(5)]}]}]}}
    game={'game_id':'espn:1','game_time':'2026-10-06T23:00:00Z','home':'A','away':'B'}
    now=datetime(2026,10,6,12,tzinfo=timezone.utc)
    provider=Provider(True)
    assert load_game_lineups(game,now,provider)['teams']['home']['status']=='Confirmed'
    assert 'ESPN depth charts' not in provider.calls
    provider=Provider(False)
    assert load_game_lineups(game,now,provider)['teams']['home']['status']=='Projected'
    provider=Provider(False)
    assert load_game_lineups({**game,'game_time':'2026-10-05T23:00:00Z'},now,provider)['teams']['home']['status']=='Unavailable'
    assert 'ESPN depth charts' not in provider.calls
