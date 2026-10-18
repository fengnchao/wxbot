"""本地收发队列查看与异常恢复：python -m wxbot.queue_admin --help。"""
import argparse
import json
from pathlib import Path
import sys
import time

from .config import load_config
from .queue_store import QueueStore, queue_database


def main(argv=None):
    parser = argparse.ArgumentParser(description="查看 wxbot 队列，人工核对异常任务")
    parser.add_argument("--database", help="SQLite 文件路径；默认读取 wxbot 配置")
    parser.add_argument("--config", help="wxbot 配置路径")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="统计各状态数量（不修改任务状态）")
    listing = commands.add_parser("list", help="列出异常和未完成任务，不打印消息正文")
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--all", action="store_true", help="包含已完成任务")
    retry = commands.add_parser("retry", help="显式重试异常任务，可能重复执行工具或发送")
    retry.add_argument("id")
    retry.add_argument("--delivery", action="store_true", help="重试发件任务；默认重试模型批次")
    retry.add_argument("--acknowledge", action="store_true", help="已核对原操作结果并接受重试")
    sent = commands.add_parser("sent", help="人工确认指定发件任务已经发送")
    sent.add_argument("id")
    skip = commands.add_parser("skip", help="跳过异常任务，释放该会话的后续消息")
    skip.add_argument("id")
    skip.add_argument("--delivery", action="store_true", help="跳过发件任务；默认跳过模型批次")
    args = parser.parse_args(argv)
    if args.command == "retry" and not args.acknowledge:
        parser.error("重试可能重复执行工具或发送消息；核对微信/Butler 后加 --acknowledge")
    if args.command == "list" and args.limit < 1:
        parser.error("--limit 必须大于 0")
    store = None
    try:
        path = args.database or queue_database(load_config(args.config))
        if str(path) != ":memory:" and not Path(path).is_file():
            raise ValueError(f"队列数据库尚不存在：{path}")
        # 不占 UI 运行锁、不调用 recover，允许运行中查看。
        store = QueueStore(path, access='readonly' if args.command in {'status','list'} else 'admin')
        if args.command == "status":
            result = store.counts()
        elif args.command == "list":
            result = {}
            for table in ("batches", "outbox"):
                rows = store.records(table)
                if not args.all:
                    rows = [row for row in rows if row["state"] not in {"done", "sent", "skipped"}]
                result[table] = [{"id": row["id"], "contact": row["contact"], "state": row["state"],
                                  "characters": len(row["text"]), "error": row["error"],
                                  **({"part": f"{row['part_seq']}/{row['part_count']}"}
                                     if table == 'outbox' else {"progress": f"{row['completed_parts']}/{row['part_count']}"})}
                                 for row in rows[-args.limit:]]
        elif args.command == "retry":
            store.retry(args.id, delivery=args.delivery)
            result = {"id": args.id, "result": "已重新入队"}
        else:
            store.resolve(args.id, delivery=args.command == "sent" or args.delivery,
                          sent=args.command == "sent", now=time.time())
            result = {"id": args.id, "result": "已确认发送" if args.command == "sent" else "已跳过"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
