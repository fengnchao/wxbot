"""Local Telegram login, receive-only relay, and read-only status."""
import argparse
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
import signal

from butler.config import load as load_butler
from .config import load
from .client import FatalTelegramError, TelegramSource, login
from .service import Relay, instance_lock, read_subscribers
from .store import Store

ROOT = Path(__file__).resolve().parents[2]


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def status(cfg):
    path = cfg.state_path / 'relay.sqlite3'
    if not path.is_file():
        return {'status': 'not_started', 'sources': list(cfg.sources), 'enabled': cfg.enabled}
    store = Store(path, readonly=True)
    try:
        return {'status': 'saved_snapshot', 'enabled': cfg.enabled, **store.status()}
    finally:
        store.close()


async def run(cfg, butler_cfg, store):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.getsignal(sig)
        signal.signal(sig, lambda *args: loop.call_soon_threadsafe(stop.set))
    try:
        await Relay(cfg, butler_cfg, store, TelegramSource(cfg)).run(stop)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'login', 'run', 'status'))
    parser.add_argument('--config', default=str(ROOT / 'config.telegram.toml'))
    parser.add_argument('--butler-config', help='覆盖 Telegram 配置中的 Butler 配置文件路径')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            import tomlkit
            from butler.defaults import telegram_defaults
            from butler.setup import _new
            created=_new(Path(args.config).resolve(),tomlkit.dumps(telegram_defaults()))
            emit({'ok':True,'created':created,'config':str(Path(args.config).resolve())})
            return 0
        cfg = load(args.config, butler_config=args.butler_config)
        if args.command == 'status':
            emit(status(cfg))
            return 0
        if args.command == 'run' and not cfg.enabled:
            raise FatalTelegramError('Telegram 接收未启用；请在本机配置中设置 enabled=true')
        bc = None
        if args.command == 'run':
            if not cfg.butler_config.is_file():
                raise FatalTelegramError('指定的 Butler 配置文件不存在')
            bc = load_butler(cfg.butler_config)
            read_subscribers(bc.group_file_path())
        session = str(cfg.session_path)
        if not session.endswith('.session'):
            session += '.session'
        with ExitStack() as stack:
            stack.enter_context(instance_lock(cfg.state_path / 'run.lock'))
            stack.enter_context(instance_lock(Path(session + '.relay.lock')))
            if args.command == 'login':
                emit(asyncio.run(login(cfg)))
                return 0
            store = Store(cfg.state_path / 'relay.sqlite3')
            try:
                emit({'status': 'starting', 'sources': list(cfg.sources),
                      'note': '首次启用跳过历史；Ctrl+C 停止接收并等待当前投递回执'})
                asyncio.run(run(cfg, bc, store))
                emit({'status': 'stopped', **store.status()})
            finally:
                store.close()
        return 0
    except KeyboardInterrupt:
        emit({'status': 'interrupted'})
        return 130
    except Exception as exc:
        report = {'status': 'failed', 'error_type': type(exc).__name__}
        if isinstance(exc, FatalTelegramError):
            report['reason'] = str(exc)
        else:
            report['reason'] = '请检查配置和 telegram status；错误原文已隐藏以保护认证信息'
        emit(report)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
