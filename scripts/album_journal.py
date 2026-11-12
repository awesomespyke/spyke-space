"""Crash-safe, replayable staging for Telegram updates (Python 3.9+).

This module does NOT publish, acknowledge, or advance Telegram offsets.
Callers must persist incoming updates before acknowledging them, and only
mark processed after publication has durably completed.
"""
import json
import os
import tempfile
import time
from pathlib import Path

class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self._load()

    def _load(self):
        if not self.path.exists():
            return {'version': 1, 'updates': {}, 'done': []}
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('updates'), dict):
            raise ValueError('Unsupported journal format')
        return data

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.album-journal-', dir=str(self.path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump(self.data, out, ensure_ascii=False, sort_keys=True)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def ingest(self, updates, now=None):
        now = time.time() if now is None else now
        done = set(self.data['done'])
        for update in updates:
            uid = str(update['update_id'])
            if uid in done or uid in self.data['updates']:
                continue
            self.data['updates'][uid] = {'update': update, 'seen_at': now}
        self._save()

    def ready(self, now=None, quiet_seconds=10):
        """Return groups that have been quiet long enough; no state changes.

        For albums, all currently observed members share one work item. An
        arbitrarily late member can still appear later: Telegram has no
        explicit end-of-album marker. Production integration must reconcile
        late members and make publication idempotent.
        """
        now = time.time() if now is None else now
        groups = {}
        for uid, entry in self.data['updates'].items():
            msg = entry['update'].get('message') or {}
            group = msg.get('media_group_id')
            key = ('album', msg.get('chat', {}).get('id'), str(group)) if group is not None else ('single', uid)
            groups.setdefault(key, []).append(entry)
        ready = []
        for key, entries in groups.items():
            if key[0] == 'album' and now - max(x['seen_at'] for x in entries) < quiet_seconds:
                continue
            entries.sort(key=lambda x: x['update']['update_id'])
            ready.append([x['update'] for x in entries])
        ready.sort(key=lambda group: min(x['update_id'] for x in group))
        return ready

    def mark_done(self, updates):
        ids = {str(u['update_id']) for u in updates}
        if not ids.issubset(self.data['updates']):
            raise ValueError('Cannot complete unstaged updates')
        for uid in ids:
            del self.data['updates'][uid]
        self.data['done'] = sorted(set(self.data['done']).union(ids), key=int)
        self._save()
