"""Durable local deletion markers; Python 3.9+ stdlib."""
import json
import os
import tempfile
from pathlib import Path

class Tombstones:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version') != 1 or not isinstance(data.get('ids'), list) or not all(isinstance(x, str) for x in data['ids']):
                raise ValueError('Invalid tombstone state')
            self.ids = set(data['ids'])
        else:
            self.ids = set()

    def contains(self, identity):
        return identity in self.ids

    def add(self, identity):
        if identity in self.ids:
            return
        updated = self.ids | {identity}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.tombstones-', dir=str(self.path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump({'version': 1, 'ids': sorted(updated)}, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, self.path)
            self.ids = updated
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
