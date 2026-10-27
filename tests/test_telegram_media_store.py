from io import BytesIO
import re

from PIL import Image
import pytest


def picture(fmt='PNG'):
    out = BytesIO()
    Image.new('RGB', (3, 2), 'red').save(out, fmt)
    return out.getvalue()


def test_store_validates_real_images_and_detects_cache_corruption(tmp_path):
    from butler.media import MediaStore
    store = MediaStore(tmp_path)
    meta = store.put(picture())
    assert re.fullmatch('[0-9a-f]{32}', meta['media_id'])
    assert (meta['mime'], meta['width'], meta['height']) == ('image/png', 3, 2)
    data, read_meta = store.read(meta['media_id'])
    assert data == picture() and read_meta == meta
    (tmp_path / (meta['media_id'] + '.bin')).write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        store.read(meta['media_id'])


@pytest.mark.parametrize('data', [b'not image', b'x' * (20 * 1024 * 1024 + 1), picture('GIF')], ids=['corrupt', 'oversize', 'gif'])
def test_store_rejects_corrupt_large_and_unsupported_images(tmp_path, data):
    from butler.media import MediaStore
    with pytest.raises(ValueError):
        MediaStore(tmp_path).put(data)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('value', ['../auth', 'https://example/a', 'A' * 32, 'a' * 31, None])
def test_store_rejects_non_server_ids(tmp_path, value):
    from butler.media import MediaStore
    with pytest.raises(ValueError):
        MediaStore(tmp_path).read(value)


@pytest.mark.parametrize('items', [[], [{'kind': 'image', 'media_id': 'a' * 32, 'path': 'secret'}],
    [{'kind': 'image', 'media_id': '../x'}], [{'kind': 'text', 'text': ''}],
    [{'kind': 'text', 'text': 'x'}] * 51, [{'kind': 'image', 'url': 'http://x'}]])
def test_bundle_rejects_arbitrary_fields_paths_and_unbounded_items(items):
    from common.media_bundle import validate_items
    with pytest.raises(ValueError):
        validate_items(items)


def test_bundle_retains_text_image_order():
    from common.media_bundle import validate_items
    items = [{'kind': 'text', 'text': 'caption'}, {'kind': 'image', 'media_id': 'a' * 32}]
    assert validate_items(items) == items
