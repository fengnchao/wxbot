"""Small, strict wire schema shared by the two authenticated services."""
import re

MAX_ITEMS = 50
MAX_TEXT = 10000
MEDIA_ID = re.compile(r'[0-9a-f]{32}')


def validate_media_id(value):
    if not isinstance(value, str) or not MEDIA_ID.fullmatch(value):
        raise ValueError('无效 media_id')
    return value


def validate_items(items):
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError('图文包须包含 1-50 个项目')
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('无效图文项目')
        if item.get('kind') == 'text' and set(item) == {'kind', 'text'}:
            text = item['text']
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                raise ValueError('无效图文正文')
            result.append({'kind': 'text', 'text': text})
        elif item.get('kind') == 'image' and set(item) == {'kind', 'media_id'}:
            result.append({'kind': 'image', 'media_id': validate_media_id(item['media_id'])})
        else:
            raise ValueError('图文项目仅支持正文或服务端 media_id')
    return result


def validate_request_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', value):
        raise ValueError('无效 request_id')
    return value
