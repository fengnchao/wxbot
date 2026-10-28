# Delete unsent messages and isolate deferred capture

The user confirmed deleting message records and stopping later delivery, from a
global button on the queue page covering wxbot and Telegram. Successful delivery
history, contacts, subscriptions, memory, reminders and configuration remain.

## Behavior

- Add `删除所有未发送成功消息` above queue results. Its scope is all conversations
  and pages, independent of search and filters. Require one explicit confirmation
  and return actual deletion and protected-in-flight counts.
- Physically remove unsent queued/failed/uncertain/skipped delivery records and
  their now-unused incoming/model records. Keep successful child records and the
  parent data they require. A partially deleted package must never become a
  successful full-package receipt merely because its remaining children are sent.
- Keep currently sending/confirming wxbot rows and actual Telegram HTTP submissions
  until their operations finish. Report them clearly. Remove other queued parts.
  Never edit the live WeChat draft; mention remaining drafts when relevant.
- UI-discovered unread conversations that have not been collected are read tasks,
  not stored messages. Preserve their live/persisted markers and report them as
  `protected_reads`, included in the protected total, to avoid memory re-enqueue or
  silently dropping a genuinely new incoming message.
- Preserve polling offsets and minimal replay barriers. A model response, queued
  outbound request or Telegram expansion begun before deletion must not recreate
  a deleted task. No automatic replay, restart, or real test send.
- Fix queue action de-duplication to use the actually rendered reply-round page,
  not the independently paginated outbox data.
- Isolate known incoming-capture `ReadDeferred` errors from delivery. Retain unread
  tasks and snapshots without guessing unknown message senders. A genuinely
  unreadable send baseline or unverified destination still stops sending safely.

## Approach

The user selected physical deletion over cancellation with retained message bodies.
Use existing SQLite transactions and dashboard same-origin confirmation protection.
Avoid database/schema resets and new dependencies. Preserve package request IDs
and Telegram cursor metadata for replay prevention. Add a payload-free cleanup
event for wxbot's outbound request cutoff. Test with temporary databases and fake UI.

## Workspace and validation

Work in the existing feature checkout; unrelated pre-existing tracked bytecode
deletions remain untouched. Separate frontend, Telegram and capture fixes across
agents, with the main agent owning wxbot cleanup and HTTP integration. Use TDD,
an independent review, focused checks and the complete offline test suite. Existing
baseline failures and sandbox networking failures must be reported distinctly.
