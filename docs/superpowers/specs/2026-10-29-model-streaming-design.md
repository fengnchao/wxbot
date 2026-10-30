# Dynamic model workflow and streaming WeChat replies

Approved direction: user selected real streaming sentence delivery and agreed that interrupted generation keeps confirmed sent sentences, stops the turn and never automatically replays it. This document records that approved direction; implementation choices below are builder decisions.

## Goals and choices

Resolve model display from actual wxbot installation/model transport, plus runtime metadata when available. Keep direct/external/local routing intact. Show configured and active model separately when they differ. Expand the optional model panel to show public reasoning summaries, tool progress and generated answer text. Never invent reasoning or render opaque/private reasoning as a public summary. No summary/tool event can become a WeChat delivery.

Two approaches were considered: stream dashboard only and wait for complete replies; or real append-only answer streaming into durable per-sentence deliveries. The user selected the latter while retaining full-paste and chunk-paste modes.

## Protocol and boundaries

Introduce common/model_stream.py: context-bound event callback, emit(kind, **fields), bind(callback), with canonical kinds backend, summary_delta, tool, answer_delta, complete, error. Events have bounded fields; only explicitly public summaries and final-answer channel deltas are eligible. Backend adapters must advertise true answer streaming separately from observational progress. Intermediate/tool-loop commentary is never sendable. Unsupported adapters announce fallback and deliver the final validated answer once, never fake generation.

Processor.handle_reply gains optional on_event callback propagated through Router. Existing call contracts stay valid. Butler adds authenticated POST /v1/handle-stream using SSE, retains /v1/handle; the stream ends with the normal validated Result JSON or error. Existing identities/permissions and body validation remain. No second model request on reconnect/failure. Streaming cannot bypass Butler final cleanup/actions/pending replies: if safe append-only final text cannot be guaranteed, progress streams but answer is buffered until composition completes. The final response must match any already streamed prefix; mismatch stops, never replaces already sent text.

## Durable model stream and send modes

wxbot records bounded per-request canonical events in a SQLite auxiliary stream table via the queue runtime. GET projection/content access remains read-only, no schema initialization. log serves local fixed-path incremental event reads; polling with cursor is acceptable for initial real-time transport, around 250-500ms for selected active stream, no overlapping requests. No remote admin credential forwarding.

wechat.typing.mode = full | chunked | streaming; missing preserves chunked. Existing chunk_size/chunk_interval remain. Full waits for entire reply and pastes one bubble (except platform length constraints). Chunked retains existing complete-result chunk typing. Streaming appends incoming final-answer text to a live queue part and input draft; sealed sentence parts alone may press Enter. UI stays on its owning thread, guards target/focus/draft/clipboard and confirms each bubble before next part. A live unsealed part must never press Enter, including on interruption.

Sentence splitting: strong sentence punctuation 。！？!?; contiguous punctuation and closing quotes remain together; no splitting within fenced code, inline code, URLs or decimals. Normal completion flushes remainder. Incremental parser holds punctuation until boundary is unambiguous. Limit buffered text and duration, backend timeout bounds unsealed input. Never use silence timeout as permission to send an unsealed thought. Stable batch/part sequence prevents duplicate queue entries. Streaming output is persisted before UI consumes it; each batch pins its send mode at claim time.

On error/restart cancel unsent streaming parts, retain sent receipts, protect Enter-attempted outcomes as uncertain/manual review, do not replay model request. Clear only a verified owned draft, otherwise preserve it with review indication. Same-contact ordering and no overlapping UI writers remain mandatory. Unsupported window/backend streaming explicitly falls back to complete-result mode; do not silently drop replies.

Builder-check rulings: Before early answer deltas Butler must resolve the service-issued identity/mention metadata; unknown group mention falls back to full-result delivery. The stream Enter gate verifies sealed immutable text/active generation under the queue transaction and durably marks Enter-attempted before keypress; cancellation uses the same transaction boundary. If cancellation wins no Enter, otherwise later cancellation retains uncertain outcome. Direct Chat Completions/Responses are the initial genuine streaming paths; legacy Hermes composition may explicitly buffer when it cannot guarantee final-answer deltas.

## UI and configuration

Workflow model label shows provider and optional model, from wxbot config for direct mode and Butler config/runtime metadata for Butler mode; do not require a Butler config for direct mode. Flow diagram truthfully bypasses Butler in direct mode. Selected model stream is bounded, escapes content, separates summary/progress/answer; tab changes and selection changes abort reads and reject stale replies. Preserve message-first layout and history deletion.

Expose reply mode enum in configuration with Chinese choices/descriptions, defaults and validation. Runtime config changes require restarting wxbot as other typing settings do. Do not change user's actual mode to streaming automatically. No real WeChat sends in tests.

## Validation

Fake SSE/SDK and temporary queues: complete and unsupported streaming, malformed/truncated frames, interleaved tools, request identity, secret redaction, final-prefix mismatch, duplicate sequence, sentence parser across arbitrary deltas, live draft appends, unsealed no Enter, confirmed send before next, error/restart with sent and unsent parts, same-contact ordering. Frontend stale request/tab/selection races, dynamic direct-mode display without Butler config, escaped bounded panel content, existing cleanup/jobs/config regressions.

No commits/staging, runtime-config migration or credentials changes are part of this request. Existing dirty work is preserved. Authorized service start/restart is permitted, but only fake delivery tests; no actual chat turn is initiated by verification.
