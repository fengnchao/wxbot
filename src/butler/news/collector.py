"""Bounded RSS fetches, deterministic selection and source-attributed digests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import re
import time
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import requests

from common.news_config import CATEGORIES, FEEDS, SOURCES, validate

CST = timezone(timedelta(hours=8))
MAX_FEED_BYTES = 2 * 1024 * 1024
PATH_CATEGORY = {
    'gn': 'domestic', 'ga': 'domestic', 'tw': 'domestic', 'dwq': 'domestic',
    'gj': 'world', 'sh': 'society', 'cj': 'finance', 'ty': 'sports',
    'wh': 'culture', 'yl': 'culture', 'cul': 'culture', 'edu': 'education',
    'jk': 'health', 'life': 'life',
}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        elif tag in ('br', 'p', 'div'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_text(value):
    parser = PlainText()
    parser.feed(value or '')
    text = re.sub(r'\s+', ' ', ''.join(parser.parts)).strip()
    return ''.join(c for c in text if c >= ' ' and c not in '\u202a\u202b\u202c\u202d\u202e')


def article_url(value):
    parts = urlsplit((value or '').strip())
    host = parts.hostname or ''
    if (parts.scheme not in ('http', 'https') or parts.username or parts.password
            or not (host == 'chinanews.com.cn' or host.endswith('.chinanews.com.cn'))):
        return None
    canonical = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
    return canonical if len(canonical) <= 200 else None


def publication_time(value):
    try:
        result = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            result = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None
    return result.replace(tzinfo=CST) if result.tzinfo is None else result


def feed_requests(settings):
    feeds = []
    for source in settings['sources']:
        if source == 'cns_categories':
            feeds.extend((source, category, SOURCES[source]['url'] + FEEDS[category] + '.xml')
                         for category in settings['categories'])
        else:
            feeds.append((source, None, SOURCES[source]['url']))
    return feeds


def fetch_feed(spec, now):
    source, category, url = spec
    report = {'source': source, 'category': category, 'url': url, 'status': 'ok', 'count': 0}
    try:
        started = time.monotonic()
        # Only publisher catalogue URLs are requested; no article crawling or arbitrary URLs.
        with requests.get(url, timeout=(5, 12), stream=True, allow_redirects=False,
                          headers={'User-Agent': 'ButlerNews/1.0 RSS Reader'}) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError('unexpected RSS response')
            content = bytearray()
            for chunk in response.iter_content(16384):
                content.extend(chunk)
                if len(content) > MAX_FEED_BYTES or time.monotonic() - started > 25:
                    raise ValueError('RSS response exceeds size or time budget')
        if b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
            raise ValueError('unsupported RSS declarations')
        root = ET.fromstring(content)
        if root.tag != 'rss':
            raise ValueError('not an RSS feed')
        articles = []
        for item in root.findall('./channel/item')[:200]:
            title = clean_text(item.findtext('title'))
            link = article_url(item.findtext('link'))
            published = publication_time(item.findtext('pubDate'))
            if (not title or len(title) > 160 or not link or not published
                    or not now - timedelta(hours=24) <= published <= now):
                continue
            guessed = PATH_CATEGORY.get(urlsplit(link).path.strip('/').split('/')[0])
            kind = category or guessed
            if kind not in CATEGORIES:
                continue
            articles.append({'title': title, 'url': link, 'category': kind,
                             'source': source, 'publisher': '中国新闻网',
                             'published_at': published.astimezone(CST).isoformat(),
                             'description': clean_text(item.findtext('description'))[:1000]})
        report['count'] = len(articles)
        if not articles:
            report['status'] = 'empty_or_stale'
        return articles, report
    except (requests.RequestException, ValueError, ET.ParseError, UnicodeError) as exc:
        report.update(status='failed', error_type=type(exc).__name__)
        return [], report


def title_key(title):
    return re.sub(r'[\W_]+', '', title).casefold()


def select_articles(articles, settings):
    candidates = sorted(articles, key=lambda a: (a['published_at'], a['url']), reverse=True)
    buckets = {category: [] for category in settings['categories']}
    for article in candidates:
        if article['category'] in buckets:
            buckets[article['category']].append(article)
    selected, urls, titles = [], set(), []
    # Cycle categories to avoid one busy feed monopolizing the digest.
    while len(selected) < settings['count'] and any(buckets.values()):
        for category, rows in buckets.items():
            while rows:
                article = rows.pop(0)
                key = title_key(article['title'])
                if article['url'] in urls or any(SequenceMatcher(None, key, old).ratio() >= .86 for old in titles):
                    continue
                urls.add(article['url'])
                titles.append(key)
                selected.append(article)
                break
            if len(selected) == settings['count']:
                break
    return selected


def render_digest(articles, now):
    lines = [f'每日早报｜{now.astimezone(CST):%Y-%m-%d}', '近24小时资讯 · 来源：中国新闻网']
    for index, article in enumerate(articles, 1):
        lines.extend(['', f'{index}.【{CATEGORIES[article["category"]]}】{article["title"]}'])
        # Quote only a short complete source sentence, never generate unsupported facts.
        description = article['description']
        sentence = re.match(r'^(.{8,60}?[。！？])', description)
        if sentence and title_key(sentence[1]) != title_key(article['title']):
            lines.append('原文摘要：' + sentence[1])
        lines.append(article['url'])
    return '\n'.join(lines)


def collect(settings, now=None):
    settings = validate(settings)
    now = now or datetime.now(CST)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda spec: fetch_feed(spec, now), feed_requests(settings)))
    candidates = [article for articles, _ in results for article in articles]
    selected = select_articles(candidates, settings)
    return {'generated_at': now.isoformat(), 'settings': settings, 'articles': selected,
            'sources': [report for _, report in results],
            'text': render_digest(selected, now) if selected else '',
            'status': 'ready' if selected else 'no_news'}
