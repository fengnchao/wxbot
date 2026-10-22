# Butler / Codex integration v1

The application owns identities, authorization, SQLite business records, scheduling
and delivery. The plugin owns portable role/tool instructions. The official Python
SDK (0.163.0 with its pinned runtime) owns Codex threads and model turns.

## Application boundary

Existing `/v1/handle`, `/v1/reset`, `/v1/push`, `/health` contracts are retained.
Authenticated `GET /v1/skills` returns `{object:"list",data:[...]}`; each entry has
name, description, category, tags and the tools requested by that skill.
`GET /v1/runtime` returns backend, protocol_version, memory, reminders and events.
Administrator tokens are never returned to the dashboard.

`POST /mcp` implements stateless Streamable HTTP JSON-RPC: initialize, ping,
tools/list, tools/call and initialization/cancellation notifications. There is no
SSE subscription or persistent MCP session. The server is loopback-only.

MCP bearer credentials bind owner, contact, validated policy, read-only flag,
request id and expiry. Model arguments cannot override owner/contact/uid/profile.
Worker aliases point to a fresh signed capability for each turn and are revoked
when a turn finishes. The policy file is checked again on each invocation.
Tool names are the intersection of the implemented catalogue and allowed skills.
Write operations are transactional and idempotent by owner/request/call id.

## State and isolation

Scope hashes include identity, selected role, allowed skills and chat/heartbeat
kind. Thread IDs persist in business.sqlite3. Workers are bounded and evicted while
idle. Separate scopes never share a mutable runtime client or MCP capability.

Only selected instruction files are copied into a scope workspace. Role text is
injected as developer instructions; linked references can be read through the
same authorized skill_read endpoint. Native shell/browser/apps are disabled and
the filesystem policy grants read access only to that scope workspace. Host code
mode remains enabled because current Codex MCP tools use that execution bridge.
Personal Codex settings/auth are not copied into the bot environment.

Only completed turns with a complete final agent item produce replies. Tool
arguments, reasoning, credentials and raw provider responses are excluded from
flow events. Failed or interrupted turns return reply_complete=false.

## Extending skills

Add a directory with SKILL.md and YAML frontmatter. Use metadata.butler.tags:
`[butler-role]` for personas or `[butler-tool]` for functional instructions.
Functional skills declare metadata.butler.tools using implemented tool names.
Adding a skill never creates executable authority on its own. New executable
tools must be registered and authorized in ToolService as well.

Role tags from metadata.hermes are accepted for compatibility of supplied role
files. Setup skills are excluded from the chatbot catalogue and cannot be granted.
