# Codex plugin and portable Butler distribution

Approved scope: the user's implementation request in this conversation. Deliver
`plugins/butler-wechat`, a Git marketplace, an isolated Codex backend, enforced
per-contact tools/skills, fresh local memory/reminders, portable initialization,
diagnostics, and log integration. Preserve HTTP and wxbot queue contracts.

1. Portable configuration, plugin catalogue, SQLite business storage and tools.
2. Official Python SDK backend, isolated worker scopes and persistent threads.
3. Butler integration, durable reminders and read-only heartbeat.
4. Log configuration/catalogue/runtime views and distributable setup.
5. Offline regression suite, real Codex probe without WeChat, release inspection.

Constraints: no importing Hermes data, no automatic service restart, no real
WeChat test messages, no credentials or personal runtime state in distribution.
Keep existing uncommitted work. Tests and local Codex inference are authorized.
