# Telegram relay Skill and image delivery implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development and maintain this plan's ledger. User explicitly approved execution with 实施; continue without a second plan approval.

**Goal:** Configurable Desktop channel → current Telegram bot → Butler → WeChat, including actual photos and albums, with serialized desktop interaction.
**Architecture:** Butler owns relay settings, permissions and media IDs. Bot network receiver downloads approved images and creates ordered packages. wxbot owns the one UI thread, Telegram forwarding and WeChat image sends. log administers configuration and displays progress.
**Tech:** Python/SQLite/requests/Pillow/uiautomation, existing JS admin.
**Spec:** docs/superpowers/specs/2026-10-25-configurable-telegram-relay-skill-design.md (approved).

## Constraints and review focus

- Work in existing authorized feature checkout; preserve earlier uncommitted fixes and unrelated deletions. No commit/push/release requested.
- No service restarts, credentials/config copying, real clipboard or real test messages. Temporary DB/fake UI only. Disabled templates never activate a live route.
- Arbitrary paths/URLs cannot become media inputs; server-issued media IDs only. Unknown results never replay automatically.
- Telegram may own desktop only when WeChat has no active transaction; network waits never retain UI ownership.
- Test source identity ambiguity, Bot identity mismatch, photo-only/album messages, late album members, duplicate packages, corrupt/oversized images, interrupted UI operations and admin revocation.

## Shared contracts

- `common.media_bundle.validate_items(items)` returns bounded `{kind:'text',text}` / `{kind:'image',media_id}` list (max 50); rejects arbitrary extra fields/path input. Media ID is 32 lowercase hex.
- `butler.media.MediaStore(root).put(data:bytes)->dict` returns media_id,mime,size,sha256,width,height; `.read(media_id)->(bytes,dict)` verifies cached data. HTTP root integration: authenticated POST `/v1/media` binary ≤20MiB, GET `/v1/media/<id>`.
- Bundle HTTP: authenticated Butler POST `/v1/push/bundle` `{contact,items,request_id}` → wxbot POST `/send-bundle`, same payload, X-Wxbot-Token, waits for whole package. `request_id` stable source/package key; queue inserts all items atomically and idempotently.
- Relay config module `butler.telegram_relay.settings`: `load(path,missing_ok=True)` returning dataclass with enabled,window_title,bot_username,bot_id,poll_interval,include_images,album_quiet_seconds,max_album_wait,admin_contacts,channels; channels have key,name,username,chat_id,enabled. `Settings(path).read()` returns safe versioned dict; `.update(payload,version)` validates and writes atomically. Root resolves path with `cfg.resolve_path('config.telegram-relay.toml')` or project wxbot config root. Missing file means disabled/no media activation.
- Bot receiver publishes `state_dir/bot-identity.json` containing bot_id,username,at (no secrets), confirmed by getMe. Desktop verifies target matches this current bot identity before forwarding.
- Desktop `RelayStore(path)` persists baseline/cursors/tasks/status; `DesktopRelay(settings_path,state_dir,driver).tick()` one bounded UI operation. Root owns this module and integrates MainInbox to yield safely between Telegram/WeChat.

## Task 1 — media ingestion and Bot network pipeline (agent media_pipeline)

Own: common/media_bundle.py, butler/media.py, butler/push.py (bundle helper only), butler/push_client.py (bundle helper), butler/telegram_bot/{media.py,news.py,queue.py,service.py,config.py}, tests/test_telegram_media*.py.

- [x] RED tests: strict image store IDs/type/size; photo-only input; grouped photos; duplicate/late album members; stable recipient packages and unknown network outcomes.
- [x] Implement media store, getFile download and binary registration, image grouping and package fanout. Retain legacy text path when optional media capability disabled. Network and image assembly stay outside UI thread.
- [x] `push_bundle_to_wxbot(cfg,contact,items,request_id,log=None)->(ok,detail)` and `push_news_bundle(cfg,contact,items,request_id)->{state,reason}`.
- [x] Publish Bot identity snapshot atomically, read relay include_images from shared settings path. No new credentials or polling instance.
- [x] Run focused tests and report exact interfaces/evidence; no shared server/core edits.

## Task 2 — wxbot package transport and image sending (agent image_delivery)

Own: wxbot/{queue_schema.py,queue_store.py,outbound.py,delivery.py}, wxbot/wechat/{image.py,clipboard.py,chat_window.py}, tests/test_image_delivery*.py, tests/test_media_outbound*.py.

- [x] RED tests: forged IDs/paths rejected; package insertion atomic/idempotent; per-recipient text/image ordering; image clipboard restoration and focus/preview/send confirmation fail closed.
- [x] `/send-bundle` resolves images from authenticated Butler `/v1/media/<id>` in HTTP/network context, caches only validated images; all UI remains main thread. QueueStore package insertion must avoid interleaving same-contact items. Update queue schema additively with prior backup.
- [x] `OutboundQueue`/`OutboundRequest` accept optional package fields without breaking text call sites. Root will wire Butler credentials into outbound server construction if needed.
- [x] Image typing/session API analogous to text, checks verified chat, own draft, clipboard and preview. DeliveryPump supports `kind='image'` and whole-package receipts.
- [x] Offline tests and self-review. Do not edit inbox/main/server files.

## Task 3 — settings, Skill and log administration (agent relay_admin)

Own: butler/telegram_relay/{__init__.py,settings.py}, butler/tools.py, plugins/butler-wechat/skills/telegram-relay/**, log/{telegram_relay_admin.py,server.py,index.html,assets/telegram_relay.js,assets/app.js}, config.telegram-relay.example.toml, .gitignore (only runtime config ignore), tests/test_relay_settings*.py/tests/test_relay_admin*.py.

- [x] Implement shared settings contract FIRST and notify agents. Missing config safe/disabled. Validate channel/window/bot settings, no secrets. Versioned atomic edits and admin identity allowlist.
- [x] Skill has `telegram_relay_status`, `telegram_relay_pause`, `telegram_relay_resume`; policy alone does not grant global admin privilege. ToolService accepts configured settings via `relay_settings` property, checks verified contact against admin_contacts. Heartbeats read-only.
- [x] log page GET/POST `/api/telegram-relay` with same-origin/custom action header and safe local Settings access; source values configuration only, no service lifecycle actions.
- [x] Expose all requested settings, per-channel list editing and runtime queue state. No Token in page/config. Root wires Butler `tools.relay_settings` and runtime backend snapshot path.
- [x] Author compact Skill; validate discovery and tool boundaries with offline tests. No Butler server/core edits.

## Task 4 — desktop forwarding, scheduler and HTTP integration (root)

Own: wxbot/telegram_desktop.py, butler/telegram_relay/store.py, wxbot/inbox.py, wxbot/main.py, butler/{server.py,core.py}, tests/test_telegram_desktop*.py/tests/test_relay_integration*.py; docs.

- [x] RED tests for per-channel baselines/idempotence/fairness/recovery, exact Telegram target binding and wxbot/Telegram UI mutual exclusion.
- [x] Implement UIA adapter with configurable selectors, reliable message IDs/permalinks, protected-content detection and bounded native forwarding state machine. Unknown identities/UI outcomes must remain explicit calibration/uncertain states, never invent forwarding success.
- [x] MainInbox schedules relay only at safe UI boundaries, with no concurrent worker mouse operations; preserves active WeChat transaction. Relay changes stop unsubmitted work and preserve cursor.
- [x] Wire authenticated media/bundle endpoints and admin tools configuration. No runtime changes.
- [x] Run integrated/full offline tests, syntax, diff check. Independent review, fix relevant issues, docs and truthful live-UI calibration limitations.

## Final verification (2026-10-26)

Implementation and independent review are complete. Related offline feature tests: 191 passed. Full repository suite: 851 passed, 3 previously reproduced baseline failures; see the SDD verification report. Skill validation, Python compilation, JavaScript syntax and git diff whitespace checks passed. Real Telegram/WeChat calibration and live end-to-end sending remain installation validation steps; no services or real routes were activated.
