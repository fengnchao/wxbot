---
type: impact
status: verified
date: '2026-11-03'
---
# 开发文档与技术基线口径核对

## 范围和核对结果

- 根 README、requirements 注释、前端包描述、Vite 注释与两个 Python 模块说明需要对齐；不改业务逻辑。
- 当前源码采用 src/ 布局；butler/README.md、PROJECT_MEMORY.md、旧示例 TOML 与嵌套包目录已不存在，不重建旧入口。
- 安装配置来自 src/butler/defaults.py，经 runtime/install_wizard.py 生成 config.butler.toml、config.wxbot.toml、config.log.toml；不能复制实际配置或凭据来造示例。
- 生产默认 model.backend=butler。Butler 后端可使用 Hermes、OpenAI 兼容 API 等；wxbot 直接适配器是另一个层级，仅保留旁路调试与旧配置兼容。
- 发送正文通过 TypingSession + ClipboardLease + Ctrl+V，默认 chunk_interval=0.25 秒。此次仅更正文档，不执行微信操作。
- heartbeat/ 当前含受版本控制的辅助脚本，不把整个目录当成运行残留忽略或删除。
- 核对时正式目录在 codex-butler-distribution，开发 worktree 在 codex/grok-setup 且多一个 WEB-001 提交；不能把“两个 tip 同 SHA”写成长期事实。实际运行进程加载版本不在本轮核验范围。
- 原目录 .venv 的 common.paths 实际来自开发 worktree；本轮图谱操作显式传 --repo-root 绑定当前仓库，不把另一个工作树的结果当作当前证据，不自动修改可编辑安装或运行服务。

## 影响面、调用方与契约

安装消费者是 setup/install_wizard；正文发送消费者是 wxbot UI 主线程；前端产物由 src/dashboard/http.py 在 /app/ 提供。只改变说明、注释与 package description，配置值、HTTP/API/DTO、数据库及迁移、前端交互、异步任务均不变。

## 图谱与验证

新增开发基线概念页，与 modules/wiki 互相链接；复核 README 来源行号与完整文件摘要。原图谱未覆盖工作树基线和历史布局区别，本次补充。

验证依赖与锁文件不变、Python 非文档 AST 不变、Vite 非注释内容不变、package.json 除 description 外不变，并运行图谱 ingest/lint 与 git diff --check。无需重启服务、真实发送、模型调用或发布打包；回滚仅需撤销本轮文档/注释/元数据与配套图谱差异。
