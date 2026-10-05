"""Tests use isolated databases and caches; never touch installed user data."""
import pytest
from nba import runtime, storage

@pytest.fixture(autouse=True)
def isolated_data(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'DATA_DIR',tmp_path)
    monkeypatch.setattr(storage,'DATA_DIR',tmp_path)
