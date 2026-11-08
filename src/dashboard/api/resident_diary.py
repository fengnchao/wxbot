"""Read the resident role's published diary files from the configured data root."""
import re
import stat

from butler.config import load
from butler.runtime.resident import resident_root


PAGE_SIZE = 20
MAX_BYTES = 64 * 1024
_DIARY = re.compile(r'(\d{4}-\d{2}-\d{2})-[0-9a-f]{32}\.md')
_VIDEO = re.compile(r'- (.+)（约 (\d+(?:\.\d+)?) 秒） \[作品\]\((https://www\.douyin\.com/video/\d{3,24})\)')
_MARKDOWN_ESCAPE = re.compile(r'\\([\\`*{}\[\]<>#_!|])')


def _entry(path, day, updated_at):
    if path.resolve() != path:
        return None
    with path.open('rb') as source:
        content = source.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        return None
    body = content.decode('utf-8').replace('\r\n', '\n').removeprefix(f'# 小潮的日记 · {day}\n').strip()
    note, separator, record = body.partition('\n\n网页播放记录\n\n')
    videos = []
    if separator:
        for line in record.splitlines():
            match = _VIDEO.fullmatch(line)
            if not match:
                note, videos = body, []
                break
            title, seconds, url = match.groups()
            videos.append({'title': _MARKDOWN_ESCAPE.sub(r'\1', title), 'seconds': seconds, 'url': url})
    return {'id': path.stem, 'date': day, 'updated_at': updated_at,
            'note': _MARKDOWN_ESCAPE.sub(r'\1', note), 'videos': videos}


def read(ctx):
    try:
        root = resident_root(load(ctx.butler_config_path())) / 'diary'
        if root.resolve() != root:
            raise ValueError('Redirected diary directory')
        try:
            paths = list(root.iterdir())
        except FileNotFoundError:
            paths = []
        files = []
        for path in paths:
            match = _DIARY.fullmatch(path.name)
            if not match:
                continue
            try:
                info = path.lstat()
                if stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES and path.resolve() == path:
                    files.append((match[1], info.st_mtime, path))
            except FileNotFoundError:
                continue
        files.sort(reverse=True)
        total = len(files)
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(pages, max(1, ctx.num('page', 1)))
        offset = (page - 1) * PAGE_SIZE
        entries = []
        for day, updated_at, path in files[offset:offset + PAGE_SIZE]:
            try:
                entry = _entry(path, day, updated_at)
            except FileNotFoundError:
                continue
            if entry is not None:
                entries.append(entry)
        return 200, {'entries': entries, 'page': page, 'pages': pages, 'total': total}
    except (OSError, RuntimeError, ValueError):
        return 500, {'error': '无法读取小潮日记，请刷新重试。'}
