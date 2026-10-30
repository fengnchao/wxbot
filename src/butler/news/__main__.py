"""python -m butler.news [--preview] [--config PATH]. No services are started."""
import argparse
import json

from butler.config import load
from common.news_config import read_settings
from butler.news.collector import collect
from butler.news.delivery import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    parser.add_argument('--preview', action='store_true', help='仅获取和输出简报，不发送或写发送状态')
    args = parser.parse_args()
    try:
        cfg = load(args.config)
        result = collect(read_settings(cfg.group_file_path())[0]) if args.preview else run(cfg)
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in ('ready', 'sent', 'no_subscribers', 'legacy_run_exists') else 1


if __name__ == '__main__':
    raise SystemExit(main())
