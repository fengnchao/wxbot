"""配置：一个 TOML 读进来，其余模块只认 Config 对象。

密钥只从文件读，从不打印（日志里只出现"有没有配"）。
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .contacts import ContactMap, load_contacts

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config.toml"


@dataclass
class Config:
    # server
    host: str = "127.0.0.1"
    port: int = 8770
    token: str = ""
    # hermes
    hermes_url: str = "http://127.0.0.1:8642"
    hermes_key: str = ""
    hermes_model: str = "hermes-agent"
    hermes_timeout: int = 600
    hermes_root: str = ""
    send_identity: bool = True
    # wxbot（主动推送）
    wxbot_url: str = "http://127.0.0.1:8765"
    wxbot_token: str = ""
    wxbot_timeout: int = 120
    # dispatch（决策层）
    actions_enabled: bool = True
    script_dir: str = ""
    respond_after_action: bool = False
    # 联系人
    contacts: ContactMap = field(default_factory=ContactMap)

    @property
    def have_token(self) -> bool:
        return bool(self.token)

    def hermes_up(self) -> bool:
        return bool(self.hermes_url)


def load(path: str | os.PathLike | None = None) -> Config:
    p = Path(path) if path else DEFAULT_CONFIG
    raw: dict = {}
    if p.exists():
        with open(p, "rb") as fh:
            raw = tomllib.load(fh)

    srv = raw.get("server") or {}
    h = raw.get("hermes") or {}
    w = raw.get("wxbot") or {}
    d = raw.get("dispatch") or {}

    return Config(
        host=str(srv.get("host") or "127.0.0.1"),
        port=int(srv.get("port") or 8770),
        token=str(srv.get("token") or "").strip(),
        hermes_url=str(h.get("url") or "http://127.0.0.1:8642").rstrip("/"),
        hermes_key=str(h.get("api_key") or "").strip(),
        hermes_model=str(h.get("model") or "hermes-agent"),
        hermes_timeout=int(h.get("timeout") or 600),
        hermes_root=str(h.get("root") or "").rstrip("/\\"),
        send_identity=bool(h.get("send_identity", True)),
        wxbot_url=str(w.get("url") or "http://127.0.0.1:8765").rstrip("/"),
        wxbot_token=str(w.get("token") or "").strip(),
        wxbot_timeout=int(w.get("timeout") or 120),
        actions_enabled=bool(d.get("actions_enabled", True)),
        script_dir=str(d.get("script_dir") or "").rstrip("/\\"),
        respond_after_action=bool(d.get("respond_after_action", False)),
        contacts=load_contacts(raw.get("contacts")),
    )


def masked(value: str) -> str:
    """用于日志/状态输出：永远不打印密钥本体。"""
    if not value:
        return "（未配置）"
    return f"已配置({len(value)} 字符)"
