# Unified contacts implementation plan

> **For agentic workers:** Use focused parallel implementation tasks with TDD and a final independent review. Preserve existing uncommitted work.

**Goal:** One authoritative SQLite contact source and one management entry, merging same-named people while retaining group nicknames, existing settings and delivery destinations.

**Architecture:** Reuse user_profiles/user_bindings for people and membership identity. Add a versioned unified_contacts state in the same database for conversations (routes/listening/policy/subscriptions), global channel settings and unresolved nickname observations. Legacy directory/policy/group interfaces project from this state after explicit migration; old installations retain their readers until migrated.

**Tech Stack:** Python 3.14+, SQLite, existing JavaScript/HTML/CSS, pytest and in-memory DOM checks. No new dependency.

**Spec:** docs/superpowers/specs/2026-10-30-unified-contacts-design.md (approved by user on 2026-10-30).

## Global constraints

- User explicitly approved same-name merging across groups, shared personal memory, and preserving group/nickname relations.
- Preserve service-issued identity validation, disabled bindings, current route/profile/session values, policy/heartbeat switches and subscription destinations.
- Do not restart services or send real WeChat messages. Do not migrate live data until old writers are stopped; prepare read-only preview and verified temporary migrations.
- Preserve previous heartbeat path fixes, unrelated IDE changes and tracked bytecode deletions. Work in this existing feature checkout; do not commit unrelated work.
- Three baseline failures already independently reproduced at HEAD: test_queue_admin::test_multipart_cli_sent_and_retry_preserve_other_parts, test_queue_store::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker, test_typing::test_typing_steps_keep_half_second_between_batches_and_one_final_enter.

## Shared interfaces

New butler/contact_store.py:
- is_unified(path) -> bool: read-only, false for missing/inactive state.
- ContactStore(path): database service; explicit construction creates additive schema, never imports legacy data automatically.
- snapshot() -> {version:int, conversations:list, settings:dict, aliases:list, person_policies:dict}.
- conversation: {id:str,name:str,channel_type:'dm'|'group',uid:str,profile:str,label:str,session_key:str,listening:bool,enabled:bool,person_id:str,policy:dict|None,subscriptions:list[int]}. A group's person_id is empty. Preserve route values. Unknown passive routes are disabled for listening but retained.
- save(state, expected_version:int) -> snapshot: transaction, optimistic version, validates names/types/IDs/policies/subscriptions; unrelated fields preserved.
- activate(state, expected_version:int=0) -> snapshot: explicit successful migration flag, same transaction; is_unified remains false before it.
- contact_rows() -> legacy route list for enabled conversations; channel_projection() -> legacy derived bound_users/groups plus global settings.
- policies() -> dict[name,policy]; set_policy(name,policy) -> policy; groups() -> dict[str,list[str]]; set_groups(groups) -> dict.
- directory_snapshot() -> legacy {contacts,channel,aliases,version}; save_directory(payload,expected_version) -> projection. Never persist duplicate bound lists in canonical state.
- observe_member(group,member_key,name) and member_name(group,member_key) preserve display evidence, not permissions.
- from_config(cfg) -> ContactStore|None: cfg.contacts.path or cfg.contact_database if active; database path is not conveyed through a fake JSON filename.

Identity helper in butler/contact_identity.py (owned by identity task):
- normalize_name(value) -> str: NFC + trim, empty for placeholder names.
- merge_same_named(db) -> report; merge_users(db,source_id,target_id) -> report. Existing SQLite connection/transaction required. Deterministic private-first/oldest-ID survivor, redirects and conflict variants retained.
- reuse_person(db,nickname) -> user_id|None only when unified schema active (during migration explicit merge_same_named may run before activate).
- conflict_memories(db,user_id) -> list of source-labeled variants for shared recall/UI.

Migration task consumes these exact interfaces; UI task may add business-facing helpers in butler/contact_admin.py rather than reaching into storage from JavaScript. UserRegistry remains identity/memory authority.

## Review focus

- Names present only in listening/policy/subscription files must survive migration without enabling passive observations.
- Same-name memory conflicts retain both values and sources; disabled identities stay disabled.
- Rename and different group nicknames keep stable relationships; ambiguous proactive @ never chooses an arbitrary member.
- Custom relative paths, log overrides and repeated migrations remain deterministic; invalid/conflicting source files fail before activation.
- Migrated newsletter/Telegram readers cannot fall back to old JSON after activation.

## Task 1: canonical conversation storage and compatibility adapters (root)

Files: create butler/contact_store.py, tests/test_contact_store.py; modify butler/directory.py, butler/config.py, butler/core.py, butler/skill_policy.py, butler/groups.py and newsletter subscriber adapters as needed.

- [x] Write/run failing tests for one canonical contact, generated listening projections, policy/group updates and version conflicts.
- [x] Implement schema, activation, transactions and projections; no activation by normal reads.
- [x] Switch existing runtime services through active database adapters, preserving legacy behavior when inactive.
- [x] Verify migrated readers ignore changed/deleted old JSON and all subscriber paths agree.

## Task 2: people, same-name merging and shared memories (identity worker)

Files: create butler/contact_identity.py, tests/test_contact_identity.py; modify butler/user_registry.py only (other core modules remain root-owned).

- [x] Write/run failing tests for same-name cross-group reuse, same person different nicknames via explicit linking, placeholder handling, disabled state and source-labeled memory conflicts.
- [x] Implement helpers and UserRegistry hooks gated on active unified schema, preserving old-install isolation tests.
- [x] Ensure memory recall and admin memory results expose retained conflicts; existing binding IDs and member/observation rows survive.
- [x] Run identity, recall and related tests using temporary data.

## Task 3: explicit migration, installation and switch instructions (migration worker)

Files: create butler/contact_migration.py and tests/test_contact_migration.py; modify butler/upgrade.py, butler/__main__.py, butler/install_wizard.py and docs/CODEX_INSTALL.md/README.md as required. Do not edit existing butler/migration.py (legacy importer remains compatible).

- [x] Write/run failing tests for preview purity, union of sources, idempotence, backups, exact role/subscription preservation and failure rollback.
- [x] Implement preview_contacts(root)->dict and migrate_contacts(root, *, acknowledge_stopped=False)->dict. Explicit migration refuses mutation unless acknowledged stopped; CLI adds contacts-preview and contacts-migrate --acknowledge-stopped, and refuses occupied configured service ports for migration.
- [x] Import source paths using owning config directory, including log group override. Conflicting effective sources produce a preview error; malformed policy files never become empty configuration.
- [x] Reuse existing directory migration first only inside acknowledged/temporary workflow. Backups use SQLite backup, exclude credentials from reports, do not delete old source files; migration marks them retired and all readers use DB thereafter.
- [x] New installation initializes empty active canonical state without recreating policy/group JSON; existing installs never silently activate on ordinary start.
- [x] Test exact destination preservation, aliases and user binding/name merge, and document manual cutover/rollback.

## Task 4: single contact management page/API (UI worker)

Files: create butler/contact_admin.py, log/assets/contacts.js, tests/test_contact_admin.py and tests/contacts_frontend_checks.js; modify log/server.py, log/config_view.py, log/config_editor.py, log/index.html, log/assets/app.js/common.js/configuration.js/dashboard.css as needed. Preserve existing uncommitted heartbeat fixes. Do not edit butler/contact_store.py or identity/migration task files.

- [x] Write/run failing service and DOM tests for one person with multiple groups, creation/edit/version conflicts and one navigation entry.
- [x] Add /api/contacts GET and POST backed by Butler service module. Use existing local-only confirmed-origin validation for writes; catalogue validation for roles/tools; no browser-selected filesystem paths.
- [x] Service list result: {active:bool,version:int,rows:[{id,kind:'person'|'group',name,enabled,conversations:[],memberships:[],memory_count,policy}],total:int}. Detail GET ?id=...; writes {action,version,...}, updated snapshot/version. Implement create, person edit/rename, conversation edit, policy/subscription save, existing binding association via UserRegistry, memory UI reuse.
- [x] One Contacts nav entry; old users/heartbeat/groups links redirect to contacts sections. News configuration still available from Contacts subscription section. Existing users.js memory dialogs can be reused, but do not show an independent people list.
- [x] Config inventory exposes canonical source read-only and contact-entry link; migrated policy/group/directory fields must not be separately writable. Preserve old-install configuration behavior.
- [x] Inactive installations display preview/cutover guidance; UI must not silently import runtime data.

## Task 5: integrate, review and verify (root)

- [x] Inspect worker diffs and resolve interfaces. Run focused new regression tests and affected existing suites.
- [x] Run full offline pytest; report baseline failures by name and compare against prior baseline. Run JS checks and diff whitespace validation.
- [x] Independent read-only review of implementation against approved spec; fix correctness issues with regression tests.
- [x] Produce read-only real-install migration preview and concrete manual cutover commands. No live mutation while services are running, no service restart, no real test messages.
- [x] Update spec/plan completion evidence and deliver changes plus activation steps and any actual limitations.

## Verification result

Final full offline pytest: 1229 passed, 3 pre-existing failures in 88.76 seconds. Both contacts and existing dashboard Node checks pass; git diff --check passes. Three independent-review findings reproduced RED then fixed GREEN: current-group-name rename merge, stale unified version after registry edits, runtime-discovered DM route creation. Additional pending-route/global group nickname checks pass.

Actual installation was read only. Staged copy simulation produced 21 people, 2 group conversations, 11 identity merges, retained 2 role policies and 3 subscription destinations, no memory conflicts. Live state remains inactive, waiting for manual stopped-writer cutover. See ../verification/2026-10-30-unified-contacts.md.
