# log dashboard implementation ledger

Approved brief: the user's 2026-10-21 “log 管理页面整体整理” plan in this conversation.

Tasks: (1) read-only projections and sorting; (2) grouped layout and flow/queue views;
(3) configuration forms and runtime views; (4) regression, browser verification and review.

Ruling: work in the existing codex-butler-distribution checkout, retaining all
uncommitted distribution work. A fresh checkout would omit the approved runtime
and configuration editor that this dashboard extends. No commits or service restarts.

Pre-flight: query parameters remain optional and old API responses stay compatible;
frontend pagination consumes server ordering. Configuration drafts retain canonical
source IDs/paths, original versions and existing writer validation.

Task 1: complete. Watched new tests fail for missing offsets/scope/order/form metadata,
then pass with optional compatible parameters. Queue reads remain read-only and
sorting occurs before LIMIT/OFFSET. Runtime reminder selection prioritizes due
scheduled tasks before its 200-row limit; legacy business callers keep their order.

Task 2: complete. Extracted static assets, grouped navigation and shared components;
flow stages grouped per operation, summaries closed by default, independent queue
pagers and active/issues/history. Rendering preserves manual detail state and scroll.

Task 3: complete. Six configuration categories, inactive backend compatibility
details, canonical source/path drafts, structured contacts/string lists, enum
controls and dirty-only sticky save actions. Existing writer/secret tests retained.
Runtime memory/events filtered, reminders linked to jobs, role/tool/heartbeat
settings separated from execution records. Added current user documentation.

Task 4: complete. `python -m pytest -o addopts='' -q`: 415 passed in 26.94s.
`node tests/log_frontend_checks.js`: passed, including a final run after focus-key
handling. `git diff --check`: no whitespace errors (existing CRLF warnings only).
Browser QA used tests/dashboard_preview.py with temporary Chinese/space paths,
fake backend data and an independent loopback port. Checked 1280, 820 and 390px,
no document overflow, automatic list collapse, independent pagination, ascending
flow ordering, disclosure persistence after refresh, draft persistence across
categories, structured contact edits, hidden secret drafts and no console errors.
Screenshot: data/ops/log-dashboard-preview.png (ignored).

Review: one independent read-only final reviewer found an Important tool grouping
issue and a Minor invalid contact draft issue. Fixed both. Regression reproduced
tool occurrence collapse (1 vs 3), then passed. Calls without IDs now pair only
unambiguous occurrences; overlapping calls remain separate. Invalid contact items
fall back to JSON with an error note. A further regression prevents duplicate
recovery buttons when the same task is already in the current list.

Ruling: service-side reminder projection needs a manual Butler restart in addition
to log, so global due order is correct before truncation. No wxbot change/restart.
All existing services and live configurations/data left untouched. No WeChat sends,
Git commits, pushes or release publication performed.

Reviewer set aside only pre-existing distribution/backend changes and real-service
integration; accepted because this task is dashboard organization with explicitly
temporary/fake verification. The current task's added projection changes were reviewed.
