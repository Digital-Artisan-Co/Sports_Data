"""Refresh real NBA snapshots. Failure never replaces a previously valid snapshot."""
import gzip
import json
import sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nba.providers import Providers
from nba.snapshots import ROOT,snapshot_name

now=datetime.now(timezone.utc)
year=now.year if now.month>=10 else now.year-1
current=f'{year}-{str(year+1)[-2:]}'
previous=f'{year-1}-{str(year)[-2:]}'
p=Providers(allow_snapshots=False)
ROOT.mkdir(exist_ok=True)
failures=[]
for kind,season,season_type in [('logs',previous,'Regular Season'),('logs',current,'Regular Season'),('logs',current,'Pre Season'),('roster',current,'Regular Season')]:
    try:
        rows=p.nba_roster(season) if kind=='roster' else p.nba_logs(season,season_type)
        if not rows:
            print(kind,season,season_type,'empty — preserving previous snapshot');continue
        payload={'schema_version':1,'source':'NBA.com via nba_api','kind':kind,'season':season,'season_type':season_type,
                 'retrieved_at':datetime.now(timezone.utc).isoformat(),'rows':rows}
        path=ROOT/snapshot_name(kind,season,season_type)
        temp=path.with_suffix('.tmp')
        temp.write_bytes(gzip.compress(json.dumps(payload,allow_nan=False,separators=(',',':')).encode(),mtime=0))
        temp.replace(path)
        print(kind,season,season_type,len(rows),'real records saved')
    except Exception as e:
        failures.append((kind,season,season_type,type(e).__name__))
        print(kind,season,season_type,'refresh failed; existing snapshot preserved')
if failures:sys.exit(1)
