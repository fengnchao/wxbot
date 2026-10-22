# Butler/wxbot development and installation

Read README.md and docs/CODEX_INSTALL.md for portable setup. Use the installation
owner's own Codex login. Never copy credentials, local config or runtime data from
another installation. `python -m butler init` preserves existing configurations.

Business operations belong in Butler services; model backends implement the
shared backend interface; wxbot owns Windows UI interaction and the delivery queue.
Role and skill instructions are under plugins/butler-wechat. Tool execution must
validate the service-issued identity and permissions; prompts are not authority.

Never automatically restart existing services. Do not send real WeChat test
messages without explicit authorization. Use temporary data and fake delivery for
tests. tests/conftest.py forbids accessing the real clipboard in offline tests.

Before preparing a release, run authorized checks and tools/release.py; never
commit auth.json, config.*.toml runtime files, data/, cache/, virtual environments
or databases. Keep *.example.toml templates credential-free.
