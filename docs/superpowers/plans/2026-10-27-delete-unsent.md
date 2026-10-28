# Delete Unsent Messages Implementation Plan

> **For agentic workers:** Use test-driven development for each implementation task.

**Goal:** Let the user delete all unsuccessful queued messages immediately and
restore push delivery when incoming message capture is deferred.

**Architecture:** Existing dashboard confirmation guards invoke coordinated wxbot
and Telegram cleanup services. Transactions protect successful/in-flight records;
replay barriers prevent stale work from rebuilding deleted tasks. Incoming capture
failures are isolated at the inbox boundary without weakening send verification.

**Tech Stack:** Python 3.14, SQLite, stdlib HTTP, vanilla JavaScript, pytest/Node.

**Spec:** `docs/superpowers/specs/2026-10-27-delete-unsent-design.md`

## Global Constraints

- No automatic service restart, real WeChat sends, or real clipboard in tests.
- No credentials, runtime data, databases or local config in source changes.
- Preserve sent history, users, subscriptions, memory and authentication.
- Use server-configured paths and same-origin explicit-confirmation protection.

## Review Focus

- Late model/outbound/Telegram work must not recreate deleted tasks.
- Partial delivery must not be reported as complete success.
- Active UI/HTTP work survives cleanup and is explicitly reported.
- Pagination and searching must not hide the sole manual-action controls.
- Clipped unknown incoming rows retain unread state without blocking valid pushes.

### Task 1: Frontend controls

- [x] Reproduce action buttons disappearing with independently paginated rounds.
- [x] Fix de-duplication, add the global delete control and confirmation.
- [x] Test request fields, busy/error handling, accurate results and refresh.

### Task 2: Transactional cleanup and HTTP integration

- [x] Write mixed-state, partial-delivery, late-work and idempotency tests first.
- [x] Implement `QueueStore.delete_unsent` and Telegram `cleanup.delete_unsent`.
- [x] Preserve active sends, package replay receipts and Telegram cursor/barriers.
- [x] Add `POST /api/queue-delete-unsent` with existing origin/JSON confirmation.
- [x] Release deleted delivery waiters and reject stale outbound requests.

### Task 3: ReadDeferred isolation

- [x] Reproduce deferred incoming capture blocking valid target delivery.
- [x] Catch only known capture deferrals at inbox capture/switch boundaries.
- [x] Verify unread snapshots stay intact and unreadable baselines still stop sends.

### Task 4: Integrated verification

- [x] Run targeted tests, frontend script and Python/JavaScript syntax checks.
- [x] Run the full offline suite and compare against recorded baseline failures.
- [x] Review the combined change independently and fix material findings.
- [x] Document the new action and the services the user must reload manually.

## Verification record (2026-10-28)

- Final complete offline run: **905 passed, 3 failed**, 51.17 seconds, 908 tests.
  JUnit evidence: `.superpowers/delete-unsent-verified.xml`.
- The following pre-existing failures were separately reproduced using the
  original `HEAD` queue-store and typing modules, without changing workspace
  sources (`.superpowers/delete-unsent-head-baseline.xml`):
  - `tests/test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts`
  - `tests/test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker`
  - `tests/test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter`
- New/closely related feature tests: 54 passed. Node frontend checks, JavaScript
  syntax, AST checks for 16 Python files and `git diff --check` passed.
- Independent review found cancellation-overwrite, partial-success projection,
  and unread-discovery-marker lifecycle issues. Each was reproduced and addressed
  with covering tests. Added write-lock backup tests for both channels as well.
- Scope ruling: keep uncollected UI read tasks and report `protected_reads`;
  collected unmerged inbox rows and processing model batches are deleted. This
  keeps live memory aligned and prevents silently consuming genuinely new unread
  messages. Preserve currently active UI/HTTP operations and report their counts.
- No service restart, real WeChat send, live clipboard operation, credential
  change or production database cleanup was performed during implementation.
