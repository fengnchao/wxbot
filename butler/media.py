"""Butler-owned image bytes. Callers can name only server-issued opaque IDs."""
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4
import warnings

from PIL import Image, UnidentifiedImageError

from common.media_bundle import validate_media_id

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
FORMATS = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}


def validate_image(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise ValueError('图片为空或超过 20MiB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as im:
                mime = FORMATS.get(im.format)
                width, height = im.size
                if not mime or width * height > MAX_PIXELS or min(width, height) < 1 or getattr(im, 'n_frames', 1) != 1:
                    raise ValueError('图片格式、尺寸或动画不受支持')
                im.verify()
            # verify() checks the container; load() also catches truncated pixel data.
            with Image.open(BytesIO(data)) as im:
                im.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError('图片数据损坏或尺寸过大') from exc
    return {'mime': mime, 'size': len(data), 'sha256': sha256(data).hexdigest(),
            'width': width, 'height': height}


def _atomic(path, data):
    descriptor, name = tempfile.mkstemp(prefix='.media-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class MediaStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data):
        metadata = validate_image(data)
        media_id = uuid4().hex
        metadata = {'media_id': media_id, **metadata}
        _atomic(self.root / (media_id + '.bin'), data)
        _atomic(self.root / (media_id + '.json'), json.dumps(metadata).encode('utf-8'))
        return metadata

    def read(self, media_id):
        validate_media_id(media_id)
        data_path = self.root / (media_id + '.bin')
        meta_path = self.root / (media_id + '.json')
        if data_path.resolve().parent != self.root or meta_path.resolve().parent != self.root:
            raise ValueError('无效媒体缓存位置')
        if data_path.stat().st_size > MAX_BYTES or meta_path.stat().st_size > 4096:
            raise ValueError('媒体缓存大小无效')
        data = data_path.read_bytes()
        try:
            metadata = json.loads(meta_path.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError) as exc:
            raise ValueError('媒体缓存元数据损坏') from exc
        expected = {'media_id': media_id, **validate_image(data)}
        if metadata != expected:
            raise ValueError('媒体缓存校验不匹配')
        return data, metadata
