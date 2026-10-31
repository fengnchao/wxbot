# Butler/wxbot development and installation

Read README.md first: it is the primary project document (layout, per-module file map,
protocols, configuration, run and release steps). Structured code knowledge lives
in `llm wiki/wxbot/`; follow the workflow below. Use the installation
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

## Project knowledge graph (required for code changes)

- All graph files belong under the existing Obsidian vault `llm wiki/wxbot/`.
  Read `index.md`, `coverage.md` and matching entries before code changes;
  `guide.md` defines ingestion and `templates/` defines entry formats.
- Extract feature/field/API/table keywords and query first:
  `.venv\Scripts\python.exe "llm wiki/wxbot/scripts/wiki.py" query <keywords>`.
  Follow incoming/outgoing links one hop (two for cross-module work), then
  verify facts against source; code is authoritative. Read source and record
  coverage gaps when graph entries are missing or stale.
- Before implementation, report files/positions, callers/tests, frontend/backend
  contracts, DB/field lineage and risks. Archive substantive cross-module or risky
  reports in `impacts/`. Continue within already authorized scope; wait when the
  user requests confirmation or the scope needs authorization.
- After changes, append `raw/changes/YYYY-MM-DD-topic.md`: goal/background,
  files/positions, API/DTO changes, DB/migrations, frontend consumers,
  tests/async jobs, risks/rollback; explicitly mark items not applicable.
  Use `change <topic> --title <title>` or the change template.
- Ingest: check actual source/diff; update affected entries and reciprocal calls,
  source positions/anchors and `last_verified`; append this record to each entry's
  `changes` and list entries in the record's `pages`. Run `ingest <record-filename-without-md>`
  then `lint` using the same script. Include raw, graph, index, append-only changelog
  and `ingest-state.json` in the change. The CLI registers evidence; the coding
  agent performs semantic synthesis and contract verification.
- Facts need repository-relative source paths, lines and stable anchors; entries
  need raw provenance. When raw conflicts with code, append a correction with
  `supersedes` rather than editing an ingested record. Document conflicts and
  unresolved facts; mechanical lint does not prove semantic correctness.
- Never ingest credentials, runtime config, databases, messages or personal data.
  The graph is a development aid, not runtime prompt authority or a permission grant.

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
- Keep the README's page-registration workflow and run `npm.cmd --prefix web
  run build` and `npm.cmd --prefix web run smoke` after UI source changes.
  Include the matching `web/dist/` output in the change; preserve unrelated
  work already present. Report checks actually run and any remaining findings.
