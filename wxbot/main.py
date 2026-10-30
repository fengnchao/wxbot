"""
启动收发服务：默认监听主微信窗口，兼容按绑定列表轮询独立聊天窗口。

运行：python -m wxbot.main
"""
import random
import time

from .dpi import set_dpi_aware

set_dpi_aware()

import uiautomation as auto  # noqa: E402

from .config import load_config
from .log import log
from .outbound import OutboundQueue, start_server
from .processor.base import EchoProcessor
from .processor.butler import ButlerProcessor
from .processor.ollama import OllamaProcessor
from .processor.openai_compat import OpenAICompatProcessor
from .processor.router import Router
from .state import new_messages
from .wechat.chat_window import ChatWindow
from .wechat.clipboard import restore_pending
from .inbox import mentioned_text as _mentioned_text, run_main_inbox


def build_processor(cfg: dict) -> Router:
    mcfg = dict(cfg.get("model", {}))
    backend = mcfg.get("backend", "ollama")
    mcfg.setdefault('provider',cfg.get('installation',{}).get('provider') or backend)
    if cfg.get('_config_dir') and backend in ('hermes', 'openclaw'):
        from pathlib import Path
        mcfg.setdefault('session_state', str(Path(cfg['_config_dir']) / 'data' / 'agent_sessions.sqlite3'))
    raise_errors = cfg.get("wechat", {}).get("mode", "main") == "main"
    if backend == "echo":
        model = EchoProcessor()
    elif backend == "butler":
        model = ButlerProcessor(cfg.get("butler", {}), raise_errors=raise_errors)
    elif backend in ("hermes", "openai"):
        model = OpenAICompatProcessor(mcfg, raise_errors=raise_errors)
    elif backend == "openclaw":
        model = OpenAICompatProcessor(mcfg, raise_errors=raise_errors)
    elif backend == "responses":
        from .processor.responses import ResponsesProcessor
        model = ResponsesProcessor(mcfg, raise_errors=raise_errors)
    elif backend == "cursor":
        from pathlib import Path
        from .processor.cursor import CursorProcessor
        cursor_cfg = dict(mcfg)
        if cursor_cfg.get('work_dir') and not Path(cursor_cfg['work_dir']).is_absolute():
            cursor_cfg['work_dir'] = str(Path(cfg.get('_config_dir', '.')) / cursor_cfg['work_dir'])
        model = CursorProcessor(cursor_cfg, raise_errors=raise_errors)
    elif backend != "ollama":
        raise ValueError(f"Unsupported model backend: {backend}")
    else:
        model = OllamaProcessor(mcfg, raise_errors=raise_errors)
    return Router(model, cfg["bot"].get("command_prefix", "/"))


def run() -> None:
    cfg = load_config()
    bcfg = cfg["bot"]
    router = build_processor(cfg)
    users = list(bcfg.get("bound_users", []))
    groups = list(bcfg.get("bound_groups", []))
    group_names = set(groups)
    chats = {name: ChatWindow(name, cfg["wechat"], group_mode=name in group_names)
             for name in dict.fromkeys(users + groups)}
    mention_names = bcfg.get("mention_names", [])
    snapshots: dict[str, list] = {}
    warned: set[str] = set()

    # 外发服务（8765）：接收主动推送请求入队，由下面的主循环在【本线程】代发（COM 线程亲和）
    ocfg = cfg.get("outbound", {})
    queue = OutboundQueue()
    if ocfg.get("enabled", True):
        host = ocfg.get("host", "127.0.0.1")
        port = ocfg.get("port", 8765)
        try:
            from pathlib import Path
            from .queue_store import queue_database
            media_cache=Path(queue_database(cfg)).resolve().parent/'wechat-media'
            start_server(host, port, str(ocfg.get("token", "")), queue,
                         butler_url=cfg.get('butler',{}).get('url',''),
                         butler_token=cfg.get('butler',{}).get('token',''),media_cache_dir=media_cache,
                         allow_bundles=cfg['wechat']['mode']=='main')
            log.info("外发服务已启动 → http://%s:%s（接收 butler/脚本的主动推送）", host, port)
        except Exception as e:
            if cfg["wechat"]["mode"] == "main":
                log.error("外发服务启动失败，停止启动主窗口收发: %s", e)
                raise RuntimeError("主窗口模式停止启动，请先检查是否已运行另一个 wxbot") from e
            log.error("外发服务启动失败（主动推送不可用，独立窗口轮询照常）: %s", e)

    if cfg["wechat"]["mode"] == "main":
        run_main_inbox(cfg, router, queue)
        return

    log.info("已绑定联系人：%s；群聊：%s。请在微信里把这些聊天打开为独立窗口。按 Ctrl+C 退出。",
             "、".join(users) or "(无)", "、".join(groups) or "(无)")
    if groups and not mention_names:
        log.warning("配置了群聊监听，但 [bot].mention_names 为空；群消息不会触发回复")

    while True:
        restore_pending()
        # 每轮先排空外发队列：在主线程调 ChatWindow.send，HTTP 线程绝不触碰 uiautomation
        for req in queue.drain():
            if req.items is not None:
                req.finish(False,'图文包只支持主窗口队列模式，未提交')
                continue
            chat = chats.get(req.contact)
            bound = chat is not None
            if chat is None:                       # 未绑定的目标：临时开窗发送
                chat = ChatWindow(req.contact, cfg["wechat"])
            if not chat.available():
                log.warning("[外发] %s 窗口不存在，推送失败", req.contact)
                req.finish(False, f"窗口不存在: {req.contact}")
                continue
            if chat.send(req.text):
                log.info("[外发] %s ✓ %s", req.contact, req.text[:60])
                req.finish(True, "sent")
            else:
                log.warning("[外发] %s 发送失败", req.contact)
                req.finish(False, "发送失败")
            if bound and req.contact in snapshots:  # 已绑定：刷新快照，避免下轮把自己发的当新消息
                snapshots[req.contact] = chat.read_messages()

        for name, chat in chats.items():
            if not chat.available():
                if name not in warned:
                    log.warning("[%s] 没找到独立聊天窗口，请双击会话打开", name)
                    warned.add(name)
                snapshots.pop(name, None)
                continue
            if name in warned:                  # 之前没找到、现在找到了 → 刚监听到窗口
                warned.discard(name)
                kind = "群聊" if name in group_names else "联系人"
                log.info("[%s] ✓ 监听到%s窗口", name, kind)

            msgs = chat.read_messages()
            if name not in snapshots:
                snapshots[name] = msgs          # 首次读取：只记录，不回复历史消息
                log.info("[%s] 窗口已连接，读到 %d 条历史消息（历史不回复）", name, len(msgs))
                continue

            new_all = new_messages(snapshots[name], msgs)
            snapshots[name] = msgs
            for m in new_all:                   # 每条新消息都打印，含发送方判断，便于调试
                if name in group_names:
                    speaker = m.sender_name or "未知成员"
                    log.info("[%s] 接收到新消息 [发言人=%s; member_id=%s]: %s",
                             name, speaker, m.sender_key or "unknown", m.text)
                else:
                    log.info("[%s] 接收到新消息 [发送方=%s]: %s", name, m.sender, m.text)

            fresh = []
            for m in new_all:
                if m.sender != "other":
                    continue
                text = m.text
                if name in group_names:
                    text = _mentioned_text(text, mention_names)
                    if text is None:
                        log.info("[%s] 群消息未 @机器人，跳过", name)
                        continue
                    log.info("[%s] 群消息 @机器人，交给处理器", name)
                fresh.append(m)
                context = (f"[群聊发言人：{m.sender_name or '未知成员'}; "
                           f"member_id={m.sender_key or 'unknown'}]"
                           if name in group_names else "")
                try:
                    reply = router.handle(name, text, context=context,
                                          member_key=m.sender_key or '',member_name=m.sender_name or '')
                except Exception as exc:
                    # Keep polling other conversations; exception text can contain
                    # remote response data or credentials and is not a chat reply.
                    log.error('[独立窗口] 模型请求失败，跳过本条：%s',type(exc).__name__)
                    continue
                if not reply:
                    log.info("[%s] （本条判定不回复）", name)
                    continue
                time.sleep(random.uniform(bcfg.get("reply_delay_min", 0.8), bcfg.get("reply_delay_max", 2.5)))
                if chat.send(reply):
                    log.info("[%s] 已回复: %s", name, reply[:60])

            if fresh:
                time.sleep(0.5)
                snapshots[name] = chat.read_messages()   # 把自己刚发的也纳入快照

        time.sleep(bcfg.get("poll_interval", 1.5))


def main() -> None:
    with auto.UIAutomationInitializerInThread():
        try:
            run()
        except KeyboardInterrupt:
            log.info("已退出")
        finally:
            if not restore_pending(force=True):
                log.warning('退出时剪贴板仍被占用，原内容尚未恢复')


if __name__ == "__main__":
    main()
