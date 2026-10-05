import json
from nba import runtime

def test_cache_update_preserves_old_bytes(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'DATA_DIR',tmp_path)
    runtime.save_cache('bundle.json',{'original':True})
    before=(tmp_path/'bundle.json').read_bytes()
    runtime.save_cache('bundle.json',{'new':True})
    assert json.loads((tmp_path/'bundle.json').read_text())=={'new':True}
    assert next((tmp_path/'cache_history').iterdir()).read_bytes()==before
