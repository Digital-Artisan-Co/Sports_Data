"""Versioned, real provider snapshots for hosts blocked by NBA.com."""
import gzip
import requests
import json
from pathlib import Path
from datetime import datetime, timezone
from .model import instant

ROOT=Path(__file__).resolve().parents[1]/'snapshots'

def snapshot_name(kind,season,season_type='Regular Season'):
    if not all(c.isdigit() or c=='-' for c in season):raise ValueError('Invalid season')
    suffix='preseason' if season_type=='Pre Season' else 'regular'
    return f'nba_{kind}_{season}_{suffix}.json.gz'

def load_snapshot(kind,season,season_type='Regular Season',now=None):
    path=ROOT/snapshot_name(kind,season,season_type)
    payload=None
    # Data-only branch refreshes do not redeploy the app or erase its local database.
    if now is None:
        try:
            url='https://raw.githubusercontent.com/Digital-Artisan-Co/Sports_Data/nba-data/snapshots/'+path.name
            response=requests.get(url,timeout=6)
            if response.status_code==200:
                payload=json.loads(gzip.decompress(response.content))
        except (requests.RequestException,ValueError,OSError):pass
    if payload is None:
        if not path.exists():raise ValueError('No saved NBA snapshot for this season')
        with gzip.open(path,'rt',encoding='utf-8') as f:payload=json.load(f)
    if payload.get('source')!='NBA.com via nba_api' or payload.get('season')!=season or payload.get('kind')!=kind:
        raise ValueError('Snapshot provenance does not match the request')
    now=instant(now or datetime.now(timezone.utc).isoformat())
    age=(now-instant(payload['retrieved_at'])).total_seconds()/3600
    current_start=now.year if now.month>=10 else now.year-1
    completed_regular=kind=='logs' and season_type=='Regular Season' and int(season[:4])<current_start
    if age<0 or (age>24 and not completed_regular):
        raise ValueError('NBA snapshot is stale (over 24 hours); current roster/minutes unavailable')
    if not isinstance(payload.get('rows'),list):raise ValueError('Invalid snapshot records')
    return payload['rows'],{'status':'CACHED — NBA.com snapshot','source':payload['source'],
        'retrieved_at':payload['retrieved_at'],'age_hours':round(age,1),'records':len(payload['rows'])}
