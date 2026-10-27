# 用户身份、记忆与群上下文 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Track progress below.

**Goal:** 在 log 管理固定用户与记忆，隔离成员会话并提供公共群上下文，节省静默请求，使用真正微信提及。
**Architecture:** Butler owns registry and memory operations; wxbot owns avatar sampling, delivery and public-message intake; log proxies authenticated administration. Fixed UUIDs are independent of avatar hashes. Public context is bounded and never carries another member's memories.
**Tech Stack:** Python, SQLite, Pillow, stdlib HTTP, existing plain JavaScript dashboard and fake UI pytest fixtures.
**Spec:** docs/superpowers/specs/2026-10-25-user-identity-memory-group-context-design.md (approved by user: 实施).

## Global Constraints

- No real WeChat test messages, clipboard access, service restarts or credential/config copying.
- Preserve runtime data; schema migrations are additive and backed up before alteration.
- Default group/DM memories separate; only explicit administrator binding shares memory.
- One UI thread, complete-result-only delivery, no replay of uncertain submissions.
- Work in current non-main feature checkout; preserve pre-existing tracked deletions. User authorized implementation in this project; avoid moving runtime files or creating an unnecessary checkout.

## Review Focus

- Ambiguous or unknown avatar cannot acquire somebody else's memory credentials.
- Manual linking with duplicate memory keys must not silently replace either value.
- Group public messages cannot expose another member's private memory or another group.
- Rich mention objects must survive draft verification; missing/ambiguous candidate must stop before Enter.
- Administrator endpoints require existing server credential and browser same-origin protections.

### Task 1: Registry, avatars and memory ownership
Files: common/avatar_identity.py, butler/user_registry.py, butler/business.py, butler/contacts.py, butler/core.py, butler/backends/codex.py, butler/tools.py, tests/test_user_registry.py.
Interfaces: UserRegistry(store).create(channel_type,contact,nickname,avatar), list_users(query='',contact='',offset=0,limit=50), resolve(contact,channel_type,member_key='',avatar='',nickname=''), memories(binding_id), change_memory(binding_id,key,value,version,delete=False), update_binding(binding_id,version,**changes), link(binding_id,target_id,version,resolutions=None). Avatar upload is base64 bytes. resolve returns binding_id,user_id,memory_owner,memory_version,status. list rows expose avatar as bounded data URL and memory_count. Fixed binding keeps independent session, shared memory owner can change explicitly.
- [ ] Write and run failing registry/avatar/ownership/conflict tests.
- [ ] Implement transactional registry, bounded image validation, audit/versioning and migration.
- [ ] Integrate authorized owner resolution, retrieval and memory revision scopes; run registry and Codex tests.

### Task 2: True mentions and normalized runtime avatars
Files: wxbot/wechat/chat_window.py, wxbot/wechat/typing.py, wxbot/wechat/mentions.py, wxbot/queue_schema.py, wxbot/queue_store.py, wxbot/delivery.py, tests/test_true_mentions.py.
Interfaces: Delivery.mention_name (default ''), QueueStore.finish_batch_parts saves body without @ prefix and first-part mention target. chat.start_send(text,mention_name='',clock=...) uses mention selection state machine, actual object draft representation, and expected visible submitted_text. Message.avatar (default '') supplies normalized 36x36 PNG base64 using common/avatar_identity.py. Legacy member key remains observational, not permanent user ID.
- [ ] Write failing real-mention fake UI, ambiguous candidate and backward-queue tests.
- [ ] Implement selection state machine and rich-draft guard; queue fields are additive, old uncertain rows untouched.
- [ ] Run related delivery/typing/queue tests and review relevant compatibility failures.

### Task 3: Public group context and local reply decisions
Files: butler/group_context.py, wxbot/queue_worker.py, wxbot/inbox.py, wxbot/processor/butler.py, wxbot/processor/router.py, wxbot/config.py, tests/test_group_public_context.py.
Interfaces: GroupContext(store).archive(contact,source_id,messages) idempotently; snapshot(contact,before_seq,after_seq=0,limit=30,max_chars=6000); worker forwards archive via ButlerProcessor.archive_group(contact,source_id,text,member_key,member_name,avatar='') and returns sequence boundary for model request. ButlerProcessor.handle_reply optional avatar/group_context_seq; worker silent/emoji archive before no-model branch. Do not edit queue_schema/queue_store owned by Task 2; use existing batch IDs to archive queued observations. Current request excluded from public snippet. Continuations and config defaults remain bounded/local.
- [ ] Write failing archive/isolation/no-model tests.
- [ ] Implement bounded group store, transport and local cooldown/budget decisions, independent of model execution.
- [ ] Run group worker/processor/inbox tests; root integrates authenticated archive and context injection.

### Task 4: log user management and admin transport
Files: log/user_admin.py, log/server.py, log/index.html, log/assets/users.js, log/assets/app.js, log/assets/dashboard.css, butler/user_api.py, butler/server.py, tests/test_user_admin.py.
Interfaces: authenticated GET /v1/users?query=&contact=&offset=&limit= returns rows,total; POST /v1/users accepts action create/update/avatar/link/memory_set/memory_delete with binding_id/version and field values; GET /v1/users/memory?binding_id=; GET /v1/users/audit?binding_id=. Browser GET /api/users(/memory,/audit) proxies server-side; POST /api/users requires X-Wxbot-User-Action:1 and same origin; no credentials reach browser. Functions dispatch_user_get(registry,path,query), dispatch_user_post(registry,payload). New page ordered avatar, ID, channel/nickname, memory button with upload/create, edits, link conflict preview, audit.
- [ ] Write failing endpoint/security tests and frontend contract checks.
- [ ] Implement user page, safe upload and authenticated proxy using existing helpers.
- [ ] Run endpoint/frontend tests; verify DOM in a local isolated dashboard fixture.

### Task 5: integration, migration, workflow and review
Files: common/flow_trace.py, log/workflow_view.py, log/assets/workflow.js, docs/USER_MEMORY.md and integration tests as needed.
- [ ] Integrate registry with real request path; unknown members get no persistent memory privileges.
- [ ] Extend existing workflow with identity/context/memory/mention summaries without content leakage.
- [ ] Run targeted suite, full offline suite, syntax checks and git diff --check; distinguish baseline failures.
- [ ] Dispatch independent final code review and fix important findings with regression tests.
- [ ] Document manual restarts, identity onboarding/migration and real UI verification limits; no publishing or service restart.
