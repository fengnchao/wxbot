# User Message Forwarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 指定联系人使用独立 HTTP 单向消息接口，其他联系人继续调用现有模型。

**Architecture:** Butler 在模型相关操作之前匹配私聊联系人路由。独立模块验证配置并投递固定 JSON 协议，管理台复用该验证器。

**Tech Stack:** Python 3.14、requests、TOML、现有 pytest 与配置管理台。

**Spec:** `docs/superpowers/specs/2026-10-29-user-message-forwarding-design.md`

## Global Constraints

- 不修改真实运行配置、不重启服务、不向实际接口或微信发送测试消息。
- 保留工作区原有流式回复等未提交改动，在当前 checkout 完成小范围增量修改。
- 不自动提交当前工作区中的其他工作。

## Review Focus

- 失败与超时不回退模型、不产生微信回复，不自动重放。
- 相同名称的群聊和禁用规则仍使用原模型。
- 不合法 URL、重复联系人、空 code 和非有限超时同时被加载器与管理台拒绝。
- 转发成功不解析响应正文，不认领旧补发，不调用模型会话重置。
- 流式入口完成转发后不发答案增量，也不误标 Codex 为当前后端。

## Task 1: 路由配置、转发与配置管理

**Files:** Create `butler/message_forwarding.py`, `tests/test_message_forwarding.py`; modify `butler/config.py`, `butler/core.py`, `butler/defaults.py`, `log/config_view.py`, `log/config_schema.py`, `log/config_editor.py`, `wxbot/queue_worker.py`, `docs/MESSAGE_API.md`.

**Interfaces:** `MessageRoute`, `load_message_routes(rows) -> tuple[MessageRoute, ...]`, `forward_message(route, text) -> int`, `ForwardingError`; `Config.message_routes` carries validated rules.

- [x] Write failing behavior tests: exact payload and no reply/model/pending/reset; unmatched/disabled/group fallback; HTTP error, redirect and timeout; validation and dashboard editing; buffered and streaming transport.
- [x] Run `.venv/Scripts/python.exe -B -m pytest tests/test_message_forwarding.py -o addopts= -p no:cacheprovider -q`; confirm failures are missing routing behavior.
- [x] Implement the module and integrate before model policy/pending operations; add empty defaults and a JSON config row with shared validation.
- [x] Run the new tests and relevant existing transport/config/streaming tests.
- [x] Document the real config snippet, contact matching, timeout and operator-controlled reload.
- [x] Run the full offline pytest suite and inspect the incremental diff; leave implementation uncommitted for review.

## Execution record

Ruling: User supplied the concrete endpoint after the forwarding proposal; proceed with the established one-way contract. Existing uncommitted pipeline changes are required context, so implement in place without copying runtime state.

Ruling: Queue end-to-end testing found full typing mode calling `.strip()` on a silent `None` reply. One-line empty-text handling fixes successful forwarding being marked uncertain; the new test failed before the fix.

Ruling: Route matching belongs before `_resolved_contact`, whose legacy memory import may fail on unrelated memory conflicts. A real temporary UserRegistry regression reproduced that failure; matching now bypasses identity/memory import for forwarded requests.

Verification: 35 forwarding tests plus existing identity, config, transport, pipeline, concurrency and streaming tests: **171 passed**. Tests use a unique workspace `cache/pytest-forwarding-<uuid>` basetemp; the sandbox denies loopback sockets (WinError 10013), so local fake HTTP tests run with approved elevated execution. No actual 8790 API, model or WeChat calls.

Review: Fresh read-only reviewer found the pre-routing identity/memory issue; after the regression and fix, review has no remaining findings.

Final full suite: **1138 passed, 3 failed** (72.95 seconds). The remaining failures exercise existing workspace changes in queue storage and typing, rather than message forwarding; those implementations are preserved:

- `tests/test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts`: batch becomes `done` instead of `waiting_delivery`.
- `tests/test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker`: batch becomes `done` instead of `uncertain`.
- `tests/test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter`: a second paste occurs before the expected half-second interval.

`git diff --check` for the touched tracked files passed; only existing CRLF conversion notices were emitted. Actual runtime configuration remains unchanged, so the operator must add a contact-specific rule and reload Butler to activate it.
