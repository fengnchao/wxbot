"""Shared news catalogue and settings for the dashboard and daily collector."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time


CATEGORIES = {
    'domestic': '国内', 'world': '国际', 'society': '社会', 'finance': '财经',
    'culture': '文娱', 'sports': '体育', 'education': '教育', 'health': '健康',
    'life': '生活',
}
FEEDS = {
    'domestic': 'china', 'world': 'world', 'society': 'society', 'finance': 'finance',
    'culture': 'culture', 'sports': 'sports', 'education': 'edu', 'health': 'jk', 'life': 'life',
}
SOURCES = {
    'cns_top': {'label': '中新网 · 要闻导读', 'description': '编辑精选的综合要闻',
                'url': 'https://www.chinanews.com.cn/rss/importnews.xml'},
    'cns_latest': {'label': '中新网 · 即时新闻', 'description': '覆盖更广，按发布时间筛选',
                   'url': 'https://www.chinanews.com.cn/rss/scroll-news.xml'},
    'cns_categories': {'label': '中新网 · 分类频道', 'description': '按所选新闻类型读取对应频道',
                       'url': 'https://www.chinanews.com.cn/rss/'},
}
DEFAULTS = {'categories': ['domestic', 'world', 'society', 'finance'],
            'sources': ['cns_top', 'cns_categories'], 'count': 5}


def settings_path(groups_path):
    path = Path(groups_path)
    return path.with_name(path.stem + '.news.json')


def runtime_path(groups_path):
    path = Path(groups_path)
    return path.with_name(path.stem + '.news')


class NewsConflict(ValueError):
    pass


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name,
                                         suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            file.write((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def save_settings(groups_path, settings, version):
    """Caller holds the dashboard's config_lock for this sidecar file."""
    settings = validate(settings)
    path = settings_path(groups_path)
    content = path.read_bytes() if path.exists() else b''
    if not isinstance(version, str) or sha256(content).hexdigest() != version:
        raise NewsConflict('新闻配置已被修改，当前草稿已保留；请刷新、取消旧草稿后重新编辑')
    if content:
        backup = path.with_name(path.name + '.config-backup-' + str(time.time_ns()))
        with backup.open('xb') as file:
            file.write(content)
    atomic_json(path, {'version': 1, 'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'news': settings})


def validate(settings):
    if not isinstance(settings, dict) or set(settings) != set(DEFAULTS):
        raise ValueError('新闻配置须包含 categories、sources、count')
    result = {}
    for field, catalogue, label in (
            ('categories', CATEGORIES, '新闻类型'), ('sources', SOURCES, '新闻来源')):
        values = settings[field]
        if (not isinstance(values, list) or not values or len(values) > len(catalogue)
                or any(not isinstance(v, str) or v not in catalogue for v in values)
                or len(set(values)) != len(values)):
            raise ValueError(f'{label}至少选择一项，且不能包含重复或未知选项')
        result[field] = list(values)
    if type(settings['count']) is not int or not 1 <= settings['count'] <= 10:
        raise ValueError('每日新闻条数须为 1–10 的整数')
    result['count'] = settings['count']
    return result


def read_settings(groups_path):
    path = settings_path(groups_path)
    content = path.read_bytes() if path.exists() else b''
    version = sha256(content).hexdigest()
    if not content:
        return deepcopy(DEFAULTS), version
    raw = json.loads(content.decode('utf-8-sig'))
    if not isinstance(raw, dict) or raw.get('version') != 1:
        raise ValueError('新闻配置文件版本或格式无效')
    return validate(raw.get('news')), version


def payload(groups_path):
    error = ''
    try:
        settings, version = read_settings(groups_path)
    except (OSError, ValueError, UnicodeError) as exc:
        settings, version = None, ''
        error = '新闻配置无法读取，请检查文件格式（' + type(exc).__name__ + '）'
    try:
        latest = json.loads((runtime_path(groups_path) / 'latest.json').read_text(encoding='utf-8'))
        latest = {key: latest.get(key) for key in ('date', 'status', 'article_count', 'sent', 'uncertain', 'updated_at')}
    except (OSError, ValueError, AttributeError):
        latest = None
    return {'settings': settings, 'version': version, 'error': error, 'latest': latest,
            'file': str(settings_path(groups_path)),
            'categories': [{'id': key, 'label': value} for key, value in CATEGORIES.items()],
            'sources': [{'id': key, **value} for key, value in SOURCES.items()],
            'schedule': '每天 09:00（北京时间，由 Codex 定时任务触发）',
            'note': '保存后下次任务生效；最近24小时，去重后最多发送设定条数。所有订阅者共用此配置。'}
