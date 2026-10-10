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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler.config import Config                    # noqa: E402
from butler.contacts import load_contacts           # noqa: E402
from butler.core import Butler                      # noqa: E402
from butler.server import make_handler              # noqa: E402

DEFAULT_CONTACT = {"name": "101", "profile": "wxbot-101", "uid": "101", "label": "微信联系人101"}
DEFAULT_PENDING = [{"key": "reminder-x@2026-10-11 00:00:00", "text": "⏰ 该喝水啦"}]
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
    print(json.dumps({"items": json.loads((HERE / "items.json").read_text(encoding="utf-8"))},
                     ensure_ascii=False))
'''


class FakeHermes:
    """替身：把 'chat' 写进同一个 events.log（顺序可断言），并可返回预设异常。"""

    def __init__(self, events_file: Path, replies=None):
        self.events_file = events_file
        self.replies = list(replies if replies is not None else ["好的"])
        self.calls: list[dict] = []
        self.session_ids: dict[str, str] = {}

    def session_id(self, contact):
        return self.session_ids.get(contact.name) or contact.session_id()

    def reset(self, contact):
        self.session_ids[contact.name] = contact.session_id() + "-reset"

    def alive(self, profile):
        return True

    def chat(self, contact, text, *, extra_system="", timeout=None):
        self.calls.append({"contact": contact.name, "profile": contact.profile,
                           "uid": contact.uid, "text": text, "extra_system": extra_system})
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
        hermes = FakeHermes(events, replies)
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
