"""Bot API image download and authenticated Butler registration, outside the UI."""
import re

import requests

from butler.delivery.media import MAX_BYTES, validate_image
from common.media_bundle import validate_media_id


class MediaError(ValueError):
    """A controlled, credential-free media diagnostic suitable for operator status."""


def validate_file_path(path):
    if (not isinstance(path, str) or len(path) > 1024
            or not re.fullmatch(r'[A-Za-z0-9_./-]+', path)
            or any(part in ('', '.', '..') for part in path.split('/'))):
        raise MediaError('无效 Telegram 文件位置')
    return path


class TelegramMedia:
    def __init__(self, api, cfg, *, upload=None):
        self.api, self.cfg = api, cfg
        self.upload = upload or self._upload

    def _upload(self, data):
        cfg = self.cfg
        host = '127.0.0.1' if cfg.host in ('0.0.0.0', '::') else cfg.host
        if host not in ('127.0.0.1', 'localhost', '::1') or not cfg.token:
            raise MediaError('图片注册仅支持已认证本机 Butler')
        address = f'[{host}]' if ':' in host else host
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.post(f'http://{address}:{cfg.port}/v1/media', data=data,
                    headers={'Authorization': 'Bearer ' + cfg.token, 'Content-Type': 'application/octet-stream'},
                    timeout=(5, 30), allow_redirects=False) as response:
                    if response.status_code != 200:
                        raise MediaError('Butler 图片注册未确认')
                    return response.json()
        except (requests.RequestException, ValueError):
            raise MediaError('Butler 图片注册失败；未创建图文投递') from None

    def prepare(self, message):
        if message.get('has_protected_content'):
            raise MediaError('受保护内容不允许转发')
        photos = message.get('photo')
        document = message.get('document')
        if photos:
            if not isinstance(photos, list) or any(not isinstance(p, dict) for p in photos):
                raise MediaError('无效图片信息')
            descriptor = max(photos, key=lambda p: int(p.get('width', 0)) * int(p.get('height', 0)))
        elif document:
            if not isinstance(document, dict) or document.get('mime_type') not in ('image/jpeg', 'image/png', 'image/webp'):
                raise MediaError('附件类型暂不支持')
            descriptor = document
        elif any(message.get(k) for k in ('video', 'animation', 'audio', 'voice', 'sticker')):
            raise MediaError('附件类型暂不支持')
        else:
            return []
        file_id = descriptor.get('file_id')
        if not isinstance(file_id, str) or not 1 <= len(file_id) <= 512:
            raise MediaError('无效图片标识')
        for size in (descriptor.get('file_size'),):
            if size is not None and (type(size) is not int or not 0 < size <= MAX_BYTES):
                raise MediaError('Telegram 图片超过下载上限')
        result = self.api.call('getFile', file_id=file_id)
        if not isinstance(result, dict):
            raise MediaError('无效 getFile 回执')
        size = result.get('file_size')
        if size is not None and (type(size) is not int or not 0 < size <= MAX_BYTES):
            raise MediaError('Telegram 图片超过下载上限')
        data = self.api.download(validate_file_path(result.get('file_path')))
        validate_image(data)
        if size is not None and size != len(data):
            raise MediaError('Telegram 图片下载长度不匹配')
        metadata = self.upload(data)
        if not isinstance(metadata, dict):
            raise MediaError('无效图片注册回执')
        return [{'kind': 'image', 'media_id': validate_media_id(metadata.get('media_id'))}]
