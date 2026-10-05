import gzip,json
import pytest
from nba import snapshots

def write(tmp_path,kind,season,season_type,stamp):
    path=tmp_path/snapshots.snapshot_name(kind,season,season_type)
    payload={'source':'NBA.com via nba_api','kind':kind,'season':season,'season_type':season_type,'retrieved_at':stamp,'rows':[{'player_id':'fixture'}]}
    path.write_bytes(gzip.compress(json.dumps(payload).encode()))

def test_fresh_roster_is_usable(tmp_path,monkeypatch):
    monkeypatch.setattr(snapshots,'ROOT',tmp_path)
    write(tmp_path,'roster','2026-27','Regular Season','2026-10-05T12:00:00Z')
    rows,health=snapshots.load_snapshot('roster','2026-27',now='2026-10-05T20:00:00Z')
    assert len(rows)==1 and health['age_hours']==8

def test_stale_roster_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(snapshots,'ROOT',tmp_path)
    write(tmp_path,'roster','2026-27','Regular Season','2026-10-03T12:00:00Z')
    with pytest.raises(ValueError,match='stale'):
        snapshots.load_snapshot('roster','2026-27',now='2026-10-05T20:00:00Z')

def test_completed_season_remains_historical_data(tmp_path,monkeypatch):
    monkeypatch.setattr(snapshots,'ROOT',tmp_path)
    write(tmp_path,'logs','2025-26','Regular Season','2026-10-03T12:00:00Z')
    rows,_=snapshots.load_snapshot('logs','2025-26',now='2026-10-05T20:00:00Z')
    assert rows
