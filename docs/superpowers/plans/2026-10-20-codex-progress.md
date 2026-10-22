# Execution ledger — 2026-10-20-codex-distribution

- Started on `codex-butler-distribution`, preserving the pre-existing dirty tree.
- Ruling: implement in the current checkout on a new branch because the approved
  integration depends on existing uncommitted queue/config-editor work; no live
  configuration is changed. Cost: integration changes share the working tree.
- Ruling: maintain the plugin in this repository as an independently packageable
  directory. The same Git repository supplies its marketplace and application.
- Interface preflight: legacy Config/HermesClient methods must stay compatible;
  generic backend methods feed existing complete-reply and heartbeat contracts.
- Interface preflight: role policy JSON stays editable by log; Codex business
  records and sessions live in a separate SQLite database under the data root.
- Task 1: complete — portable config, tagged plugin catalogue, fresh SQLite,
  signed identity capabilities, allowlists, read-only heartbeat and idempotency.
- Task 2: complete — pinned official SDK/runtime 0.163.0; bounded isolated
  workers, durable thread mappings, final-answer-only delivery and proxy support.
- Task 3: complete — compatible Butler/wxbot interfaces, independent heartbeat
  scopes, durable one-time/recurring reminders and delivery failure records.
- Task 4: complete — Butler-backed log catalogue/runtime view, editable backend
  settings, portable init/doctor/login/start, plugin marketplace and release tool.
- Task 5: complete — 404 offline checks passed; real Codex role, MCP memory write,
  worker shutdown/resume and memory read passed without any WeChat delivery.

## Final review and fix pass

- Fresh read-only reviewer: two Important findings; no confirmed Critical issue.
- Fixed cancellation race: claim each reminder immediately before dispatch;
  already-delivering/sent reminders reject cancellation. Two regressions observed
  RED then GREEN; cancelled queued reminders never enter fake delivery.
- Fixed relative startup configuration: resolve once before spawning children
  with another working directory. Regression observed RED then GREEN.
- Also added required tool arguments to advertised schemas and regression;
  checked explicit relative business paths and removed legacy file instructions
  from Codex identity text, with RED then GREEN coverage.
- Doctor now checks configured service ports; regression observed RED then GREEN.
- Failure coverage: login absent, quota error, interrupted/incomplete final output
  and deadline expiry all produce no sendable reply. Changed permissions revoke
  existing tool capabilities; group/chat/heartbeat/role/permission scopes differ.
- Full suite: `python -m pytest -o addopts= -q` -> 404 passed. Lock validation and
  normal `git diff --check` passed. Pre-existing work remains unstaged.
- Release allowlist and current Git candidates passed credential pattern,
  current local credential-value and runtime-file exclusion checks.
- Final archives: 145 application files and 23 standalone plugin files. Extracted
  into a Chinese-and-space temporary path; setup installed a fresh venv, repeat
  init preserved bytes, doctor reported SDK 0.163.0/protocol 1 and no copied auth.
  Verification captured subprocess output using PYTHONUTF8=1 on Windows.
- Final suite after the fix pass: 404 passed in 26.65s.

## Delivery rulings

- Ruling: retain the existing working tree and branch without committing, merging
  or pushing — the user requested implementation/distribution and the tree also
  contains prior work — cost: the owner must choose and review the Git commit.
- Ruling: retain code-mode host for the current SDK's MCP bridge while disabling
  native shell/browser/apps and enforcing server capabilities — disabling it
  prevented real tool calls — cost: isolation must be rechecked on SDK upgrades.
- Ruling: use the owner's already-authenticated Codex home only for the explicitly
  authorized real probe; production init creates a separate home and copies no
  authentication — cost: probe sessions remain in that selected test account.
- Review limits: native sandbox enforcement was not adversarially audited; actual
  WeChat delivery and remote marketplace installation remain manual checks.
  Local CLI marketplace discovery and real MCP access were exercised.
- No deferred review findings; no existing service was restarted or stopped.

## User-authorized deployment — 2026-10-21

- User subsequently authorized stopping legacy services, switching the existing
  installation in place, and real WeChat tests scoped to contact 101.
- Completed a fresh browser login in data/codex; no authentication was copied.
- Backed up configs and task definitions under ignored data/backups; disabled
  two legacy Windows startup tasks, stopped Hermes and paused four legacy jobs.
- Preserved contact/role/skill/group settings; moved runtime paths to data/,
  leaving legacy history, memory, reminders and queue records untouched.
- Started Butler, log and wxbot in hidden user-session processes. Backend API
  reports codex; log reads the project data root; wxbot connected to WeChat.
- Fixed misleading startup backend text with RED->GREEN regression coverage.
- Real send exposed a zero-generation empty clipboard. Native read/write/restore
  proved access worked; clipboard guard rejected the valid initial empty state.
  Added three regressions, observed RED, fixed while retaining post-write checks;
  focused clipboard/typing/delivery suite passed 57 tests.
- Real outbound test confirmed matching submitted text and a new self bubble.
  Real inbound '1' reached its own merged batch, Codex completed, and automatic
  reply '在呢，兄弟，有啥想聊的？' was confirmed sent. No synthetic inbox row used.
- Full regression after the fixes: 408 passed in 26.81s. Runtime records and
  rollback notes are private deployment data excluded from source releases.
