"""Read-only browsing in a dedicated Edge profile."""
from contextlib import contextmanager
from dataclasses import dataclass
import math
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urljoin, urlsplit


FEED_URL = 'https://www.douyin.com/?recommend=1&from_nav=1'
VIDEO_ID = re.compile(r'[0-9]{3,24}')
PAGE_TIMEOUT_MS = 2500
VERIFICATION_WAIT_SECONDS = 600

_SNAPSHOT = r'''(body, playId) => {
    const visible = node => {
        const r = node.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(node).visibility !== 'hidden';
    };
    const blocked = [...body.querySelectorAll(
        '#uc-second-verify, #captcha_verify_container, [id^="captcha_container"], ' +
        '[data-e2e="captcha-container"], iframe[src*="captcha"], ' +
        '[data-e2e="login-modal"], [data-e2e="login-mask"], #login-pannel')].some(visible) ||
        [...body.querySelectorAll('[role="dialog"]')].some(el => visible(el) &&
            /扫码登录|登录后继续|安全验证|完成验证/.test(el.innerText || ''));
    if (blocked || /\/(login|verify|captcha)(?:\/|$)/.test(location.pathname)) return {blocked: true};
    if (location.hostname !== 'www.douyin.com' ||
        !/^\/(?:recommend\/?|video\/\d+)?$/.test(location.pathname)) return null;
    const active = '[data-e2e="feed-active-video"], [data-e2e="video-detail"]';
    const videos = [...body.querySelectorAll('video')].filter(video => visible(video) &&
        !video.closest('[data-e2e="im-dialog"], [data-e2e="conversation-item"]'));
    const area = el => {
        const r = el.getBoundingClientRect();
        return Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0)) *
            Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    };
    const video = videos.sort((a, b) => area(b) - area(a))[0];
    if (!video || area(video) < 100) return null;
    const item = video.closest(active) || video.closest('[data-aweme-id], [data-e2e="feed-video"]');
    const classId = node => node?.className?.match(/(?:^|\s)video_(\d+)(?:\s|$)/)?.[1];
    const playerId = classId(video.closest('[data-e2e="player-container"]'));
    const itemId = classId(item) || item?.getAttribute('data-aweme-id');
    const url = new URL(location.href);
    const pathId = url.pathname.match(/^\/video\/(\d+)$/)?.[1];
    const pageId = pathId || url.searchParams.get('modal_id');
    const ids = new Set([playerId, itemId, pageId].filter(Boolean));
    if (ids.size > 1) return null;
    const id = playerId || itemId || pageId ||
        item?.querySelector('a[href*="/video/"]')?.pathname.match(/^\/video\/(\d+)$/)?.[1];
    if (!id) return null;
    const caption = item?.querySelector('[data-e2e="video-desc"], [data-e2e="video-title"], ' +
        '[data-e2e="detail-video-info"], [class*="video-info-detail"]');
    const title = caption?.innerText?.split('\n')[0] ||
        (id === pathId ? document.querySelector('meta[property="og:title"]')?.content : '') || '';
    const canPlay = video.paused && !video.ended && video.readyState >= 2;
    if (playId === id && canPlay) {
        video.muted = true;
        void video.play().catch(() => {});
    }
    return {id, title, time: video.currentTime, source: video.currentSrc,
        playing: !video.paused && !video.seeking && !video.ended, canPlay};
}'''


class LoginRequired(Exception):
    """The account needs user attention in the dedicated profile."""


class BrowserUnavailable(Exception):
    """The optional browser runtime is missing."""


@dataclass(frozen=True)
class VideoObservation:
    video_id: str
    title: str
    seconds: float


def playback_delta(before, after, elapsed):
    """Count verified advancement on the same playable source."""
    if not before or not after or before['id'] != after['id'] or before.get('source') != after.get('source'):
        return 0
    if not before['playing'] or not after['playing']:
        return 0
    delta = after['time'] - before['time']
    return min(delta, elapsed) if math.isfinite(delta) and 0 < delta <= elapsed + 0.5 else 0


class DouyinBrowser:
    def __init__(self, profile: Path, *, headless=True):
        self.profile = profile
        self.headless = headless

    @contextmanager
    def _edge(self, *, headless):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise BrowserUnavailable('请安装 wxbot[resident]') from None
        self.profile.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(self.profile), channel='msedge', headless=headless,
                args=['--mute-audio'], timeout=8000,
            )
            try:
                yield context
            finally:
                context.close()

    @staticmethod
    def _logged_in(context):
        return any(cookie['name'] in {'sessionid', 'sessionid_ss'} and cookie['value']
                   for cookie in context.cookies(FEED_URL))

    def login(self):
        with self._edge(headless=False) as context:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(FEED_URL, wait_until='commit', timeout=8000)
            input('请在专用 Edge 中登录或处理验证，完成后保持窗口打开并按回车。')
            return self._logged_in(context)

    @staticmethod
    def _follow_recommend_link(page, should_stop):
        current = urlsplit(page.url)
        if (current.scheme, current.netloc, current.path.rstrip('/')) != ('https', 'www.douyin.com', '/jingxuan'):
            return False
        link = page.get_by_role('link', name='推荐', exact=True)
        if should_stop() or link.count() != 1:
            return False
        href = link.get_attribute('href', timeout=PAGE_TIMEOUT_MS)
        target = urlsplit(urljoin(page.url, href or ''))
        if (target.scheme, target.netloc) != ('https', 'www.douyin.com'):
            return False
        is_feed = (target.path.rstrip('/') == '/recommend' or
                   (target.path == '/' and parse_qs(target.query).get('recommend') == ['1']))
        if not is_feed or should_stop():
            return False
        link.click(timeout=PAGE_TIMEOUT_MS)
        return True

    def _wait_for_access(self, context, page, body, cancelled, interrupted, limit):
        deadline = time.monotonic() + limit
        followed_recommend_link = False
        while not cancelled() and time.monotonic() < deadline:
            if page.is_closed():
                break
            try:
                snapshot = body.evaluate(_SNAPSHOT, timeout=PAGE_TIMEOUT_MS)
                if snapshot and snapshot.get('id') and self._logged_in(context):
                    return
                if not snapshot and not followed_recommend_link:
                    followed_recommend_link = self._follow_recommend_link(page, lambda: (
                        cancelled() or interrupted() or time.monotonic() >= deadline or not self._logged_in(context)))
            except Exception:
                # User verification can navigate the tab and invalidate an in-flight read.
                if page.is_closed():
                    break
            time.sleep(max(0, min(1, deadline - time.monotonic())))
        if not cancelled():
            raise LoginRequired()

    def watch(self, limit, interrupted, observed, *, cancelled=None, on_verification=None):
        cancelled = interrupted if cancelled is None else cancelled
        if interrupted():
            return
        if self.headless and not self.profile.is_dir():
            raise LoginRequired()
        deadline = time.monotonic() + limit
        with self._edge(headless=self.headless) as context:
            if interrupted() or time.monotonic() >= deadline:
                return
            needs_login = not self._logged_in(context)
            if needs_login and self.headless:
                raise LoginRequired()
            page = context.pages[0] if context.pages else context.new_page()
            remaining = deadline - time.monotonic()
            if interrupted() or remaining <= 0:
                return
            page.goto(FEED_URL, wait_until='commit', timeout=min(8000, remaining * 1000))
            body = page.locator('body')
            previous, sampled_at = None, time.monotonic()
            watched = 0.0
            next_at = sampled_at + 12
            awaiting = ''
            attempted_play = ''
            wait_left = VERIFICATION_WAIT_SECONDS
            followed_recommend_link = False
            while not interrupted() and time.monotonic() < deadline:
                current = None if needs_login else body.evaluate(_SNAPSHOT, timeout=PAGE_TIMEOUT_MS)
                now = time.monotonic()
                if needs_login or (current and current.get('blocked')):
                    if self.headless or wait_left <= 0:
                        raise LoginRequired()
                    if on_verification:
                        on_verification(True)
                    try:
                        self._wait_for_access(context, page, body, cancelled, interrupted, wait_left)
                    finally:
                        if on_verification:
                            on_verification(False)
                    if interrupted() or cancelled():
                        return
                    sampled_at = time.monotonic()
                    paused = sampled_at - now
                    deadline += paused
                    wait_left -= paused
                    needs_login = False
                    previous, watched, next_at = None, 0.0, sampled_at + 12
                    awaiting = attempted_play = ''
                    continue
                if not current and not followed_recommend_link:
                    followed_recommend_link = self._follow_recommend_link(
                        page, lambda: interrupted() or time.monotonic() >= deadline)
                    if followed_recommend_link:
                        sampled_at = time.monotonic()
                        previous, next_at = None, sampled_at + 12
                        continue
                if current and VIDEO_ID.fullmatch(current['id']):
                    if awaiting and current['id'] != awaiting:
                        awaiting, watched, next_at = '', 0.0, now + 12
                    delta = playback_delta(previous, current, min(now, deadline) - sampled_at)
                    if delta > 0 and not awaiting:
                        watched += delta
                        observed(VideoObservation(current['id'], current['title'], delta))
                    if (not awaiting and current.get('canPlay') and attempted_play != current['id']
                            and not interrupted() and time.monotonic() < deadline):
                        attempted_play = current['id']
                        body.evaluate(_SNAPSHOT, attempted_play, timeout=PAGE_TIMEOUT_MS)
                if now >= next_at and not interrupted() and now < deadline:
                    if awaiting or not current or not VIDEO_ID.fullmatch(current['id']):
                        break
                    awaiting = current['id']
                    next_video = page.locator('[data-e2e="video-switch-next-arrow"]:visible')
                    has_next_button = next_video.count() == 1
                    if interrupted() or time.monotonic() >= deadline:
                        break
                    if has_next_button:
                        next_video.click(timeout=PAGE_TIMEOUT_MS)
                    else:
                        body.press('ArrowDown', timeout=PAGE_TIMEOUT_MS)
                    next_at = now + 6
                elif watched >= 8:
                    next_at = min(next_at, now)
                previous, sampled_at = current, now
                # Wait briefly between snapshots, including on a paused or loading video.
                time.sleep(max(0, min(0.5, deadline - time.monotonic())))
