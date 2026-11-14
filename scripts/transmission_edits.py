"""Stable per-Telegram-message captions inside Hugo transmission Markdown."""
import re

class EditableCaptionError(ValueError):
    pass

def caption_block(message_id, caption):
    """Keep attribution even when a caption is empty or later removed."""
    mid = int(message_id)
    return '<!-- spyke-caption:{}:start -->\n{}\n<!-- spyke-caption:{}:end -->'.format(mid, caption, mid)

def replace_caption(body, message_id, caption, is_album=False):
    mid = int(message_id)
    pattern = re.compile(r'<!-- spyke-caption:' + str(mid) + r':start -->\n(.*?)\n<!-- spyke-caption:' + str(mid) + r':end -->', re.S)
    matches = list(pattern.finditer(body))
    if len(matches) == 1:
        return body[:matches[0].start()] + caption_block(mid, caption) + body[matches[0].end():]
    if matches:
        raise EditableCaptionError('Duplicate caption markers.')
    if is_album:
        raise EditableCaptionError('Older album has no reliable per-message caption markers.')
    # Legacy single-message Markdown: caption precedes media/preview blocks.
    # Never infer album ownership. Keep all existing media and previews intact.
    media = re.search(r'(?m)^(!\[Transmission photograph\]\(/transmissions/|\{\{< transmission-(?:audio|video|link)\b)', body)
    if media:
        tail = body[media.start():]
        return (caption + '\n\n' if caption else '') + tail
    return caption + '\n'
