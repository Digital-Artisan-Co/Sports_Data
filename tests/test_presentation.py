import pandas as pd
from nba.presentation import player_overview


def test_overview_keeps_players_games_and_missing_values_without_summing_books():
    rows = pd.DataFrame([
        dict(player_id=p, game_id=g, player='Same Name', team='A', opponent='B',
             projected_minutes=30, stat=s, projection=value, sportsbook=book)
        for p,g,s,value,book in [
            ('1','g1','pts',20,'FanDuel'), ('1','g1','pts',20,'DraftKings'),
            ('1','g1','reb',None,None), ('2','g1','pts',12,None), ('1','g2','pts',18,None)]
    ])
    overview, identities = player_overview(rows)
    assert identities == [('1','g1'),('2','g1'),('1','g2')]
    assert overview.Points.tolist() == [20,12,18]
    assert overview.Rebounds.isna().all()
    assert len(overview.columns) == 9
    selected, _ = player_overview(rows[rows.stat == 'pts'], 'Points')
    assert selected.columns.tolist() == ['Player','Matchup','Minutes','Points']
    empty, ids = player_overview(rows.iloc[:0])
    assert empty.empty and ids == []


def test_player_detail_view_renders_and_switches_players():
    from streamlit.testing.v1 import AppTest
    def page():
        import pandas as pd
        import streamlit as st
        from nba.presentation import render_player_props
        rows = pd.DataFrame([
            dict(player_id=p,game_id='game',player=name,team='A',opponent='B',
                 stat=s,projection=value,projected_minutes=30,confidence=65,
                 recommendation='No Play',missing=['matchup'],context={})
            for p,name,s,value in [('1','First','pts',20),('1','First','reb',7),('2','Second','pts',12)]
        ])
        render_player_props(st,rows)
    app = AppTest.from_function(page).run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 2
    assert app.dataframe[1].value.Stat.tolist() == ['Points','Rebounds']
    app.selectbox[0].select(('2','game')).run()
    assert not app.exception
    assert app.dataframe[1].value.Projection.tolist() == [12]
