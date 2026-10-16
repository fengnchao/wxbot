# Butler 心跳与用户角色技能配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 log 面板按用户管理 Hermes 角色 skill、可用 skill 和心跳开关；Butler 将配置用于所有该用户请求，Hermes 运行时强制 skill allowlist。

**Architecture:** log 服务将联系人策略写入共享 JSON 配置；Butler 每次处理消息或心跳时加载策略并发送结构化 `skill_policy`。Hermes API 校验该字段并在请求执行线程中建立隔离策略，过滤 skills_list 并拒绝未授权 skill_view。Butler 服务内的后台调度器按随机间隔触发，每次随机选择一名开启者。

**Tech Stack:** Python stdlib HTTP servers, Hermes Agent aiohttp API, static HTML/JavaScript.

**Spec:** `docs/superpowers/specs/heartbeat-role-skills.md`

## Global Constraints

- 保留 wxbot checkout 中现有未提交改动，不重置、不覆盖、不提交。
- 不重启 Butler、wxbot、log 服务或 Hermes。
- 普通用户流程、群聊流程和 Hermes toolset 全局配置保持兼容。
- 本任务遵从上层指令，不新增或运行测试；用 Python 语法编译和静态代码检查验证。

## Review Focus

- 并发 API 请求下用户 A 的 skill allowlist 不得泄漏到用户 B。
- 已加载旧技能的会话在策略变更后不得继续复用旧 transcript。
- 未授权或不存在的 skill 名称必须失败关闭；未配置策略的既有请求保持原行为。
- log 面板不得向浏览器暴露 Hermes API key；配置文件必须原子保存。
- 用户关闭/移除心跳后，下一次调度不得继续为该用户调用 Hermes。

---

### Task 1: Hermes API 的请求级 skill policy

**Files:**
- Create: `D:/ai/hermes/hermes-agent/agent/skill_policy.py`
- Modify: `D:/ai/hermes/hermes-agent/gateway/platforms/api_server_openai_routes.py`
- Modify: `D:/ai/hermes/hermes-agent/gateway/platforms/api_server.py`
- Modify: `D:/ai/hermes/hermes-agent/tools/skills_tool.py`

**Interfaces:**
- `skill_policy` request object: `{"role_skill": str, "allowed_skills": list[str]}`.
- Context API: `skill_policy_scope(allowed_names)` and `current_skill_allowlist()`; `None` means legacy unrestricted behavior.
- `skill_view` permits the selected role plus allowed names; `skills_list` returns only that set.

- [x] Parse and validate `skill_policy` against the routed profile's installed skill catalogue.
- [x] Carry policy explicitly into `_run_agent`'s executor closure and scope only `agent.run_conversation()`; always reset the ContextVar in `finally`.
- [x] Add the role instruction to the ephemeral system message without changing any persisted transcript rows.
- [x] Filter `skills_list` and reject unauthorized `skill_view` names, including plugin-qualified names.
- [x] Run syntax-only parsing on touched Hermes modules and inspect the diff.

### Task 2: Butler shared policy store and request/session plumbing

**Files:**
- Create: `D:/work/code/wxbot/butler/skill_policy.py`
- Modify: `D:/work/code/wxbot/butler/config.py`
- Modify: `D:/work/code/wxbot/butler/hermes.py`
- Modify: `D:/work/code/wxbot/butler/core.py`

**Interfaces:**
- `SkillPolicyStore(path).for_contact(name)` returns validated per-contact settings.
- `HermesClient.chat(contact, text, *, skill_policy=None, session_kind="chat", ...)` sends a structured policy only when configured.
- Session ID includes a policy fingerprint and `session_kind`; the existing session key remains unchanged.

- [x] Add a shared config path and atomic JSON loader for role skill, allowed skills, and heartbeat toggle.
- [x] Add role/allowlist system instructions and the structured Hermes API request field.
- [x] Keep `X-Hermes-Session-Key` stable; isolate transcripts by policy and keep heartbeat history separate.
- [x] Apply policy on ordinary messages and reset calls; preserve group identity behavior already in the working tree.
- [x] Run syntax-only parsing on touched Butler modules and inspect the diff.

### Task 3: log service APIs and configuration UI

**Files:**
- Modify: `D:/work/code/wxbot/log/server.py`
- Modify: `D:/work/code/wxbot/log/index.html`
- Modify: `D:/work/code/wxbot/log/README.md`

**Interfaces:**
- `GET /api/heartbeat-config` returns contacts and saved policies.
- `GET /api/skills?profile=<profile>` returns safe skill catalogue fields through the Hermes server-side proxy.
- `POST /api/heartbeat-config` validates and atomically saves one contact's policy.

- [x] Load Hermes URL/key/profile routing from Butler config without logging or returning secrets.
- [x] Add the per-user heartbeat toggle, role selector, allowed-skill multi-select, and save feedback.
- [x] Restrict configuration to known direct-message contacts and installed skills.
- [x] Run syntax-only parsing and inspect the generated HTML/JS diff.

### Task 4: Butler in-process random heartbeat

**Files:**
- Create: `D:/work/code/wxbot/butler/heartbeat.py`
- Modify: `D:/work/code/wxbot/butler/config.py`
- Modify: `D:/work/code/wxbot/butler/server.py`
- Modify: `D:/work/code/wxbot/config.butler.example.toml`
- Modify: `D:/work/code/wxbot/butler/README.md`

**Interfaces:**
- `HeartbeatScheduler.start()` owns one daemon thread; `stop()` signals and joins it.
- Each trigger reads current policies, selects one enabled contact, calls Hermes with `session_kind="heartbeat"`, and pushes only a suggestion to that contact.

- [x] Add configurable random interval bounds (180–360 minutes by default) and a persisted next-run timestamp.
- [x] Ensure one heartbeat call at a time; no candidates is a silent skip.
- [x] Parse a strict no-action/suggestion result; only suggestions are sent through existing `Butler.push()`.
- [x] Start/stop the scheduler with the Butler HTTP server lifecycle; do not restart any running service.
- [x] Run syntax-only parsing and inspect the working-tree diff in both repositories.
