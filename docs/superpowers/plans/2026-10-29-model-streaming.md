# Model Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Dynamic model identity and public progress in log, plus full/chunked/real streaming sentence typing in wxbot.
**Architecture:** Canonical callback events flow from backend adapters through the processor/Butler stream endpoint into a durable local queue event projection and an append-only sentence delivery state machine. log reads bounded event snapshots without calling the model.
**Tech Stack:** Python, SQLite, SSE, vanilla JavaScript, existing UIA typing guards.
**Spec:** docs/superpowers/specs/2026-10-29-model-streaming-design.md

## Global Constraints

- No actual WeChat test messages; temporary data/fake UI only. No commits/staging, credentials changes or real config changes.
- Keep prior dirty work. Current branch codex-butler-distribution (verify actual branch from terminal); continue current checkout because feature builds on uncommitted installation/workflow changes, no separate checkout copying runtime data.
- Event contract: on_event(event: dict), event type in backend, summary_delta, tool, answer_delta, complete, error; text for summary_delta/answer_delta, sendable=True only for final-answer append-only text. Metadata provider/model/streaming on backend, status/tool on tool; no auth values or tool arguments.
- common.model_stream exposes bind(callback) context manager and emit(kind, **fields); processors accept optional on_event=None via handle_reply; Router forwards only when provided (keep old fake adapters compatible).
- Full-result consumers remain valid. No raw private reasoning. No automatic replay after a stream emitted answer text.

## Review Focus

- Tool commentary/final mismatch must never be sent as final answer.
- Stream failure/restart must not send unsealed drafts or repeat sent content.
- Race between queue writer and Enter must require sealed latest snapshot.
- Direct mode without Butler config must load correct workflow identity.
- Stale stream UI requests after tab/selection changes must be ignored.

### Task 1: Transport and public model events

**Files:** common/model_stream.py; butler/backends/codex.py; butler/hermes_stream.py; butler/core.py; butler/server.py; wxbot/processor/{base,router,butler,openai_compat,responses,cursor,ollama}.py; matching new tests.
**Interfaces:** on_event(dict); metadata/backend event; result validation stays authoritative. SSE POST /v1/handle-stream with same auth/body as existing handle, event JSON frames ending type=result with result=normal Result JSON. Persist/replay is not a second generation request.
- [x] Write failing fake-adapter/SSE tests for answer versus summary separation, malformed EOF, final validation, unsupported fallback and metadata.
- [x] Implement bounded canonical context events, safe adapter capability checks, authenticated Butler streaming and callback propagation.
- [x] Verify fake-only adapter and existing backend tests, report exact commands/results and unsupported capabilities.

### Task 2: Durable streaming sentence queue and typing

**Files:** wxbot/streaming.py (or focused modules), queue_store.py, queue_worker.py, delivery.py, wechat/typing.py, config.py, inbox.py; matching tests.
**Interfaces:** ModelWorker(..., typing_mode='chunked') calls Router.handle_reply(on_event=...) only when supported/callback contract enabled; records bounded model events to queue auxiliary table for all modes. Expose read-only projection via log task3 independently (coordinate schema method names). Canonical events as Global Constraints. New methods stream_snapshot(batch_id) and model_events(batch_id, after=0) should be simple adapters/read-only helpers; parent will implement log read module using agreed table schema model_stream_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT NOT NULL,event TEXT NOT NULL,created_at REAL NOT NULL), per batch bounded retention. Auxiliary initialized runtime only; legacy readonly reads tolerate missing table.
- [x] Write failing parser, worker/queue interruption, append-draft and no-Enter-until-sealed tests.
- [x] Implement incremental sentence buffer protecting code/URLs/decimals/closing punctuation; persist append-only live part, sealed state and frozen batch mode.
- [x] Implement full/chunked/streaming typing without breaking existing UI guards; cancel stream drafts on error/restart, retain sent and uncertain receipts, no retry.
- [x] Wire mode validation/default in wxbot config and ModelWorker startup. Parent updates config editor/defaults.
- [x] Verify queue/typing/delivery regressions with fake delivery only.

### Task 3: Workflow identity, bounded live panel and configuration

**Files:** log/model_stream_view.py, log/workflow_view.py, log/server.py, log/assets/workflow.js/css, log/config_schema.py, log/config_view.py, butler/defaults.py, docs and tests.
**Interfaces:** GET /api/workflow returns model metadata {provider,label,model,via_butler}; backend retained compatibility. GET /api/workflow-stream?id=<batch>&after=<seq> reads local fixed queue table above, validated selected message ID; no arbitrary paths, no model calls. Poll about 400ms selected stream, abort/epoch on navigation; bounded panel text escapes HTML.
- [x] Write failing dynamic direct/local identity, no-Butler-config and stream readonly/readlimits tests; frontend request race and escape tests.
- [x] Implement provider/model config resolution and runtime event overrides, truthful routing, summary/tool/answer panel with compact empty state.
- [x] Add editable wechat.typing.mode enum full/chunked/streaming with default chunked, clear restart semantics and unsupported fallback explanation.
- [x] Update docs, run feature/regression checks and final independent review; fix Important findings with regression tests.

## Integration

- [x] Verify all component contracts together using fake model streams and actual temporary queue/typing harness.
- [x] Run broad offline suite, compare known pre-existing failures against baseline evidence; do not mask new failures.
- [x] Authorized log restart and read-only browser QA; no real model turn or WeChat send. Explain changed service restart needs and supported backend streaming limitations in final.
