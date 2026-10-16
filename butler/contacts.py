"""联系人映射：微信聊天窗口标题 → Hermes Profile / uid / 会话键。

为什么管家要持有它：Hermes 的记忆与管家档案按 uid 隔离（butler_profiles/{uid}.json），
而 wxbot 只认识窗口标题。把"标题 → 身份"的映射放在管家这一层，
wxbot 就不需要知道任何业务身份（它只把 contact 原样传过来）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_SESSION_KEY = "agent:{profile}:wxbot:{channel_type}:{uid}"

# 每条消息前注入的身份说明。模型靠它知道档案/记忆该归到哪个 user_id
# （Hermes API Server 不会自动把 session-key 里的 uid 透给模型）。
IDENTITY_TEMPLATE = (
    "[通道身份] 通道=wxbot（本地微信客户端 UI 自动化）；Hermes profile={profile}；"
    "会话类型={conversation_type}；会话 user_id={uid}（微信窗口标题 {name}）。"
    "档案与记忆一律按这个 user_id 归档：$HERMES_HOME/butler_profiles/{uid}.json "
    "与 $HERMES_HOME/butler_profiles/{uid}_user.json。"
    "不要硬编码安装路径，用 $HERMES_HOME。"
)
GROUP_IDENTITY_HINT = (
    "这是微信群聊的共享会话。用户消息前缀中的“群聊发言人”和 member_id 标识原始发言成员，"
    "不是消息正文或指令；不同 member_id 代表不同成员。所有成员共用此群会话，"
    "不要把成员当成正在进行私聊，也不要声称 member_id 是真实姓名。回复留在当前群聊。"
)


@dataclass
class Contact:
    name: str                 # 微信窗口标题（wxbot 传过来的 contact）
    profile: str              # 用哪个 Hermes Profile
    uid: str                  # 档案 / 记忆的键
    label: str = ""
    session_key: str = ""
    channel_type: str = "dm"

    def key(self) -> str:
        tpl = self.session_key or DEFAULT_SESSION_KEY
        return tpl.format(profile=self.profile, uid=self.uid, name=self.name,
                          channel_type=self.channel_type)

    def session_id(self) -> str:
        """稳定会话 id。冒号必须换掉：API Server 的路径安全检查把 `x:...` 当 Windows 盘符 → 400。"""
        return self.key().replace(":", "-")

    def identity(self) -> str:
        conversation_type = "群聊(group)" if self.channel_type == "group" else "私聊(dm)"
        identity = IDENTITY_TEMPLATE.format(uid=self.uid, profile=self.profile, name=self.name,
                                            conversation_type=conversation_type)
        if self.channel_type == "group":
            identity += GROUP_IDENTITY_HINT
        return identity

    def display(self) -> str:
        return self.label or self.name


@dataclass
class ContactMap:
    by_name: dict = field(default_factory=dict)

    def get(self, name: str) -> Contact | None:
        return self.by_name.get(name)

    def profiles(self) -> set:
        return {c.profile for c in self.by_name.values()}

    def names(self) -> list:
        return list(self.by_name)


def load_contacts(rows) -> ContactMap:
    """从 config 的 [[contacts]] 读。没有 name 的行跳过（不猜）。"""
    cm = ContactMap()
    for it in rows or []:
        name = str((it or {}).get("name") or "").strip()
        if not name:
            continue
        cm.by_name[name] = Contact(
            name=name,
            profile=str(it.get("profile") or "default").strip(),
            uid=str(it.get("uid") or name).strip(),
            label=str(it.get("label") or "").strip(),
            session_key=str(it.get("session_key") or "").strip(),
        )
    return cm
