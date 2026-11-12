"""Crash recovery for locally committed message deletion (Python 3.9+)."""
import json
import os
import tempfile
from pathlib import Path

class DeletionTransaction:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if (data.get('version') != 1 or not isinstance(data.get('identity'), str)
                or not data['identity'] or not isinstance(data.get('file'), str)
                or not data['file'].startswith('content/transmissions/')
                or '..' in Path(data['file']).parts):
            raise ValueError('Invalid deletion transaction')
        return data

    def begin(self, identity, relative_file):
        if self.load() is not None:
            raise RuntimeError('Unresolved deletion transaction')
        if not relative_file.startswith('content/transmissions/') or '..' in Path(relative_file).parts:
            raise ValueError('Unsafe message path')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.deletion-', dir=str(self.path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump({'version': 1, 'identity': identity, 'file': relative_file}, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def clear(self):
        self.path.unlink(missing_ok=True)

def reconcile(transaction, tombstones, tracked_in_head, working_tree_clean):
    """Conservative recovery. Never infer a committed deletion from disk absence.

    Caller must ensure a clean tree; a staged/uncommitted deletion is left for
    manual resolution rather than overwritten or acknowledged.
    """
    item = transaction.load()
    if item is None:
        return 'none'
    if not working_tree_clean():
        raise RuntimeError('Unresolved deletion transaction with dirty working tree')
    if tracked_in_head(item['file']):
        transaction.clear()
        return 'aborted'
    tombstones.add(item['identity'])
    transaction.clear()
    return 'committed'
