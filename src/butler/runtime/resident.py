"""Lifecycle and local diary for Butler's resident role."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import threading
import time
from uuid import uuid4

from butler.runtime.knowledge_auto import acquire, release
from butler.runtime.resident_douyin import BrowserUnavailable, DouyinBrowser, LoginRequired


SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')
POLL_SECONDS = 5


class ForegroundActivity:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._last_finished = clock()
        self._active = 0
        self._lock = threading.Lock()

    @contextmanager
    def request(self):
        with self._lock:
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
                self._last_finished = self._clock()

    def idle_for(self, seconds):
        with self._lock:
            return self._active == 0 and self._clock() - self._last_finished >= seconds


def resident_root(cfg):
    return cfg.data_path() / 'resident' / 'xiao-chao'


def atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.name}.{uuid4().hex}.tmp')
    try:
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def login_douyin(cfg):
    root = resident_root(cfg)
    if not DouyinBrowser(root / 'edge').login():
        return False
    atomic_text(root / 'login-ready', uuid4().hex)
    return True


def _model_note(cfg, root, clips):
    from butler.config import load

    if cfg.config_path:
        cfg = load(cfg.config_path)
    if cfg.provider not in {'openai', 'ollama'}:
        return ''
    from butler.backends.compatible import CompatibleBackend
    from butler.identity.contacts import Contact

    role = (cfg.plugin_path() / 'resident' / 'xiao-chao.md').read_text(encoding='utf-8')
    settings = {**cfg.model_config, 'system_prompt': '', 'max_history': 1}
    backend = CompatibleBackend(replace(cfg, data_dir=str(root / 'model'), model_config=settings))
    try:
        return backend.chat(Contact(name='小潮', profile='resident', uid='xiao-chao'),
                            json.dumps(clips, ensure_ascii=False), extra_system=role,
                            timeout=8, session_kind='resident')
    finally:
        backend.close()


def _plain(value, length):
    text = ' '.join(value.split())[:length]
    return text.translate({ord(c): '\\' + c for c in '\\`*{}[]<>#_!|'})


class ResidentRole:
    def __init__(self, cfg, activity, *, log=None, browser=None, clock=time.time,
                 elapsed_clock=time.monotonic, note=_model_note):
        self.cfg = cfg
        self.settings = cfg.resident_role
        self.activity = activity
        self.root = resident_root(cfg)
        self.browser = browser if browser is not None else DouyinBrowser(
            self.root / 'edge', headless=not self.settings.visible_browser)
        self.clock = clock
        self.elapsed_clock = elapsed_clock
        self.log = log or (lambda *args: None)
        self.note = note
        self._stop = threading.Event()
        self._thread = None

    def _load_state(self):
        try:
            state = json.loads((self.root / 'state.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}
        if (not isinstance(state, dict) or not isinstance(state.get('day'), str) or
                any(type(state.get(key)) not in (float, int) or not math.isfinite(state[key]) or state[key] < 0
                    for key in ('used_seconds', 'next_at'))):
            raise ValueError('Invalid resident role state')
        return state

    def _save_state(self, state):
        atomic_text(self.root / 'state.json', json.dumps(state, ensure_ascii=False, indent=2) + '\n')

    def _login_marker(self):
        try:
            return (self.root / 'login-ready').read_text(encoding='utf-8')
        except FileNotFoundError:
            return ''

    def _interrupted(self):
        return self._stop.is_set() or not self.activity.idle_for(self.settings.idle_seconds)

    def tick(self):
        if not self.settings.enabled or self._interrupted():
            return False
        handle = acquire(self.root / 'watch.lock')
        if handle is None:
            return False
        try:
            return self._run_if_due()
        finally:
            release(handle)

    def _run_if_due(self):
        now = self.clock()
        day = datetime.fromtimestamp(now, SHANGHAI).date().isoformat()
        state = self._load_state()
        marker = self._login_marker()
        visible = self.settings.visible_browser
        if (state.get('status') == 'login_required' and state.get('login_marker') == marker
                and state.get('visible_browser', False) == visible):
            return False
        if now < state.get('next_at', 0) or self._interrupted():
            return False
        used = state['used_seconds'] if state.get('day') == day else 0.0
        seconds_until_midnight = 86400 - (now + 8 * 3600) % 86400
        limit = min(self.settings.round_seconds, self.settings.daily_seconds - used, seconds_until_midnight)
        if limit < 1:
            return False

        run_id = uuid4().hex
        # A crash retains the reservation and cooldown. Clean completion refunds unused time.
        reservation = {'day': day, 'used_seconds': used + limit, 'status': 'watching',
                       'next_at': now + limit + self.settings.cooldown_seconds, 'visible_browser': visible}
        self._save_state(reservation)
        clips = {}
        elapsed = 0.0
        paused = 0.0
        waiting_since = 0.0

        def observed(video):
            nonlocal elapsed
            seconds = min(video.seconds, limit - elapsed)
            if seconds <= 0:
                return
            elapsed += seconds
            clip = clips.setdefault(video.video_id, {'title': '', 'seconds': 0.0,
                'url': 'https://www.douyin.com/video/' + video.video_id})
            clip['title'] = clip['title'] or ' '.join(video.title.split())[:200]
            clip['seconds'] += seconds

        def verification(waiting):
            nonlocal paused, waiting_since
            if waiting:
                waiting_since = self.elapsed_clock()
                self._save_state({**reservation, 'status': 'verification_required'})
                self.log('小潮暂停观看，请在当前的专用 Edge 窗口处理抖音登录或安全验证。')
            else:
                paused += self.elapsed_clock() - waiting_since
                self._save_state(reservation)

        def interrupted():
            return self._interrupted() or self.clock() >= now + seconds_until_midnight

        status = 'no_playback'
        diary_name = ''
        started = self.elapsed_clock()
        try:
            options = {'cancelled': self._stop.is_set, 'on_verification': verification} if visible else {}
            self.browser.watch(limit, interrupted, observed, **options)
            if interrupted():
                status = 'interrupted'
            elif clips:
                status = 'watched'
        except LoginRequired:
            status = 'login_required'
            self.log('小潮等待抖音登录或验证。处理入口：python -m butler resident-login')
        except BrowserUnavailable:
            status = 'browser_unavailable'
            self.log('小潮缺少浏览器依赖。请按 README 安装项目的 resident 可选依赖。')
        except Exception as exc:
            status = 'browser_error'
            self.log('小潮浏览失败：%s', type(exc).__name__)
        # Loading and switch transitions may play video without producing diary evidence.
        charged = min(limit, max(elapsed, self.elapsed_clock() - started - paused))
        try:
            if clips:
                diary_name = self._write_diary(day, run_id, list(clips.values()))
        finally:
            # An initial login can resume promptly; a round with playback keeps its cooldown.
            next_at = 0 if status == 'login_required' and not clips else self.clock() + self.settings.cooldown_seconds
            self._save_state({'day': day, 'used_seconds': used + charged, 'status': status,
                              'next_at': next_at, 'login_marker': marker, 'diary': diary_name,
                              'visible_browser': visible})
        self.log('小潮活动结束：%s，记录 %d 条作品', status, len(clips))
        return True

    def _write_diary(self, day, run_id, clips):
        evidence = [{**clip, 'seconds': round(clip['seconds'], 1)} for clip in clips]
        note = ''
        if not self._interrupted():
            try:
                note = _plain(self.note(self.cfg, self.root, evidence), 220)
            except Exception as exc:
                self.log('小潮改用事实日记：%s', type(exc).__name__)
        if not note:
            note = f'空闲时翻了翻抖音，记下了 {len(clips)} 条有播放记录的作品。'
        lines = [f'# 小潮的日记 · {day}', '', note, '', '网页播放记录', '']
        for clip in evidence:
            title = _plain(clip['title'], 200) or '网页未提供可核对的标题'
            lines.append(f"- {title}（约 {clip['seconds']:g} 秒） [作品]({clip['url']})")
        name = f'{day}-{run_id}.md'
        atomic_text(self.root / 'diary' / name, '\n'.join(lines) + '\n')
        return name

    def start(self):
        if not self.settings.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='butler-resident-xiao-chao', daemon=True)
        self._thread.start()
        self.log('小潮常驻角色已启动。')

    def _loop(self):
        while not self._stop.is_set():
            delay = POLL_SECONDS
            try:
                self.tick()
            except Exception as exc:
                self.log('小潮后台轮次失败：%s', type(exc).__name__)
                delay = 60
            self._stop.wait(delay)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=12)
