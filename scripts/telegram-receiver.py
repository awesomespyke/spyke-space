#!/usr/bin/env python3
"""SpykeSpace Telegram multimedia publisher. Python standard library only."""
import getpass
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from lifecycle import decorate, plan_delete, frontmatter, inventory, media_refs
from link_preview import preview
import secrets
from album_journal import Journal
from tombstones import Tombstones
from deletion_transaction import DeletionTransaction, reconcile as reconcile_deletion

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / 'content' / 'transmissions'
MEDIA = ROOT / 'static' / 'transmissions'
STATE = Path.home() / '.local' / 'state' / 'spykespace-transmissions' / 'offset.json'
PENDING = STATE.with_name('pending-deletion.json')
JOURNAL_PATH = STATE.with_name('update-journal.json')
TOMBSTONES_PATH = STATE.with_name('deletion-tombstones.json')
DELETION_TX_PATH = STATE.with_name('deletion-transaction.json')
AUTHORIZED_USER = 8476369874
POLL_SECONDS = 20
MAX_BYTES = 20 * 1024 * 1024  # Telegram cloud Bot API getFile download ceiling


def api(token, method, params=None):
    data = urllib.parse.urlencode(params or {}).encode()
    request = urllib.request.Request(f'https://api.telegram.org/bot{token}/{method}', data=data)
    with urllib.request.urlopen(request, timeout=55) as response:
        body = json.load(response)
    if not body.get('ok'):
        raise RuntimeError(f'Telegram {method} failed: {body.get("description", "unknown error")}')
    return body['result']


def run(*args):
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True)


def git(*args):
    return run('git', *args)


def tell(token, chat, message):
    api(token, 'sendMessage', {'chat_id': chat, 'text': message})


def load_offset():
    try:
        return int(json.loads(STATE.read_text())['offset'])
    except FileNotFoundError:
        return None


def save_offset(offset):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps({'offset': offset}), encoding='utf-8')
    tmp.replace(STATE)


def file_kind(message):
    if 'photo' in message:
        return 'photo', message['photo'][-1], '.jpg'
    for kind, ext in [('voice', '.ogg'), ('audio', '.mp3'), ('video', '.mp4'), ('video_note', '.mp4')]:
        if kind in message:
            return kind, message[kind], ext
    if 'document' in message:
        obj = message['document']
        mime = obj.get('mime_type', '')
        if mime.startswith('image/'):
            return 'photo', obj, mimetypes.guess_extension(mime) or '.jpg'
        if mime.startswith('audio/'):
            return 'audio', obj, mimetypes.guess_extension(mime) or '.mp3'
        if mime.startswith('video/'):
            return 'video', obj, mimetypes.guess_extension(mime) or '.mp4'
    return None


def safe_ext(kind, info, default):
    name = info.get('file_name', '')
    ext = Path(name).suffix.lower()
    allowed = {
        'photo': {'.jpg', '.jpeg', '.png', '.webp', '.gif'},
        'voice': {'.ogg', '.oga', '.mp3', '.m4a'},
        'audio': {'.mp3', '.m4a', '.aac', '.ogg', '.oga', '.wav', '.flac'},
        'video': {'.mp4', '.webm', '.mov'},
        'video_note': {'.mp4', '.webm'},
    }
    return ext if ext in allowed[kind] else default


def download(token, info, target):
    if info.get('file_size', 0) > MAX_BYTES:
        raise ValueError('File exceeds the 20 MB Telegram Bot API download limit.')
    remote = api(token, 'getFile', {'file_id': info['file_id']})
    if remote.get('file_size', 0) > MAX_BYTES:
        raise ValueError('File exceeds the 20 MB Telegram Bot API download limit.')
    file_path = remote['file_path']
    # Telegram supplies the relative path; URL-encode segments to avoid accidental query strings.
    remote_url = 'https://api.telegram.org/file/bot' + token + '/' + '/'.join(
        urllib.parse.quote(p, safe='') for p in file_path.split('/')
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + '.part')
    try:
        with urllib.request.urlopen(remote_url, timeout=120) as response, temp.open('wb') as output:
            total = 0
            while True:
                block = response.read(1024 * 256)
                if not block:
                    break
                total += len(block)
                if total > MAX_BYTES:
                    raise ValueError('Downloaded file exceeded 20 MB.')
                output.write(block)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def quote_toml(value):
    return json.dumps(value, ensure_ascii=False)


def render_item(kind, url):
    if kind == 'photo':
        return f'![Transmission photograph]({url})'
    if kind in ('voice', 'audio'):
        return '{{< transmission-audio src="' + url + '" >}}'
    return '{{< transmission-video src="' + url + '" >}}'


def link_card(captions):
    """Create one optional rich preview without changing original message text."""
    text = '\n'.join(captions)
    match = re.search(r'https://[^\s<>"\x27]+', text)
    if not match:
        return None

    url = match.group(0).rstrip('.,;:!?)]}')
    metadata = preview(url)
    if not metadata:
        return None

    fields = ['url', 'title', 'description', 'image']
    arguments = [
        key + '=' + quote_toml(metadata[key])
        for key in fields if metadata.get(key)
    ]
    return '{{< transmission-link ' + ' '.join(arguments) + ' >}}'

def find_existing_album(chat_id, group):
    """Find the canonical album regardless of the timestamp of a late member."""
    key = 'telegram:{}:album-{}'.format(chat_id, re.sub(r'[^0-9A-Za-z_-]', '', str(group)))
    matches = [r for r in inventory(CONTENT) if r['id'] == key]
    if len(matches) > 1:
        raise RuntimeError('Multiple published files match the same album identity.')
    return matches[0] if matches else None


def merge_album(token, messages, record):
    """Append late album media to its original publication without changing its URL.

    This is a development candidate: deletion tombstones and all crash windows
    are NOT yet resolved, so do not deploy it.
    """
    destination = record['path']
    original = destination.read_text(encoding='utf-8')
    front, body = frontmatter(original)
    known_ids = set(record['message_ids'])
    additions = [m for m in messages if m['message_id'] not in known_ids]
    if not additions:
        return 'already-published'
    new_files = []
    new_blocks = []
    new_captions = []
    try:
        for m in additions:
            content = m.get('caption') or m.get('text') or ''
            if content:
                new_captions.append(content)
            found = file_kind(m)
            if not found:
                raise ValueError('Late album member has no supported media.')
            kind, info, default = found
            ext = safe_ext(kind, info, default)
            name = '{}-{}{}'.format(destination.stem, m['message_id'], ext)
            target = MEDIA / name
            if not target.exists():
                download(token, info, target)
            new_files.append(target)
            new_blocks.append(render_item(kind, '/transmissions/' + urllib.parse.quote(name)))
        merged_ids = sorted(known_ids | {m['message_id'] for m in additions})
        merged_refs = sorted(set(record['media']) | {p.name for p in new_files})
        def replace_field(field, value):
            nonlocal front
            pattern = r'(?m)^' + re.escape(field) + r'\s*=.*$'
            line = field + ' = ' + value
            if re.search(pattern, front):
                front = re.sub(pattern, lambda _: line, front)
            else:
                front += '\n' + line
        replace_field('spyke_message_ids', '[' + ', '.join(map(str, merged_ids)) + ']')
        replace_field('spyke_media', '[' + ', '.join(quote_toml(x) for x in merged_refs) + ']')
        updated = '+++\n' + front + '\n+++\n' + body.rstrip('\n') + '\n\n' + '\n\n'.join(new_captions + new_blocks) + '\n'
        destination.write_text(updated, encoding='utf-8')
        run('hugo', '--gc', '--minify')
        git('add', '--', str(destination.relative_to(ROOT)), *[str(p.relative_to(ROOT)) for p in new_files])
        git('commit', '-m', 'Reconcile transmission album ' + destination.stem)
        git('push', 'origin', 'main')
        return 'reconciled'
    except Exception:
        # Restore only when no commit occurred. Committed work must be pushed
        # on recovery rather than undone.
        tracked = git('status', '--porcelain', '--', str(destination.relative_to(ROOT))).stdout.strip()
        if tracked:
            # An uncommitted edit is safe to restore; a committed edit is clean.
            git('restore', '--staged', '--', str(destination.relative_to(ROOT)))
            git('restore', '--', str(destination.relative_to(ROOT)))
            for path in new_files:
                rel = str(path.relative_to(ROOT))
                if not git('ls-files', '--', rel).stdout.strip():
                    git('reset', '--quiet', '--', rel)
                    path.unlink(missing_ok=True)
        raise


def publish(token, messages):
    first = messages[0]
    chat_id = first['chat']['id']
    timestamp = datetime.fromtimestamp(first['date'], timezone.utc)
    # Album posts are keyed by media_group_id, ordinary posts by message_id.
    group = first.get('media_group_id')
    identity = ('album-' + re.sub(r'[^0-9A-Za-z_-]', '', str(group))) if group else str(first['message_id'])
    stem = f'{timestamp:%Y-%m-%d-%H%M%S}-{chat_id}-{identity}'
    destination = CONTENT / (stem + '.md')
    canonical_id = 'telegram:{}:{}'.format(chat_id, identity)
    if Tombstones(TOMBSTONES_PATH).contains(canonical_id):
        return 'deleted'
    if git('status', '--porcelain').stdout.strip():
        raise RuntimeError('Git working tree is not clean; commit or stash unrelated edits.')
    git('pull', '--ff-only', 'origin', 'main')
    if group:
        existing = find_existing_album(chat_id, group)
        if existing:
            return merge_album(token, messages, existing)
    elif destination.exists():
        return 'already-published'
    CONTENT.mkdir(parents=True, exist_ok=True)
    media_files = []
    blocks = []
    captions = []
    try:
        for message in messages:
            body = message.get('text') or message.get('caption') or ''
            if body:
                captions.append(body)
            found = file_kind(message)
            if not found:
                if 'text' not in message:
                    raise ValueError('Unsupported Telegram attachment type.')
                continue
            kind, info, default = found
            ext = safe_ext(kind, info, default)
            name = f'{stem}-{message["message_id"]}{ext}'
            path = MEDIA / name
            if not path.exists():
                download(token, info, path)
            media_files.append(path)
            blocks.append(render_item(kind, '/transmissions/' + urllib.parse.quote(name)))
        if not captions and not blocks:
            raise ValueError('Empty transmission.')
        front = [
            '+++', f'date = {quote_toml(timestamp.isoformat())}',
            f'title = {quote_toml("Transmission " + str(first["message_id"]))}',
            'draft = false', '+++', '',
        ]
        card = link_card(captions)
        body = '\n\n'.join(captions + blocks + ([card] if card else []))
        destination.write_text(decorate(destination, '\n'.join(front) + body + '\n',
                                        message_ids=[m['message_id'] for m in messages]), encoding='utf-8')
        run('hugo', '--gc', '--minify')
        git('add', '--', str(destination.relative_to(ROOT)), *[str(p.relative_to(ROOT)) for p in media_files])
        git('commit', '-m', f'Publish transmission {identity}')
        git('push', 'origin', 'main')
        return 'published'
    except Exception:
        # A commit may have succeeded even when push failed. Never undo a commit.
        committed = git('ls-files', '--', str(destination.relative_to(ROOT))).stdout.strip() != ''
        if not committed:
            destination.unlink(missing_ok=True)
            for path in media_files:
                path.unlink(missing_ok=True)
            git('reset', '--quiet')
        raise


def pending_load():
    try:
        return json.loads(PENDING.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return None


def pending_save(data):
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    temp = PENDING.with_suffix('.tmp')
    temp.write_text(json.dumps(data), encoding='utf-8')
    temp.replace(PENDING)


def delete_command(token, message):
    chat = message['chat']['id']
    command = (message.get('text') or '').strip()
    if command == '/cancel':
        PENDING.unlink(missing_ok=True)
        tell(token, chat, 'Deletion cancelled.')
        return
    if command.split(maxsplit=1)[0] == '/delete':
        reply = message.get('reply_to_message') or {}
        if not reply or not isinstance(reply.get('message_id'), int):
            tell(token, chat, 'Reply to the original Telegram message with /delete.')
            return
        plan = plan_delete(CONTENT, MEDIA, chat, reply['message_id'])
        pending = {'chat': chat, 'reply': reply['message_id'], 'id': plan['id']}
        plan = plan_delete(CONTENT, MEDIA, chat, pending['reply'])
        if plan['id'] != pending['id']:
            raise RuntimeError('Deletion target changed; cancelled.')
        if git('status', '--porcelain').stdout.strip():
            raise RuntimeError('Git working tree is not clean; deletion deferred.')
        git('pull', '--ff-only', 'origin', 'main')
        plan = plan_delete(CONTENT, MEDIA, chat, pending['reply'])
        if plan['id'] != pending['id']:
            raise RuntimeError('Deletion target changed after pull; cancelled.')
        paths = [plan['message']] + [MEDIA / x for x in plan['exclusive']]
        relative = [str(x.relative_to(ROOT)) for x in paths]
        tx = DeletionTransaction(DELETION_TX_PATH)
        tx.begin(plan['id'], plan['message'].relative_to(ROOT).as_posix())
        git('rm', '--', *relative)
        try:
            run('hugo', '--gc', '--minify')
        except Exception:
            git('restore', '--staged', '--', *relative)
            git('restore', '--', *relative)
            tx.clear()
            raise
        git('commit', '-m', 'Delete transmission ' + plan['id'])
        # Durable deletion guard before push/replay. A crash between commit and
        # this marker still requires Git reconciliation before processing updates.
        Tombstones(TOMBSTONES_PATH).add(plan['id'])
        tx.clear()
        # Persist committed state before push for automatic retry on the next loop.
        pending['committed'] = True
        pending_save(pending)
        git('push', 'origin', 'main')
        PENDING.unlink(missing_ok=True)
        tell(token, chat, 'Deleted published message and its exclusive attachments.')


def push_pending():
    # A failed git push after a successful commit leaves a clean tree and an unpushed commit.
    # Push before accepting further messages; a repeated message then resolves as duplicate.
    git('push', 'origin', 'main')


ALBUM_QUIET_SECONDS = 3.0
ALBUM_MAX_WAIT_SECONDS = 12.0


def collect_album_window(token, updates, offset, clock=None, sleeper=None):
    """Collect delayed album members without assuming consecutive update IDs.

    Do not acknowledge any update while gathering. Stop after a quiet interval
    following the most recent arrival, bounded by an overall deadline.
    """
    clock = clock or time.monotonic
    sleeper = sleeper or time.sleep
    if not any((u.get('message') or {}).get('media_group_id') for u in updates):
        return updates
    if len(updates) >= 100:
        raise RuntimeError('Telegram update window full; album collection deferred.')
    seen = {u['update_id']: u for u in updates}
    start = clock()
    last_arrival = start
    while clock() - start < ALBUM_MAX_WAIT_SECONDS and clock() - last_arrival < ALBUM_QUIET_SECONDS:
        sleeper(min(0.25, ALBUM_MAX_WAIT_SECONDS - (clock() - start),
                    ALBUM_QUIET_SECONDS - (clock() - last_arrival)))
        # Re-fetch from the original offset: no update is acknowledged while gathering.
        more = api(token, 'getUpdates', {'offset': offset, 'timeout': 0, 'limit': 100})
        fresh = [u for u in more if u['update_id'] not in seen]
        if fresh:
            seen.update((u['update_id'], u) for u in fresh)
            last_arrival = clock()
        # Never treat a truncated 100-update window as complete.
        if len(more) >= 100:
            raise RuntimeError('Telegram update window full; album collection deferred.')
    return sorted(seen.values(), key=lambda u: u['update_id'])


def group_work(updates):
    """Return (first update ID, member updates) in first-arrival order."""
    grouped = {}
    work = []
    for update in sorted(updates, key=lambda u: u['update_id']):
        message = update.get('message') or {}
        group = message.get('media_group_id')
        if group is None:
            work.append((update['update_id'], [update]))
        else:
            key = (message.get('chat', {}).get('id'), str(group))
            if key not in grouped:
                grouped[key] = []
                work.append((update['update_id'], grouped[key]))
            grouped[key].append(update)
    return work


def process_staged(token, journal, now=None):
    """Process durable updates. Completion only follows a successful publish/command.

    Pending albums stay staged until quiet; later arrivals are handled separately
    by the reconciliation-aware publisher. Never advance an offset here.
    """
    for members in journal.ready(now=now, quiet_seconds=10):
        message = members[0].get('message') or {}
        if message.get('from', {}).get('id') != AUTHORIZED_USER:
            journal.mark_done(members)
            continue
        command = (message.get('text') or '').strip().split(' ', 1)[0]
        if command in ('/delete', '/cancel'):
            try:
                delete_command(token, message)
            except ValueError as exc:
                tell(token, message['chat']['id'], 'Deletion not available: ' + str(exc))
            journal.mark_done(members)
            continue
        batch = [u['message'] for u in members]
        try:
            status = publish(token, batch)
        except ValueError as exc:
            tell(token, message['chat']['id'], 'Transmission not published: ' + str(exc))
            journal.mark_done(members)
            continue
        # Durable completion precedes the optional acknowledgement. A failed
        # acknowledgement must not trigger a second publication.
        journal.mark_done(members)
        try:
            tell(token, message['chat']['id'],
                 '\U0001F4E1 Transmission submitted to SpykeSpace.' if status == 'published'
                 else 'This transmission was deleted.' if status == 'deleted'
                 else 'This transmission already exists.')
        except Exception as exc:
            print('Published but acknowledgement failed:', repr(exc), flush=True)


def poll_and_stage(token, journal, offset, updates):
    """Persist all received updates BEFORE acknowledging via Telegram offset."""
    if not updates:
        return offset
    journal.ingest(updates)
    new_offset = max(offset, max(u['update_id'] for u in updates) + 1)
    save_offset(new_offset)
    return new_offset


def main():
    token = os.environ.get('SPYKESPACE_BOT_TOKEN') or getpass.getpass('Telegram bot token: ').strip()
    if not token:
        raise RuntimeError('No bot token supplied.')
    journal = Journal(JOURNAL_PATH)
    offset = load_offset()
    if offset is None:
        # Preserve the established first-run behavior, but never discard
        # already staged journal work.
        old = api(token, 'getUpdates', {'offset': -1, 'timeout': 0})
        offset = old[-1]['update_id'] + 1 if old else 0
        save_offset(offset)
    print('SpykeSpace journal-backed receiver running. Ctrl+C to stop.', flush=True)
    while True:
        try:
            reconcile_deletion(DeletionTransaction(DELETION_TX_PATH),
                               Tombstones(TOMBSTONES_PATH),
                               lambda path: subprocess.run(['git', 'cat-file', '-e', 'HEAD:' + path], cwd=ROOT, capture_output=True).returncode == 0,
                               lambda: not git('status', '--porcelain').stdout.strip())
            push_pending()
            # Drain staged work even when Telegram returns no new updates.
            process_staged(token, journal)
            updates = api(token, 'getUpdates', {'offset': offset, 'timeout': POLL_SECONDS, 'limit': 100})
            offset = poll_and_stage(token, journal, offset, updates)
            process_staged(token, journal)
        except (urllib.error.URLError, RuntimeError, subprocess.CalledProcessError,
                TimeoutError, OSError, ValueError) as exc:
            print('Receiver error:', repr(exc), flush=True)
            time.sleep(8)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nReceiver stopped.')

