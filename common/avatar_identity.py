"""Shared, versioned avatar normalization; no desktop or clipboard access."""
import base64
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_AVATAR_BYTES = 512 * 1024
MAX_AVATAR_PIXELS = 4_000_000
ALGORITHM = 'dhash-v1'


def decode_avatar(value):
    if not isinstance(value, str) or len(value) > MAX_AVATAR_BYTES * 4 // 3 + 128:
        raise ValueError('头像超过 512 KiB 或格式无效')
    if value.startswith('data:'):
        header, separator, value = value.partition(',')
        if not separator or header not in {'data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64'}:
            raise ValueError('仅支持 PNG/JPEG/WebP 头像')
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise ValueError('头像编码无效') from None


def normalize_avatar(data):
    if not isinstance(data, bytes) or not data or len(data) > MAX_AVATAR_BYTES:
        raise ValueError('头像超过 512 KiB 或内容为空')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {'PNG', 'JPEG', 'WEBP'} or source.width * source.height > MAX_AVATAR_PIXELS:
                    raise ValueError('头像格式无效或像素数超过 400 万')
                if min(source.size) < 16:
                    raise ValueError('头像至少为 16×16 像素')
                source.load()
                rgba = ImageOps.exif_transpose(source).convert('RGBA')
                background = Image.new('RGBA', rgba.size, (31, 31, 31, 255))
                background.alpha_composite(rgba)
                image = ImageOps.fit(background.convert('RGB'), (36, 36), method=Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('无法解码头像图片') from None
    gray = image.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = bits << 1 | int(gray.getpixel((x, y)) > gray.getpixel((x + 1, y)))
    stream = BytesIO()
    image.save(stream, format='PNG')
    return {'image': base64.b64encode(stream.getvalue()).decode('ascii'), 'hash': f'{bits:016x}', 'algorithm': ALGORITHM}


def avatar_distance(first, second):
    """Conservative matching combines structure with actual color pixels."""
    a = normalize_avatar(decode_avatar(first))
    b = normalize_avatar(decode_avatar(second))
    left = Image.open(BytesIO(base64.b64decode(a['image']))).convert('RGB')
    right = Image.open(BytesIO(base64.b64decode(b['image']))).convert('RGB')
    error = sum(abs(x - y) for x, y in zip(left.tobytes(), right.tobytes())) / (36 * 36 * 3)
    return (int(a['hash'], 16) ^ int(b['hash'], 16)).bit_count(), error
