"""SpykeSpace content identity and safe deletion planning. Python 3.9+ stdlib."""
import json
import re
from pathlib import Path
from urllib.parse import unquote

STEM = re.compile(r'^\d{4}-\d\d-\d\d-\d{6}-(\d+)-(album-[A-Za-z0-9_-]+|\d+)$')
REF = re.compile(r'/transmissions/([A-Za-z0-9_.%-]+)')

def frontmatter(text):
    if not text.startswith('+++\n'):
        raise ValueError('Missing TOML front matter')
    end = text.find('\n+++\n', 4)
    if end < 0:
        raise ValueError('Unclosed TOML front matter')
    return text[4:end], text[end+5:]

def media_refs(text):
    return sorted({unquote(x) for x in REF.findall(text)})

def identity(path, text):
    match = STEM.fullmatch(path.stem)
    if not match:
        return {'id': 'legacy:' + path.stem, 'source': 'legacy', 'message_ids': []}
    chat, key = match.groups()
    ids = []
    if key.isdigit():
        ids = [int(key)]
    else:
        for name in media_refs(text):
            member = re.search(r'-(\d+)\.[A-Za-z0-9]+$', name)
            if member:
                ids.append(int(member.group(1)))
    return {'id': f'telegram:{chat}:{key}', 'source': 'telegram', 'message_ids': sorted(set(ids))}

def toml_string(value):
    return json.dumps(value, ensure_ascii=False)

def decorate(path, text, message_ids=None):
    front, body = frontmatter(text)
    if re.search(r'(?m)^spyke_id\s*=', front):
        return text
    info = identity(path, text)
    if message_ids is not None and info['source'] == 'telegram':
        info['message_ids'] = sorted(set(int(i) for i in message_ids))
    refs = media_refs(text)
    additions = [
        'spyke_id = ' + toml_string(info['id']),
        'spyke_source = ' + toml_string(info['source']),
        'spyke_message_ids = [' + ', '.join(str(x) for x in info['message_ids']) + ']',
        'spyke_media = [' + ', '.join(toml_string(x) for x in refs) + ']',
    ]
    return '+++\n' + front + '\n' + '\n'.join(additions) + '\n+++\n' + body

def inventory(content):
    result = []
    for path in sorted(content.glob('*.md')):
        if path.name == '_index.md':
            continue
        text = path.read_text(encoding='utf-8')
        frontmatter(text)
        info = identity(path, text)
        # Explicit IDs cover all album members, including caption-only items.
        match = re.search(r'(?m)^spyke_message_ids\s*=\s*\[([^\]]*)\]', frontmatter(text)[0])
        if match:
            info['message_ids'] = [int(v.strip()) for v in match.group(1).split(',') if v.strip()]
        result.append({'path': path, 'id': info['id'], 'source': info['source'],
                       'message_ids': info['message_ids'], 'media': media_refs(text)})
    return result

def plan_delete(content, media_root, chat_id, reply_id):
    records = inventory(content)
    matches = [r for r in records if r['id'].startswith(f'telegram:{chat_id}:')
               and reply_id in r['message_ids']]
    if len(matches) != 1:
        raise ValueError('No unique published message matches that Telegram reply. For legacy or caption-only album messages, use a reply to a media item.')
    target = matches[0]
    other = {name for r in records if r is not target for name in r['media']}
    # Also protect attachments referenced by other Hugo Markdown pages.
    site_content = content.parent
    for page in site_content.rglob('*.md'):
        if page == target['path'] or page.parent == content:
            continue
        other.update(media_refs(page.read_text(encoding='utf-8')))
    exclusive = [name for name in target['media'] if name not in other]
    shared = [name for name in target['media'] if name in other]
    for name in exclusive:
        if Path(name).name != name:
            raise ValueError('Unsafe attachment filename')
        if not (media_root / name).is_file():
            raise ValueError('Attachment missing: ' + name)
    return {'message': target['path'], 'id': target['id'], 'exclusive': exclusive,
            'shared': shared, 'media_root': media_root}
