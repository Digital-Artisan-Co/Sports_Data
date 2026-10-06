import pandas as pd
from nba.watchlists import leader_rows,historical_ceiling_rows


def test_projection_leaders_do_not_require_missing_tracking_or_duplicate_books():
    rows=pd.DataFrame([dict(player_id=p,game_id='g',stat='pts',projection=v,injury_status=status,
        top3_spike=None) for p,v,status in [('a',20,'Unknown'),('a',20,'Unknown'),('b',30,'Unknown'),('c',40,'Out'),('d',None,'Unknown')]])
    leaders=leader_rows(rows)
    assert leaders.player_id.tolist()==['b','a']
    assert leaders['rank'].tolist()==[1,2]
    assert leaders.top3_spike.isna().all()


def test_ceiling_research_requires_observed_threshold_history():
    rows=pd.DataFrame([dict(player_id=p,game_id='g',stat='pts',projection=15,season_high=35,
        projection_percentile=40,threshold_hit_rates=hits) for p,hits in [('a',{'30':.1}),('b',{})]])
    research=historical_ceiling_rows(rows)
    assert research.player_id.tolist()==['a']
    assert research.historical_hit_rate.tolist()==[10]


def test_unavailable_preseason_projections_do_not_invent_ceiling_history():
    rows=pd.DataFrame([dict(player_id='a',game_id='g',stat='pts',projection=None)])
    assert historical_ceiling_rows(rows).empty
