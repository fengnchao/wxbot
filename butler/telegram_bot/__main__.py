"""python -m butler.telegram_bot init|run|status|retry-media [--config PATH]."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tomllib

from butler.config import load as load_butler
from .config import DEFAULT, ROOT, load
from .inbox import recent
from .service import TelegramError
from .news import MediaRetryError


def status(path):
    path = Path(path).resolve()
    raw = tomllib.loads(path.read_text(encoding='utf-8-sig'))['telegram_bot']
    cfg = load_butler(path.parent / raw.get('butler_config', 'config.butler.toml'))
    queue_path = (path.parent / raw.get('state_dir', 'data/telegram-bot') / 'relay.sqlite3').resolve()
    result = {'relay': [], 'news_plan': [], 'news_delivery': [], 'news_package': [], 'news_bundle_delivery': [],
              'butler_received': recent(cfg.data_path() / 'telegram-bot' / 'inbox.sqlite3')}
    if queue_path.exists():
        with closing(sqlite3.connect(queue_path.as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            result['relay'] = [dict(row) for row in db.execute(
                'SELECT bot,uid,state,error FROM pending ORDER BY rowid DESC LIMIT 20')]
            if 'news_plan' in tables:
                result['news_plan'] = [dict(row) for row in db.execute(
                    'SELECT bot,uid,reason FROM news_plan ORDER BY rowid DESC LIMIT 20')]
            if 'news_delivery' in tables:
                result['news_delivery'] = [dict(row) for row in db.execute(
                    'SELECT id,bot,uid,contact,part,state,reason,updated FROM news_delivery ORDER BY id DESC LIMIT 50')]
            if 'news_package' in tables:
                result['news_package'] = [dict(row) for row in db.execute('''
                    SELECT bot,package_key,uid,sender,state,reason,json_array_length(items) item_count
                    FROM news_package ORDER BY rowid DESC LIMIT 50''')]
            if 'news_bundle_delivery' in tables:
                result['news_bundle_delivery'] = [dict(row) for row in db.execute('''
                    SELECT id,bot,package_key,contact,request_id,state,reason,updated
                    FROM news_bundle_delivery ORDER BY id DESC LIMIT 50''')]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'run', 'status', 'retry-media'])
    parser.add_argument('--config', default=str(DEFAULT))
    parser.add_argument('--bot-id',type=int)
    parser.add_argument('--package-key')
    args = parser.parse_args()
    if args.command=='retry-media' and (args.bot_id is None or not args.package_key):
        parser.error('retry-media 需要 --bot-id 和 --package-key')
    try:
        path = Path(args.config).resolve()
        if args.command == 'init':
            if path.exists():
                print('配置已存在，保留原文件：' + str(path))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('x', encoding='utf-8') as output:
                    output.write((ROOT / 'config.telegram-bot.example.toml').read_text(encoding='utf-8'))
                print('已生成配置，请在本机填写 token 和 allowed_user_ids：' + str(path))
        elif args.command == 'status':
            print(json.dumps(status(path), ensure_ascii=False, indent=2))
        elif args.command == 'retry-media':
            from .news import retry_media_preparation
            raw = tomllib.loads(path.read_text(encoding='utf-8-sig'))['telegram_bot']
            queue_path = (path.parent / raw.get('state_dir','data/telegram-bot') / 'relay.sqlite3').resolve()
            print(json.dumps(retry_media_preparation(queue_path,args.bot_id,args.package_key),ensure_ascii=False,indent=2))
        else:
            from .service import run
            cfg = load(path)
            run(cfg, load_butler(cfg.butler_config))
    except KeyboardInterrupt:
        print('接收已停止，待提交消息保留。')
    except TelegramError as exc:
        # This exception renders only controlled diagnostic text, never URL/token.
        print('启动/运行失败：' + str(exc))
        return 1
    except MediaRetryError as exc:
        print('媒体准备重试被拒绝：'+str(exc))
        return 1
    except Exception as exc:
        # Config parser/network error strings may contain credentials: print only type.
        print('启动/运行失败：' + type(exc).__name__ + '；请检查本机配置、代理及前面的阶段日志。')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
