"""共享夹具：一个一次性 HERMES_HOME + 一个假的 Hermes 客户端。

关键在**共享事件日志**：假的 pending_delivery.py 和假 Hermes 客户端往同一个文件里追加，
于是「先认领先调模型」变成可断言的顺序，而不是注释里的一句承诺。
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
for entry in (SRC, ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from butler.config import Config                    # noqa: E402
from butler.contacts import load_contacts           # noqa: E402
from butler.core import Butler                      # noqa: E402
from butler.hermes import HermesClient              # noqa: E402
from butler.server import make_handler              # noqa: E402

DEFAULT_CONTACT = {"name": "101", "profile": "wxbot-101", "uid": "101", "label": "微信联系人101"}
DEFAULT_PENDING = [{"key": "reminder-x@2026-10-11 00:00:00", "text": "⏰ 该喝水啦"}]


@pytest.fixture(autouse=True)
def no_system_clipboard(monkeypatch):
    """A missing test double must never reach the machine's actual clipboard."""
    from wxbot.wechat.clipboard import WindowsClipboard
    def forbidden(self):
        pytest.fail('Clipboard tests must inject a fake native API')
    monkeypatch.setattr(WindowsClipboard,'__init__',forbidden)


DEFAULT_REMINDERS = {"reminders": [
    {"id": "abc123", "content": "喝水", "status": "scheduled",
     "scheduled_at": "2026-10-12T10:00:00", "cron_job_id": "j1", "followup_job_ids": ["j2", "j3"]},
]}

# 假补发脚本：只实现管家会用的两个子命令，并把调用记进自己旁边的 events.log
FAKE_PENDING = '''# -*- coding: utf-8 -*-
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
cmd = sys.argv[1] if len(sys.argv) > 1 else ""
with open(HERE / "events.log", "a", encoding="utf-8") as fh:
    fh.write(cmd if cmd == "json" else "flush %s" % (sys.argv[2] if len(sys.argv) > 2 else ""))
    fh.write("\\n")
if cmd == "json":
    # 注意用默认 ensure_ascii（ASCII 转义）输出：子进程 stdout 走管道时按系统
    # 区域编码（中文 Windows 是 GBK），Emoji 正文直接输出会 UnicodeEncodeError。
    print(json.dumps({"items": json.loads((HERE / "items.json").read_text(encoding="utf-8"))}))
elif cmd == "flush":
    items = json.loads((HERE / "items.json").read_text(encoding="utf-8"))
    (HERE / "items.json").write_text(json.dumps([i for i in items if not isinstance(i,dict) or i.get("key") != sys.argv[2]]), encoding="utf-8")
'''


class FakeHermes(HermesClient):
    """替身：把 'chat' 写进同一个 events.log（顺序可断言），并可返回预设异常。"""

    def __init__(self, events_file: Path, replies=None, *, cfg, locks):
        super().__init__(cfg, locks=locks)
        self.events_file = events_file
        self.replies = list(replies if replies is not None else ["好的"])
        self.calls: list[dict] = []

    def alive(self, profile):
        return True

    def chat(self, contact, text, *, extra_system="", timeout=None, skill_policy=None, session_kind='chat'):
        with self.session_guard(contact, skill_policy=skill_policy, session_kind=session_kind):
            return self._fake_chat(contact,text,extra_system=extra_system,skill_policy=skill_policy,session_kind=session_kind)

    def _fake_chat(self, contact, text, *, extra_system='',skill_policy=None,session_kind='chat'):
        self.calls.append({"contact": contact.name, "profile": contact.profile,
                           "uid": contact.uid, "text": text, "extra_system": extra_system,
                           "skill_policy":skill_policy,"session_kind":session_kind})
        with open(self.events_file, "a", encoding="utf-8") as fh:
            fh.write("chat\n")
        if not self.replies:
            return ""
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class Home:
    """一次 _make() 的产物：路径 + 组装好的 Butler（Hermes 已被替身换掉）。"""

    def __init__(self, root, cfg, butler, hermes, events, profile, scripts):
        self.root, self.cfg, self.butler, self.hermes = root, cfg, butler, hermes
        self.events, self.profile, self.scripts = events, profile, scripts

    def log(self) -> list[str]:
        return [x for x in self.events.read_text(encoding="utf-8").split("\n") if x.strip()]

    def jobs(self) -> dict:
        return json.loads((self.profile / "cron" / "jobs.json").read_text(encoding="utf-8"))


@pytest.fixture
def make_home(tmp_path_factory):
    """造一个临时 HERMES_HOME。每次调用都独立，可连造多个互不干扰。"""
    def _make(replies=None, pending_items=DEFAULT_PENDING, contacts=None, reminders=None,
              cron_jobs=None):
        """pending_items 显式传 [] 表示"没有积压"；不传才是默认那条积压。"""
        root = tmp_path_factory.mktemp("hermes-home")
        profile = root / "profiles" / "wxbot-101"
        scripts = profile / "skills" / "messaging" / "wechat-reminder" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "pending_delivery.py").write_text(FAKE_PENDING, encoding="utf-8")
        events = scripts / "events.log"
        events.write_text("", encoding="utf-8")
        (scripts / "items.json").write_text(json.dumps(pending_items), encoding="utf-8")
        (profile / "reminders.json").write_text(
            json.dumps(DEFAULT_REMINDERS if reminders is None else reminders, ensure_ascii=False),
            encoding="utf-8")
        if cron_jobs is not None:
            (profile / "cron").mkdir(exist_ok=True)
            (profile / "cron" / "jobs.json").write_text(json.dumps({"jobs": cron_jobs}),
                                                        encoding="utf-8")
        cfg = Config(token="t0ken", hermes_root=str(root), script_dir="",
                     contacts=load_contacts(contacts or [DEFAULT_CONTACT]))
        butler = Butler(cfg)
        hermes = FakeHermes(events, replies, cfg=cfg, locks=butler.runtime_locks)
        butler.hermes = hermes
        return Home(root, cfg, butler, hermes, events, profile, scripts)

    return _make


@pytest.fixture
def start_server():
    """在随机端口上起真 HTTP（真 server 栈 + 假模型），退出时收干净。"""
    started = []

    def _start(butler, cfg):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(butler, cfg))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        started.append(httpd)
        return "http://127.0.0.1:%d" % httpd.server_address[1]

    yield _start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()
