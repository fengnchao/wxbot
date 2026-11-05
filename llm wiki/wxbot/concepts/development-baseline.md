---
type: concept
module: wiki
summary: 按实际工作树与解释器确定开发基线，区分当前配置、生产模型链路与历史布局
coverage: overview
last_verified: '2026-11-05'
sources:
- path: README.md
  line: 125
  anchor: '## 开发基线与历史布局'
- path: README.md
  line: 595
  anchor: '## 配置'
- path: pyproject.toml
  line: 1
  anchor: '[project]'
- path: src/butler/defaults.py
  line: 4
  anchor: 'def butler_defaults():'
- path: src/butler/defaults.py
  line: 13
  anchor: 'def wxbot_defaults():'
- path: src/wxbot/config.py
  line: 110
  anchor: def load_config(
- path: src/wxbot/main.py
  line: 29
  anchor: def build_processor(
- path: src/wxbot/wechat/typing.py
  line: 178
  anchor: ClipboardLease(self.chunks[self.index])
- path: src/wxbot/wechat/typing.py
  line: 201
  anchor: auto.SendKeys('{Ctrl}v'
- path: src/dashboard/http.py
  line: 88
  anchor: WEBAPP_DIR = os.path.join(str(REPO_ROOT), 'web', 'dist')
changes:
- raw/changes/2026-11-03-development-doc-baseline
- raw/changes/2026-11-04-root-workspace-unification
- raw/changes/2026-11-04-index-tts-skill
- raw/changes/2026-11-04-contact-index-tts
- raw/changes/2026-11-04-webui-preset-binding
- raw/changes/2026-11-04-webui-preset-graph-note
- raw/changes/2026-11-05-contact-policy-save
- raw/changes/2026-11-05-group-auto-voice
---
# 开发基线与历史布局

## 术语与状态含义

基线由工作目录、Git 分支、HEAD SHA、未提交修改及解释器实际导入的代码共同确定。
`main`、正式运行目录和开发 worktree 可以处于不同进度；分支名或“曾经同 SHA”不能证明当前内容相同。
当前代码与运行进程已加载的版本也不是同一件事（`README.md:125` 开始的核对流程）。
若 `.venv` 的可编辑安装指向另一工作树，必须先识别差异，不能把另一份代码的通过结果当作本轮证据。

## 业务规则与边界

- 配置来自 `src/butler/defaults.py:4` / `:13` 等无凭据默认值，经安装向导生成；当前仓库没有独立示例 TOML。
  实际名字是 `config.butler.toml`、`config.wxbot.toml`、`config.log.toml`（`README.md:595`）。
- Python 依赖以 `pyproject.toml:1` 的声明和 uv.lock 精确版本为准；requirements.txt 是兼容 pip 清单，不能据旧注释断言 Butler 无第三方依赖。
- 生产默认 wxbot→Butler→模型；Butler 自身的 Hermes、OpenAI 兼容 API 等 provider 是正常接入方式。
  wxbot 的直接适配器属于旁路调试／旧配置兼容；带 installation 配置时禁止非 butler backend（`src/wxbot/main.py:29`）。
- 正文发送使用 `ClipboardLease` 后执行 Ctrl+V，再读回校验；控制键仍由 UI 自动化执行（`src/wxbot/wechat/typing.py:178`、`:201`）。
  默认分批间隔为 0.25 秒；full/chunked/streaming 均使用粘贴，见 `README.md:595` 后的发送章节与 `src/butler/defaults.py:13`。

## 跨层映射

[[modules/runtime]] 负责配置生成，[[modules/models]] 定义 Butler 的模型后端，[[modules/wxbot]] 持有正文粘贴与发送确认。
[[modules/web]] 的产物由 `src/dashboard/http.py:88` 的 WEBAPP_DIR 在 /app/ 提供，不由已退场的 log/server.py 提供。
[[modules/wiki]] 的 CLI 支持 `--repo-root` 显式限定开发图谱范围，不授予运行时身份或操作权限。
本次没有 API/DTO、数据库字段／迁移或异步任务变更。

## 历史坑与冲突

旧 butler/README.md、PROJECT_MEMORY.md、kmg/、hermes_butler、固定安装路径和嵌套包名不再代表当前 src/ 布局。
它们在本轮工作分支中已不存在，不能重建旧入口来满足过期说明。根 heartbeat/ 仍含受版本控制的辅助看门狗脚本，
与 src/butler/runtime/heartbeat.py 的业务心跳分开；不把整个目录忽略或删除（`README.md:125`）。
2026-11-03 的文档核对仅用显式 --repo-root 限定图谱范围，当时没有修复可编辑安装。
2026-11-04 按用户要求由主目录接管最新 main，并在主目录自己的 .venv 中离线重装本项目；
随后从仓库外以隔离模式验证四个包及 REPO_ROOT 均来自主目录 src/。
这是开发环境绑定的核验，不证明现有进程已重新加载代码；本次未启动或重启服务。
另一个 worktree 及其独立配置、数据仍保留，不能把代码目录统一当成数据库或认证迁移。

## 相关模块、接口、测试

关联 [[modules/wiki]]、[[modules/runtime]]、[[modules/models]]、[[modules/wxbot]]、[[modules/web]]。
使用静态语义等价检查确认 Python 执行 AST、Vite 执行配置、依赖项和锁文件未变；前端构建写入临时目录并运行既有假数据冒烟。
没有新增测试；本次不改变 UI 行为、真实配置、凭据或运行数据，也不启动／重启服务。

## 代码依据与修改来源

来源与锚点见本页 sources；完整核对范围、八项问题的实际处置和验证记录见
[[impacts/2026-11-03-development-doc-baseline]] 与 [[raw/changes/2026-11-03-development-doc-baseline]]。

环境绑定后续处理见 [[impacts/2026-11-04-root-workspace-unification]] 与
[[raw/changes/2026-11-04-root-workspace-unification]]；历史 raw 保持原样。


## 本次核对

[[raw/changes/2026-11-04-index-tts-skill]]：对照本次源码 diff 复核来源与行号；新增预设语音路径见 [[apis/index-tts]]，其余已述契约未改。


## 联系人语音配置核对

[[raw/changes/2026-11-04-contact-index-tts]]：新增会话授权控件与原接口消费，源码位置已核对；后端契约保持。


## 联系人语音配置核对

[[raw/changes/2026-11-04-webui-preset-binding]]：接入网页预设列表与会话默认绑定；原有接口保持，新增接口及可选音色参数见 [[apis/index-tts]]。


图谱契约说明来源：[[raw/changes/2026-11-04-webui-preset-graph-note]]。


## 策略保存复核（2026-11-05）

本次 src/dashboard/http.py 仅细化未知技能校验错误；WEBAPP_DIR、/app/ 静态文件来源与安装基线规则未改。保存锁等待修复见 [[apis/dashboard-contact-policy]]。来源 [[raw/changes/2026-11-05-contact-policy-save]]。


## 群聊采集与自动语音复核（2026-11-05）

README 追加自动语音真实 WebUI 默认、配置热读和窗口越屏恢复说明；安装路径、静态文件位置及图谱 CLI 合同不变。功能依据见 [[concepts/automatic-voice-reply]]、[[concepts/capture-viewport]]。来源 [[raw/changes/2026-11-05-group-auto-voice]]。
