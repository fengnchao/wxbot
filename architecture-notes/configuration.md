# 配置管理

实际配置由本安装的 config.*.toml 提供。管理台显示脱敏值并使用版本校验、备份和原子保存；模型字段影响后续请求，其他启动字段需使用者手动重启相应服务。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 使用说明

- [wxbot / Butler / 配置](#doc-c12f2710f3c6a2) · `README.md`

<a id="doc-c12f2710f3c6a2"></a>

### wxbot / Butler / 配置

来源：`README.md:597`。

#### 配置

- Python 3.14+；依赖声明以 `pyproject.toml` 为准，精确版本以 `uv.lock` 为准。
  `requirements.txt` 保留为兼容 pip 安装清单；Butler 也依赖 `tomlkit`、`croniter`、`PyYAML`
  和 Codex SDK 等第三方包，并非纯标准库。每个开发 worktree 使用自己的 `.venv`。
- 配置由 `src/butler/defaults.py` 的无凭据默认值和安装向导生成：运行 `python -m butler setup`，
  或用幂等的 `python -m butler init` 初始化并保留已有配置。当前仓库不提供独立示例 TOML 文件。
  实际文件名分别是 `config.butler.toml`、`config.wxbot.toml`、`config.log.toml`，不统一改成
  `config.toml`；这三个运行配置均已在 `.gitignore` 中排除，含 token/key 的文件不要提交。
- 相对运行路径以对应配置文件所在目录为基准，切换工作目录不会改变数据库或队列位置。
- 管理台自身配置是 `config.log.toml`（`LOG_CONFIG` 可覆盖）；命令行与环境变量优先于文件。
- 队列默认 `cache/wxbot_queue.sqlite3`；业务数据在 `data/business.sqlite3`；
  Codex 登录与会话在 `data/codex/`；知识图谱在 `data/knowledge/`（一人一个 vault）。
  这些目录与所有实际配置均不提交。
- `[knowledge]` 控制知识图谱：`enabled` 默认开，`auto_extract` 与 `auto_prune` 默认关，
  需要显式打开；其余键见下一节。
<!-- end-migrated-part: doc-c12f2710f3c6a2 -->
