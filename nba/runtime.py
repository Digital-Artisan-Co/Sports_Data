"""Runtime paths and atomic cache writes; never discard the previous cache."""
import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR=Path(os.getenv('NBA_DATA_DIR','data'))

def save_cache(name,payload):
    target=DATA_DIR/name
    target.parent.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex
    pending=target.with_name(target.name+'.'+token+'.tmp')
    pending.write_text(json.dumps(payload,allow_nan=False),encoding='utf-8')
    if target.exists():
        archive=DATA_DIR/'cache_history'
        archive.mkdir(exist_ok=True)
        # Preserve bytes without moving the active file before replacement.
        (archive/(target.name+'.'+token)).write_bytes(target.read_bytes())
    pending.replace(target)
    return target
