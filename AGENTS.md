# Butler/wxbot development and installation

Read `architecture-notes/wxbot.md` first: it is the primary project document and
node index (layout, per-module file map, protocols, configuration, run and release
steps). Read matching node documents under `architecture-notes/`; follow the
workflow below. Use the installation
owner's own Codex login. Never copy credentials, local config or runtime data from
another installation. `python -m butler init` preserves existing configurations.

Business operations belong in Butler services; model backends implement the
shared backend interface; wxbot owns Windows UI interaction and the delivery queue.
Importable packages live under src/ (butler, wxbot, dashboard, common); the Vue
admin front end lives in web/ and the HTTP service in src/dashboard. Inside butler the
layers are agent/, identity/, delivery/, runtime/, channels/telegram/ (plus bot/ and
relay/); keep new modules in the matching layer. Do not add
sys.path hacks: use `from common.paths import REPO_ROOT` for repository paths.
Role and skill instructions are under plugins/butler-wechat. Tool execution must
validate the service-issued identity and permissions; prompts are not authority.

Never automatically restart existing services. Do not send real WeChat test
messages without explicit authorization. Use temporary data and fake delivery for
tests. tests/ is git-ignored and local only; tests/conftest.py forbids accessing
the real clipboard in offline tests.

Before preparing a release, run authorized checks and tools/release.py; never
commit auth.json, config.*.toml runtime files, data/, cache/, virtual environments
or databases. Keep *.example.toml templates credential-free.

## Architecture diagram (required for feature changes)

Review the canonical Archify diagram
`.archify/architecture-wxbot-20261107-201947/wxbot.html` for every feature change.
The old root `ARCHITECTURE.html` has been retired; do not recreate it.
When the implementation adds, removes, or changes a component or responsibility,
interface, data flow, data store, background job, or integration relevant to the
diagram, update the affected nodes and connections in the same change. Verify the
diagram against the implemented code before handing back the feature.

## Node documentation (required for code changes)

- Project explanations, API/field contracts, source evidence and development
  history are consolidated into the diagram-bound Markdown files under
  `architecture-notes/`. Start at `wxbot.md` and `index.json`, then search relevant
  node documents with `rg -n <keywords> architecture-notes`.
- `README.md` and the old `llm wiki/wxbot/` Markdown graph were explicitly retired
  by the project owner. Do not recreate their standalone pages or run the retired
  `change` / `ingest` / `lint` workflow. Old scripts, JSON snapshots and archived
  commands are historical material, not the current documentation workflow.
- Follow the affected node's links and verify facts against current source before
  changes. Report files/positions, callers/tests, frontend/backend contracts,
  DB/field lineage and risks before implementation. Continue within authorized
  scope; wait only when the user requests confirmation or scope needs authority.
- After a change, update the affected node documents and reciprocal links in the
  same change. Record goal/background, files and stable source anchors, API/DTO
  changes, DB/migrations, frontend consumers, tests/async jobs and risks/rollback;
  explicitly mark items not applicable and record the verification date.
- Preserve source provenance and history. When old statements conflict with code,
  add a dated correction identifying the superseded statement; do not present a
  migrated plan or historical test result as current behavior or a fresh check.
- Keep every explanatory Markdown file associated with an actual diagram node.
  The Archify document button uses `architecture-notes/`.
  `index.json` records all note files and their owning Archify node IDs, including
  detailed documents grouped under overview nodes.
  Validate note bindings and relative links before handing back documentation.
- Preserve `AGENTS.md`, runtime Skill/role/reference/template files and required
  license notices in their functional locations. Node documentation does not
  replace plugin runtime files or grant tool permissions.
- Never put credentials, runtime config, databases, messages or personal data in
  development documents. User knowledge vaults and runtime diaries remain under
  their configured data directories and are not development documentation.

## Front-end design: Hallmark (automatic)

The project owner has opted this repository into Hallmark for both new pages and
changes to existing pages. Automatically load the `hallmark` skill before any
UI-affecting work in `web/` (views, components, styles, navigation or interaction
states), even when the request does not mention Hallmark. Pure backend changes
without a UI effect do not trigger it. This is a development workflow, not a
Butler runtime skill or a dependency shipped to end users.

Resolve `SKILL.md` from `.agents/skills/hallmark/` in the project first, then
`~/.agents/skills/hallmark/`, then `$CODEX_HOME/skills/hallmark/` (default
`~/.codex/skills/hallmark/`). On this Windows installation the global skill is at
`C:/Users/fcc/.agents/skills/hallmark/SKILL.md`. Read the skill and the relevant
references, rather than merely mentioning its name. If unavailable, report the
missing skill explicitly; do not claim its checks passed.

- Use `references/flow.md` App screens for admin pages (`--scope app`) and
  Component scope for isolated components (`--scope component`). Preserve the
  Vue 3/Vite structure, existing shell and `web/src/styles/theme.css` design
  tokens; new pages share the project's design system, not a fresh theme each.
- For an existing page, the default is Hallmark polish: preserve its layout,
  content, routes, fields, handlers, API calls and test hooks. Read
  `references/redesign.md` for this scope. A full redesign or restyle requires
  the user to request that depth; routine changes do not authorize one.
- Apply accessibility, focus, reduced-motion and interaction-state checks to
  the requested change. Use real project data and existing supported states;
  do not fabricate metrics or add unsupported business actions. Do not expand
  a local change into cleanup of unrelated legacy design findings.
- Before handing back UI changes, run Hallmark's `scripts/sloplint.mjs` against
  the changed source files/folders with the matching scope. For Vue rendering,
  use `--render --url <actual-dev-server-URL-with-/app/-and-changed-tab>`;
  rendering `web/index.html` directly does not test the application. Use an
  existing dev server or start a separate preview without restarting services.
  If rendering is unavailable, run static checks and disclose that limit.
- Keep the page-registration workflow in `architecture-notes/dashboard.md` and run `npm.cmd --prefix web
  run build` and `npm.cmd --prefix web run smoke` after UI source changes.
  Include the matching `web/dist/` output in the change; preserve unrelated
  work already present. Report checks actually run and any remaining findings.
