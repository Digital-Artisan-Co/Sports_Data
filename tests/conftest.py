"""Tests use isolated databases and caches; never touch installed user data."""
import pytest
from nba import runtime, storage

@pytest.fixture(autouse=True)
def isolated_data(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'DATA_DIR',tmp_path)
    monkeypatch.setattr(storage,'DATA_DIR',tmp_path)

@pytest.fixture(autouse=True)
def offline_ui_imports(monkeypatch):
    from nba import sync
    def empty(provider,date,**kwargs):
        from datetime import datetime,timezone
        return {'date':date,'loaded_at':datetime.now(timezone.utc).isoformat(),'historical':False,
                'games':[],'bundle':None,'saved_rows':[],'actual_rows':[],'warnings':[],'stages':[],'error':None}
    monkeypatch.setattr(sync,'load_date',empty)
