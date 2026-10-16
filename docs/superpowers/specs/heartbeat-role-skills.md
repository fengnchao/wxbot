# Butler 心跳与用户角色技能配置规格

## 目标

在 log 面板中按微信联系人管理 Hermes 角色 skill、每用户可调用的 skill 和心跳开关。Butler 的普通对话与心跳请求都使用该联系人的角色及 skill 白名单；Hermes 在运行时强制校验白名单。

## 配置

log 服务维护 `{HERMES_HOME}/cache/butler_heartbeat.json`，使用原子替换写入。记录按微信窗口标题索引：

```json
{
  "version": 1,
  "contacts": {
    "联系人窗口名": {
      "heartbeat_enabled": true,
      "role_skill": "role-skill-name",
      "allowed_skills": ["skill-a", "skill-b"]
    }
  }
}
```

`role_skill` 必须存在并且自动包含在该用户的运行时 allowlist 中。`allowed_skills` 仅包含附加技能。没有配置的联系人继续按现有 Hermes API 权限工作；群聊不参与个人心跳。

## log 面板

- 新增“心跳配置”标签页，左侧列出 wxbot 配置中的私聊联系人。
- 对选中用户提供心跳开关、角色 skill 单选、可调用 skill 多选和保存操作。
- 技能目录由 log 后端代理 Hermes 鉴权 `GET /v1/skills` 获取；返回给浏览器的只有名称、描述、分类，不含 API key。
- log 后端校验联系人和技能名称，再原子写配置文件。Butler 每次请求/调度时读取最新文件。

## Hermes 请求和运行时策略

- Butler 对配置过角色的用户，在每条普通消息和心跳请求中发送 `skill_policy = {role_skill, allowed_skills}`，并附带稳定的 `X-Hermes-Session-Key` 与连续会话 `X-Hermes-Session-Id`。
- Hermes 校验技能名称存在于当前 Profile 的技能目录，角色 skill 自动获准；非法名称以 HTTP 400 拒绝。
- 请求线程中的 skill policy 通过 ContextVar 隔离。`skills_list` 只列出允许技能；`skill_view` 对未授权名称返回拒绝结果。无策略时保留原行为。
- 配置指纹进入会话 ID 命名空间。角色或 allowlist 变化后创建新 transcript，防止旧历史里加载过的技能内容绕过新策略；同一用户的长期 session key 不变。
- Hermes Profile 的 terminal/web 等底层 toolset 仍按 Hermes 原有配置授权；此策略约束 Hermes skill 加载，不改变底层 toolset。

## 心跳

- Butler 服务内启动一个后台调度线程，使用可配置的随机间隔（默认 180–360 分钟），并持久化下次触发时刻。
- 每次触发从开启心跳且有角色 skill 的私聊联系人中均匀随机选择一位；一次只调用一位。没有候选人就跳过。
- 心跳使用独立 Session ID，但复用联系人身份 key 与同一角色/allowlist。
- Hermes 返回“无建议”时不发消息；返回建议时立即经 wxbot 私聊所选用户。Butler 不执行建议或指令。
- 心跳调用失败只记录日志；不改变联系人消息流程或推送队列。

## 部署边界

本功能跨 wxbot 仓库的 log/Butler 代码和 Hermes Agent API。改完只交付代码与配置说明，不自动重启 Butler、wxbot、log 服务或 Hermes；用户自行启动/重启。
