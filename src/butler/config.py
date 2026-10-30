"""配置：一个 TOML 读进来，其余模块只认 Config 对象。

密钥只从文件读，从不打印（日志里只出现"有没有配"）。
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from common.paths import REPO_ROOT

from butler.identity.contacts import ContactMap, load_contacts
from butler.delivery.message_forwarding import MessageRoute, load_message_routes

DEFAULT_CONFIG = REPO_ROOT / "config.butler.toml"


@dataclass
class Config:
    reply_chunk_chars: int = 500
    group_context_messages: int = 30
    group_context_characters: int = 6000
    provider: str = 'hermes'  # Existing files keep their backend; init creates Codex configs.
    data_dir: str = 'data'
    config_dir: str = ''
    contact_database: str = ''
    codex_home: str = ''
    codex_plugin: str = ''
    codex_model: str = ''
    codex_api_key: str = field(default='', repr=False)
    codex_timeout: int = 600
    codex_max_workers: int = 2
    codex_idle_seconds: int = 600
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
    message_routes: tuple[MessageRoute, ...] = field(default_factory=tuple)

    @property
    def have_token(self) -> bool:
        return bool(self.token)

    def resolve_path(self, value):
        p = Path(value).expanduser()
        return (p if p.is_absolute() else Path(self.config_dir or DEFAULT_CONFIG.parent)/p).resolve()

    def data_path(self):
        return self.resolve_path(self.data_dir)

    def codex_home_path(self):
        return self.resolve_path(self.codex_home) if self.codex_home else self.data_path()/'codex'

    def plugin_path(self):
        return self.resolve_path(self.codex_plugin) if self.codex_plugin else REPO_ROOT/'plugins'/'butler-wechat'

    def hermes_up(self) -> bool:
        return bool(self.hermes_url)

    def flow_log_path(self) -> str:
        """流水日志文件路径。显式配置优先；否则 {hermes_root}/cache/wxbot.log（看板默认读这里）；都无则返回空=禁用。"""
        if self.flow_log:
            return str(self.resolve_path(self.flow_log)) if self.provider=='codex' else self.flow_log
        if self.provider == 'codex':
            return str(self.data_path()/'cache'/'wxbot.log')
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "wxbot.log")
        return ""

    def group_file_path(self) -> str:
        """用户分组字典路径。显式配置优先；否则 {hermes_root}/cache/butler_groups.json
        （log 看板「用户分组」页默认读写同一路径）；都无则返回空=禁用（群发按无人绑定处理）。"""
        if self.groups_file:
            return str(self.resolve_path(self.groups_file)) if self.provider=='codex' else self.groups_file
        if self.provider == 'codex':
            return str(self.data_path()/'cache'/'butler_groups.json')
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "butler_groups.json")
        return ""

    def heartbeat_config_path(self) -> str:
        if self.heartbeat_config_file:
            return str(self.resolve_path(self.heartbeat_config_file)) if self.provider=='codex' else self.heartbeat_config_file
        if self.provider == 'codex':
            return str(self.data_path()/'cache'/'butler_heartbeat.json')
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "butler_heartbeat.json")
        return ""

    def heartbeat_state_path(self) -> str:
        if self.heartbeat_state_file:
            return str(self.resolve_path(self.heartbeat_state_file)) if self.provider=='codex' else self.heartbeat_state_file
        if self.provider == 'codex':
            return str(self.data_path()/'cache'/'butler_heartbeat_state.json')
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "butler_heartbeat_state.json")
        return ""

    def heartbeat_audit_path(self) -> str:
        if self.heartbeat_audit_file:
            return str(self.resolve_path(self.heartbeat_audit_file)) if self.provider=='codex' else self.heartbeat_audit_file
        if self.provider == 'codex':
            return str(self.data_path()/'cache'/'butler_heartbeat_audit.jsonl')
        if self.hermes_root:
            return os.path.join(self.hermes_root, "cache", "butler_heartbeat_audit.jsonl")
        return ""


def load(path: str | os.PathLike | None = None) -> Config:
    p = Path(path) if path else DEFAULT_CONFIG
    raw: dict = {}
    if p.exists():
        with open(p, "r", encoding="utf-8-sig") as fh:
            raw = tomllib.loads(fh.read())

    srv = raw.get("server") or {}
    h = raw.get("hermes") or {}
    w = raw.get("wxbot") or {}
    d = raw.get("dispatch") or {}
    lg = raw.get("log") or {}
    gp = raw.get("groups") or {}
    hb = raw.get("heartbeat") or {}
    agent = raw.get('agent') or {}
    codex = raw.get('codex') or {}
    provider = str(agent.get('provider') or 'hermes')
    if provider not in ('hermes','codex'):
        raise ValueError('agent.provider must be codex or hermes')

    from butler.agent.reply import validate_chunk_chars
    chunk_chars = validate_chunk_chars((raw.get('reply') or {}).get('chunk_chars', 500))
    context = raw.get('context') or {}
    context_messages = context.get('group_messages',30)
    context_characters = context.get('group_characters',6000)
    if type(context_messages)is not int or not 1<=context_messages<=200:
        raise ValueError('context.group_messages must be an integer from 1 to 200')
    if type(context_characters)is not int or not 1<=context_characters<=30000:
        raise ValueError('context.group_characters must be an integer from 1 to 30000')
    from butler.identity.directory import DirectoryContactMap, directory_path, directory_enabled
    contacts = (DirectoryContactMap(directory_path(p, raw))
                if directory_enabled(p, raw) else load_contacts(raw.get("contacts")))
    return Config(
        reply_chunk_chars=chunk_chars,
        group_context_messages=context_messages,group_context_characters=context_characters,
        provider=provider, config_dir=str(p.resolve().parent),
        contact_database=str(directory_path(p,raw)) if directory_enabled(p,raw) else '',
        data_dir=str(agent.get('data_dir') or 'data'),
        codex_home=str(codex.get('home') or ''), codex_plugin=str(codex.get('plugin_root') or ''),
        codex_model=str(codex.get('model') or ''), codex_timeout=max(1,int(codex.get('timeout',600))),
        codex_api_key=str(codex.get('api_key') or ''),
        codex_max_workers=max(1,min(8,int(codex.get('max_workers',2)))),
        codex_idle_seconds=max(1,int(codex.get('idle_seconds',600))),
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
        contacts=contacts,
        message_routes=load_message_routes(raw.get('message_routes', [])),
    )


def masked(value: str) -> str:
    """用于日志/状态输出：永远不打印密钥本体。"""
    if not value:
        return "（未配置）"
    return f"已配置({len(value)} 字符)"
