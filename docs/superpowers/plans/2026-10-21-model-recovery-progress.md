# Model failure recovery

User request: fix group messages that remain blocked after model failure.

Root evidence: Butler returned reply_complete=false after a pre-turn Codex RPC
failure. wxbot discarded the failure details, converted it to a generic ValueError,
and kept a permanent uncertain batch. Queue preparation blocks later messages in
the same conversation while any nonterminal batch exists.

Implementation:

- Preserve sanitized errors and explicit pre-submission retry eligibility through
  Codex → Butler → wxbot. Mark the turn submitted before calling turn RPC.
- Recover rejected stored threads with a fresh thread using identical identity,
  role and permissions. Long-term business memory/reminders are retained; the
  new thread does not inherit the old conversational context.
- Retry confirmed pre-submission failures with the same request ID, at most three
  attempts with 5/15 second backoff. Never automatically replay unknown results.
- End incomplete failed batches without outbox results at the existing configured
  failure timeout (180 seconds by default), preserving input/error/audit. Later
  messages can then merge and execute. Safe retry exhaustion ends the failed batch.
- No schema migration. Failure audit timestamps persist the first deadline and
  latest safe/unknown status; processing interruption revokes the previous safe flag.
- Dashboard exposes retry/deadline/audit and distinguishes model_failed history
  from successfully completed replies. Existing partially generated/sent deliveries
  remain under the existing delivery policy.

Validation before final review: 425 Python tests passed in 27.33s; Node frontend checks passed.
A read-only SQLite backup of the live queue was tested in a disposable directory:
the old uncertain blocker ended, a later group batch became ready, and no outbox
record was added. No real model/UI call, queue mutation or service restart.

Cleanup: first copy verification succeeded but SQLite context managers kept handles
open until process exit. A corrected verification with explicit closing succeeded
and removed its copy. Automated command approval rejected deleting the first
copy's two named files, without providing a specific reason. That directory
remains in the local Temp folder for the user to remove; it is outside Git/release.

Restart handoff: user must restart Butler, wxbot and log in their IDE. Runtime
recovery handles existing failures after wxbot starts. No service started here.

Review: fixed two P2 findings with red/green regressions. Previously failed ready
retries now retain their deadline and are expired atomically before claim. Slot
acquisition failure now flows through pre-submission error classification, without
releasing an unowned semaphore. 42 targeted recovery/backend/queue tests passed.

Final verification: 427 tests passed in 27.36s, Node frontend checks passed,
targeted git diff whitespace check passed (line-ending notices only). No live
queue mutation or process startup/restart. The first Temp copy remains after
automatic approval also rejected a nonrecursive cleanup of its two exact files;
no further delete retries. User-facing handoff includes that cleanup limitation.

## Live repair after explicit restart and contact 101 authorization

The user subsequently authorized restarting all three services and real WeChat
testing with contact 101. At inspection their ports were not listening. Butler
received the earlier reset request, but its original process exit/connection-reset
cause could not be established from the retained logs; do not attribute that
10054 error to a proven Python exception.

A controlled live request reproduced a separate concrete startup failure:
`account/read` returned `workspace routing discovery timed out` after 15 seconds.
The user's robot login remained valid. A minimal SDK probe reusing one client
failed twice, then completed account discovery at 44.68 seconds and thread start
at 54.62 seconds. The previous failure handler closed the client after the first
timeout, discarding the warmed connection.

The backend now retries only that specific account-discovery error up to three
checks on the same client, before any model turn or business tool submission.
Other errors still propagate; exhaustion remains safe to retry. Initialization
and retry status are recorded without credentials or model input. Two regression
tests failed before the change and passed after it. All 429 Python tests and the
Node frontend checks passed.

Butler, wxbot and log were started with the isolated robot configuration and
captured UTF-8 logs. The earlier unknown batch expired through the existing
180-second policy without automatic replay. Contact 101's subsequent pending
batch completed and both reply parts were confirmed `sent` at 17:42. A short
test prompt was delivered; the real new inbound `1` was collected at 17:44 and
its model-generated reply was confirmed `sent` at 17:45:08. No unfinished model
batches remained at that check. Existing normal group backlog also resumed.

After loading the final diagnostic-field adjustment, another live Butler/Codex
request returned a complete `测试完成` reply in 23.31 seconds; that direct HTTP
probe was not forwarded to WeChat. All three health/page endpoints returned 200.
Services remain running under the repair launchers. Future IDE startup preference
is unchanged; this repair used the user's explicit one-time authorization.

## Follow-up: prevent failure-cleanup starvation

The user asked why the backlog accumulated and requested a permanent fix. Three
additional paths were reproduced with failing regressions: account initialization
was outside the request timer, initialization held the global worker-cache lock
across network I/O, and failure recovery ran only on the model threads (so two
occupied workers starved timeout cleanup).

The total deadline now starts before waiting for a model slot and covers SDK
initialize, account discovery, session restoration and model streaming. New SDK
startup has a separate maximum of 60 seconds, capped by the remaining total
deadline. A pinned-SDK transport adapter registers cancellation before the
blocking initialize RPC. The worker-cache lock protects cache/reservation changes
only; initializers reserve capacity so cached plus starting clients remain within
the configured maximum. Startup completion atomically checks/cancels its deadline
before publishing the client; a client closed during a slow session save cannot
be mistaken for a submitted model turn.

An independent wxbot maintenance thread sweeps failed-task recovery every 0.2s,
even when all model workers are waiting. It does not expire or replay active
model calls. Existing first-failure deadlines, maximum safe retries and the
no-unknown-replay policy remain in force. Review found and fixed two P2 races
with red/green regressions (expired-client publication and initializer capacity).
Final offline verification: 437 tests passed in 29.01s. Eight new regressions
cover initialization timeouts, concurrent initialization, cleanup starvation,
capacity and timer/publication races. The independent review passed.

While this fix was in progress the user requested a workflow home-page proposal
and design image only. No product homepage code was changed. Its image is a
static preview with sample data, not evidence of a live dashboard implementation.

The already-authorized repair launchers loaded the bounded-startup fix in Butler
and wxbot; log remained running. A real contact-101 model request through the
final SDK adapter returned HTTP 200, reply_complete=true and `检查完成。` in
23.95 seconds; this direct model probe was not sent to WeChat. wxbot recovered
with zero unbatched inputs, zero pending sessions and zero unfinished deliveries.
Frontend checks passed. The homepage proposal is awaiting the user's review.

Subsequent update: the user approved the homepage design and implementation.
Its changes and verification are tracked in `2026-10-21-workflow-home-progress.md`.
