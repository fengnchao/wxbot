"""配置：一个 TOML 读进来，其余模块只认 Config 对象。

密钥只从文件读，从不打印（日志里只出现"有没有配"）。
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .contacts import ContactMap, load_contacts

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config.butler.toml"


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
    # Hermes URL 是否带命名 Profile 前缀 /p/{profile}/。
    # True  → {base}/p/{profile}/v1/...（Hermes 侧配了命名 Profile 时）
    # False → {base}/v1/...（扁平接口，默认；记忆隔离仍靠 X-Hermes-Session-Key 头）
    hermes_profile_in_path: bool = False
    # wxbot（主动推送）
    wxbot_url: str = "http://127.0.0.1:8765"
    wxbot_token: str = ""
    wxbot_timeout: int = 120
    # dispatch（决策层）
    actions_enabled: bool = True
    script_dir: str = ""
    respond_after_action: bool = False
    # 流水日志（供 log 看板 8788 解析）：留空则用 {hermes_root}/cache/wxbot.log
    flow_log: str = ""
    # 用户分组字典（messageType → 绑定用户）：留空则用 {hermes_root}/cache/butler_groups.json
    groups_file: str = ""
    # 用户角色技能 + 心跳开关；log 看板与 Butler 读写同一文件。
    heartbeat_config_file: str = ""
    heartbeat_state_file: str = ""
    heartbeat_audit_file: str = ""
    heartbeat_min_interval_minutes: int = 180
    heartbeat_max_interval_minutes: int = 360
    # 联系人
    contacts: ContactMap = field(default_factory=ContactMap)

    @property
    def have_token(self) -> bool:
        return bool(self.token)

    def hermes_up(self) -> bool:
        return bool(self.hermes_url)

    def flow_log_path(self) -> str:
        """流水日志文件路径。显式配置优先；否则 {hermes_root}/cache/wxbot.log（看板默认读这里）；都无则返回空=禁用。"""
        if self.flow_log:
            return self.flow_log
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "wxbot.log")
        return ""

    def group_file_path(self) -> str:
        """用户分组字典路径。显式配置优先；否则 {hermes_root}/cache/butler_groups.json
        （log 看板「用户分组」页默认读写同一路径）；都无则返回空=禁用（群发按无人绑定处理）。"""
        if self.groups_file:
            return self.groups_file
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "butler_groups.json")
        return ""

    def heartbeat_config_path(self) -> str:
        if self.heartbeat_config_file:
            return self.heartbeat_config_file
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "butler_heartbeat.json")
        return ""

    def heartbeat_state_path(self) -> str:
        if self.heartbeat_state_file:
            return self.heartbeat_state_file
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "butler_heartbeat_state.json")
        return ""

    def heartbeat_audit_path(self) -> str:
        if self.heartbeat_audit_file:
            return self.heartbeat_audit_file
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "butler_heartbeat_audit.jsonl")
        return ""


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
    lg = raw.get("log") or {}
    gp = raw.get("groups") or {}
    hb = raw.get("heartbeat") or {}

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
        hermes_profile_in_path=bool(h.get("profile_in_path", False)),
        wxbot_url=str(w.get("url") or "http://127.0.0.1:8765").rstrip("/"),
        wxbot_token=str(w.get("token") or "").strip(),
        wxbot_timeout=int(w.get("timeout") or 120),
        actions_enabled=bool(d.get("actions_enabled", True)),
        script_dir=str(d.get("script_dir") or "").rstrip("/\\"),
        respond_after_action=bool(d.get("respond_after_action", False)),
        flow_log=str(lg.get("flow_file") or "").strip(),
        groups_file=str(gp.get("file") or "").strip(),
        heartbeat_config_file=str(hb.get("config_file") or "").strip(),
        heartbeat_state_file=str(hb.get("state_file") or "").strip(),
        heartbeat_audit_file=str(hb.get("audit_file") or "").strip(),
        heartbeat_min_interval_minutes=max(1, int(hb.get("min_interval_minutes") or 180)),
        heartbeat_max_interval_minutes=max(1, int(hb.get("max_interval_minutes") or 360)),
        contacts=load_contacts(raw.get("contacts")),
    )


def masked(value: str) -> str:
    """用于日志/状态输出：永远不打印密钥本体。"""
    if not value:
        return "（未配置）"
    return f"已配置({len(value)} 字符)"
