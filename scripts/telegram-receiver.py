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

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / 'content' / 'transmissions'
MEDIA = ROOT / 'static' / 'transmissions'
STATE = Path.home() / '.local' / 'state' / 'spykespace-transmissions' / 'offset.json'
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


def publish(token, messages):
    first = messages[0]
    chat_id = first['chat']['id']
    timestamp = datetime.fromtimestamp(first['date'], timezone.utc)
    # Album posts are keyed by media_group_id, ordinary posts by message_id.
    group = first.get('media_group_id')
    identity = ('album-' + re.sub(r'[^0-9A-Za-z_-]', '', str(group))) if group else str(first['message_id'])
    stem = f'{timestamp:%Y-%m-%d-%H%M%S}-{chat_id}-{identity}'
    destination = CONTENT / (stem + '.md')
    if destination.exists():
        return 'already-published'
    if git('status', '--porcelain').stdout.strip():
        raise RuntimeError('Git working tree is not clean; commit or stash unrelated edits.')
    git('pull', '--ff-only', 'origin', 'main')
    if destination.exists():
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
        body = '\n\n'.join(captions + blocks)
        destination.write_text('\n'.join(front) + body + '\n', encoding='utf-8')
        run('hugo', '--gc', '--minify')
        git('add', '--', str(destination.relative_to(ROOT)), *[str(p.relative_to(ROOT)) for p in media_files])
        git('commit', '-m', f'Publish transmission {identity}')
        git('push', 'origin', 'main')
        return 'published'
    except Exception:
        # If commit happened but push failed, preserve files and commit for recovery.
        if not git('status', '--porcelain').stdout.strip() and destination.exists():
            raise
        # Remove only files created for this attempted post; never delete a committed file.
        try:
            committed = git('ls-files', '--error-unmatch', str(destination.relative_to(ROOT))).returncode == 0
        except subprocess.CalledProcessError:
            committed = False
        if not committed:
            destination.unlink(missing_ok=True)
            for path in media_files:
                path.unlink(missing_ok=True)
            git('reset', '--quiet')
        raise


def push_pending():
    # A failed git push after a successful commit leaves a clean tree and an unpushed commit.
    # Push before accepting further messages; a repeated message then resolves as duplicate.
    git('push', 'origin', 'main')


def main():
    token = os.environ.get('SPYKESPACE_BOT_TOKEN') or getpass.getpass('Telegram bot token: ').strip()
    if not token:
        raise RuntimeError('No bot token supplied.')
    offset = load_offset()
    if offset is None:
        # Preserve original receiver behavior: ignore updates pending before first start.
        old = api(token, 'getUpdates', {'offset': -1, 'timeout': 0})
        offset = old[-1]['update_id'] + 1 if old else 0
        save_offset(offset)
    print('SpykeSpace multimedia receiver running. Ctrl+C to stop.', flush=True)
    while True:
        try:
            push_pending()
            updates = api(token, 'getUpdates', {'offset': offset, 'timeout': POLL_SECONDS, 'limit': 100})
            index = 0
            while index < len(updates):
                update = updates[index]
                message = update.get('message') or {}
                next_offset = update['update_id'] + 1
                if message.get('from', {}).get('id') != AUTHORIZED_USER:
                    offset = next_offset
                    save_offset(offset)
                    index += 1
                    continue
                group = message.get('media_group_id')
                batch = [message]
                if group:
                    # Telegram albums may arrive across multiple polls. Briefly collect more.
                    time.sleep(2)
                    more = api(token, 'getUpdates', {'offset': next_offset, 'timeout': 2, 'limit': 100})
                    seen = {u['update_id'] for u in updates}
                    updates.extend(u for u in more if u['update_id'] not in seen)
                    updates.sort(key=lambda u: u['update_id'])
                    j = index + 1
                    while j < len(updates) and (updates[j].get('message') or {}).get('media_group_id') == group:
                        batch.append(updates[j]['message'])
                        next_offset = updates[j]['update_id'] + 1
                        j += 1
                    index = j
                else:
                    index += 1
                try:
                    status = publish(token, batch)
                    reply = ('📡 Transmission submitted to SpykeSpace.' if status == 'published'
                             else 'This transmission already exists.')
                except ValueError as exc:
                    reply = 'Transmission not published: ' + str(exc)
                except Exception as exc:
                    print('Publishing failed; will retry:', repr(exc), flush=True)
                    break
                # Advance offset before acknowledgement to avoid republishing on reply failure.
                offset = next_offset
                save_offset(offset)
                try:
                    tell(token, message['chat']['id'], reply)
                except Exception as exc:
                    print('Published but acknowledgement failed:', repr(exc), flush=True)
        except (urllib.error.URLError, RuntimeError, subprocess.CalledProcessError, TimeoutError) as exc:
            print('Receiver error:', repr(exc), flush=True)
            time.sleep(8)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nReceiver stopped.')
