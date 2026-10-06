import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone
from .model import instant
from .runtime import DATA_DIR

class Store:
    def __init__(self,path=None):
        path=path or DATA_DIR/'nba.sqlite'
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.executescript('''CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, created TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS results(game_id TEXT, player_id TEXT, payload TEXT, PRIMARY KEY(game_id,player_id));
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, created TEXT, payload TEXT);''')
    def save(self,payload,now=None):
        now=instant(now or datetime.now(timezone.utc).isoformat())
        if not payload.get('rows'): raise ValueError('No predictions to save')
        for r in payload['rows']:
            if instant(r['game_time'])<=now: raise ValueError('Pregame snapshots must be saved before tipoff')
        identifier=str(uuid.uuid4()); payload={**payload,'id':identifier,'created':now.isoformat()}
        self.db.execute('INSERT INTO snapshots VALUES (?,?,?)',(identifier,now.isoformat(),json.dumps(payload,allow_nan=False))); self.db.commit()
        return identifier
    def snapshots(self): return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM snapshots ORDER BY created')]
    def result(self,row):
        if row.get('status')!='Final': raise ValueError('Only final box scores may enter completed-game audit')
        if not all(k in row for k in ('game_id','player_id','min','pts','reb','ast','fg3m','stl','blk')): raise ValueError('Incomplete box score')
        row={**row,'known_at':row.get('known_at',datetime.now(timezone.utc).isoformat())}
        self.db.execute('INSERT OR REPLACE INTO results VALUES (?,?,?)',(str(row['game_id']),str(row['player_id']),json.dumps(row))); self.db.commit()
    def results(self): return {(g,p):json.loads(v) for g,p,v in self.db.execute('SELECT * FROM results')}
    def artifact(self,payload):
        identifier=str(uuid.uuid4()); now=datetime.now(timezone.utc).isoformat()
        self.db.execute('INSERT INTO artifacts VALUES (?,?,?)',(identifier,now,json.dumps(payload))); self.db.commit(); return identifier

    def save_automatic(self, rows, source, now=None):
        """Save each upcoming game at most once per ten minutes, without overwrites."""
        now=instant(now or datetime.now(timezone.utc).isoformat())
        previous=self.snapshots()
        saved=[]
        games={str(r['game_id']) for r in rows if r.get('projection') is not None and instant(r['game_time'])>now}
        for game in games:
            recent=any((now-instant(s['created'])).total_seconds()<600 and
                       any(str(r['game_id'])==game for r in s['rows']) for s in previous)
            if recent:continue
            saved.append(self.save({'rows':[r for r in rows if str(r['game_id'])==game],
                                    'source':source,'automatic':True},now.isoformat()))
        return saved

    def artifacts(self):
        return [{'id':i,'created':c,**json.loads(p)} for i,c,p in self.db.execute('SELECT * FROM artifacts ORDER BY created')]

    def active_calibration(self):
        active=[a for a in self.artifacts() if a.get('status')=='active' and a.get('version')=='stat-bias-2']
        return active[-1] if active else None
