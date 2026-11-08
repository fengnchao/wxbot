# 冯草草

本文件保存该架构节点的说明、相关契约与历史依据。

[项目入口与节点索引](wxbot.md) · [Butler](butler.md) · [队列](queue-storage.md) · [管理台](dashboard.md)

文档于 2026-11-07 归并。下方保留来源文件、旧元信息和历史记录；遇到口径冲突，以当前源码、当前配置说明及日期较新的明确更正为准。历史计划和旧验证结果不表示本轮已执行。

## 原图节点说明

### 冯草草

架构图的中心节点。内部展示 Butler，右侧的 Skill 分支列出角色能力。

## 使用说明

- [wxbot / Butler / 小潮常驻角色](#doc-f544399fcbaca7) · `README.md`

<a id="doc-f544399fcbaca7"></a>

### wxbot / Butler / 小潮常驻角色

来源：`README.md:820`。

#### 小潮常驻角色

小潮随本机 Butler 服务启停。空闲时用专用 Edge 浏览抖音网页版推荐流，有微信聊天请求进入 Butler 时暂停。每轮观察到播放进度才写一条本机日记，记录可核对的标题、链接和播放时长。配置为 OpenAI 兼容接口或 Ollama 时，可通过独立的纯文本模型入口整理一条简短感想。其他后端使用事实版日记。

在项目目录安装可选依赖，并为小潮的专用 Edge 登录一次。

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e ".[resident]"
.\.venv\Scripts\python.exe -m butler resident-login
```

在 `config.butler.toml` 追加以下配置，再自行启动或重启 Butler。时长均为秒，所有时长项可省略以使用下列默认值。

```toml
[resident_role]
enabled = true
idle_seconds = 300
round_seconds = 180
cooldown_seconds = 1800
daily_seconds = 900
visible_browser = false
```

配置缺省时功能关闭。`data/resident/xiao-chao/` 保存小潮的浏览器资料、`state.json` 和 `diary/` 目录。每日额度按北京时间结算，计入浏览活动的加载与换片时间，进程重启后沿用已用额度。账号需要重新登录或验证时，用同一条 `resident-login` 命令处理即可恢复。`enabled = false` 在下次 Butler 启动时停用角色。

设 `visible_browser = true` 并重启 Butler 后，观看时会打开专用 Edge。如果抖音要求登录或安全验证，小潮会保留同一个窗口，最多等待 10 分钟。处理完保持该窗口打开，确认页面回到推荐视频后会按空闲规则继续。等待时间不占用每日观看额度。关闭窗口或等待超时后，可用 `resident-login` 准备下次重试。

本机管理台的「用户与任务 → 小潮日记」按时间展示 `diary/` 中已有的日记和作品链接。页面通过 `GET /api/resident/diary?page=1` 每页读取 20 条，使用工具栏刷新读取新日记。
<!-- end-migrated-part: doc-f544399fcbaca7 -->

## 技术资料

- [管理台小潮日记接口](#doc-38ef2f5a72288d) · `llm wiki/wxbot/apis/dashboard-resident-diary.md`
- [小潮常驻角色](#doc-81303bd5af31f1) · `llm wiki/wxbot/symbols/resident-role.md`

<a id="doc-38ef2f5a72288d"></a>

### 管理台小潮日记接口

来源：`llm wiki/wxbot/apis/dashboard-resident-diary.md:1`。

```yaml
type: api
module: dashboard
summary: 从 Butler 数据目录只读分页展示小潮日记和已核对的作品链接
coverage: core
last_verified: '2026-11-06'
sources:
- path: src/dashboard/api/resident_diary.py
  line: 38
  anchor: 'def read(ctx):'
- path: src/dashboard/api/resident_diary.py
  line: 16
  anchor: 'def _entry(path, day, updated_at):'
- path: src/dashboard/routes.py
  line: 64
  anchor: '("GET", "/api/resident/diary", resident_diary.read),'
- path: web/src/views/ResidentDiaryView.vue
  line: 25
  anchor: "apiGet('/api/resident/diary?page=' + page)"
- path: web/src/router.js
  line: 13
  anchor: "id: 'resident-diary'"
changes:
- raw/changes/2026-11-05-resident-diary-web
```
### 管理台小潮日记接口

`GET /api/resident/diary?page=1` 属于 [modules/dashboard](dashboard.md#doc-bb47c9474691fe) 本机业务接口。目录由配置指定的数据根与 [symbols/resident-role](resident.md#doc-81303bd5af31f1) 的 `resident_root` 组合，请求只提供页码。远端模式由现有路由门禁返回 503。

响应包含 `entries`、`page`、`pages`、`total`，每页 20 条。文件按文件名日期、修改时间和稳定名称倒序。条目包含 `id`、`date`、`updated_at` 秒时间戳、`note`、`videos`。只读取命名匹配的常规 Markdown，跳过临时文件、链接和超过 64 KiB 的文件。目录不存在返回空页。无法读取时提供 500 错误。

作品条目包含 `title`、`seconds` 和 `url`。链接匹配抖音规范作品地址。格式无法识别时保留纯文本，Vue 不解释任意 HTML。[modules/web](dashboard.md#doc-aeec90dfe23cd3) 的小潮日记页复用主壳刷新，翻页写入地址栏。没有数据库迁移或写入接口。

来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。
<!-- end-migrated-part: doc-38ef2f5a72288d -->

<a id="doc-81303bd5af31f1"></a>

### 小潮常驻角色

来源：`llm wiki/wxbot/symbols/resident-role.md:1`。

```yaml
type: symbol
module: runtime
summary: 常驻角色按聊天空闲调度抖音观看，持久化额度与本机日记
coverage: core
last_verified: '2026-11-06'
sources:
- path: src/butler/runtime/resident.py
  line: 91
  anchor: 'class ResidentRole:'
- path: src/butler/runtime/resident.py
  line: 20
  anchor: 'class ForegroundActivity:'
- path: src/butler/runtime/resident_douyin.py
  line: 91
  anchor: 'class DouyinBrowser:'
- path: src/butler/runtime/resident_douyin.py
  line: 126
  anchor: 'def _follow_recommend_link('
- path: src/butler/runtime/resident_douyin.py
  line: 144
  anchor: 'def _wait_for_access('
- path: src/butler/config.py
  line: 22
  anchor: 'class ResidentSettings:'
- path: src/butler/server.py
  line: 513
  anchor: 'def serve(cfg: Config) -> int:'
- path: src/butler/__main__.py
  line: 47
  anchor: "if args.command == 'resident-login':"
- path: plugins/butler-wechat/resident/xiao-chao.md
  line: 1
  anchor: '# 小潮'
changes:
- raw/changes/2026-11-05-resident-xiaochao
- raw/changes/2026-11-05-resident-diary-web
- raw/changes/2026-11-06-resident-visible-edge
- raw/changes/2026-11-06-resident-recommend-navigation
```
### 小潮常驻角色

`serve` 在 `[resident_role].enabled` 开启时创建小潮并启动后台线程，退出时停止。有效同步和流式请求使用同一并发计数。所有聊天请求完成后重新计空闲。关联 [modules/runtime](butler-functions.md#doc-241e7c8bdd1c05)、[apis/butler-handle](butler.md#doc-4f70359e7ae440)、[apis/butler-handle-stream](butler.md#doc-5135f5350303bc)。

[modules/plugin](resident-skills.md#doc-709338d3e083eb) 分发小潮的角色正文，供后台日记使用。小潮拥有独立数据目录和浏览器会话。日记通过无业务工具的纯文本后端整理，模型不可用或前台忙时回退事实版。权限边界见 [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)。

Playwright 使用专用 Edge profile。登录命令在可见浏览器中由使用者操作。活动缺省使用无窗口模式，`visible_browser = true` 时打开专用窗口。该窗口遇到登录或验证要求会等待用户，整轮累计最多 10 分钟。识别到有效登录和作品页面后复核空闲条件，再在同一窗口继续。等待期间暂停自动换片，时间不计入观看额度。作品身份和同一来源的连续播放进度用于确认实际观察。日记记录可核对的标题、链接和播放时长。

`state.json` 保存北京时间日期、已用秒数、冷却、登录等待和最近日记文件。单飞锁内先预留本轮额度，结束后按浏览器活动用时退还未使用的部分，加载和换片也计入。中断时保留已核对的观察。遇到验证时，已经获得观看记录的轮次仍保留冷却。日记按一次活动一个独立文件写入。

来源 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。

#### 小潮日记接入核对

日记生成后可从 [apis/dashboard-resident-diary](resident.md#doc-38ef2f5a72288d) 查看。网页只读现有日记，数据根仍由 Butler 配置决定。 来源 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。

`verification_required` 代表正在专用窗口等待人工处理。已结束的 `login_required` 记录由登录标记和浏览器模式共同决定是否继续等待，旧记录按无窗口处理。来源 [raw/changes/2026-11-06-resident-visible-edge](resident.md#doc-eb3bb4d27e3f68)。

推荐流使用带 `from_nav=1` 的入口。浏览器落到抖音「精选」且未识别到作品时，本轮可通过页面内唯一且符合站内推荐路由的「推荐」链接重试一次。人工验证完成且登录有效后也支持此回退。导航前仍检查取消、前台请求和本轮时限。来源 [raw/changes/2026-11-06-resident-recommend-navigation](resident.md#doc-b2141987114c61)。
<!-- end-migrated-part: doc-81303bd5af31f1 -->

## 历史记录

以下为来源原文归档，包括实施计划、影响报告和当时的验证结果；请勿把旧命令或计划自动当成现行操作。

- [小潮常驻角色实施计划](#doc-68e9f87f4924a8) · `docs/superpowers/plans/2026-11-05-resident-xiaochao.md`
- [管理台小潮日记](#doc-5b4e90fba08643) · `llm wiki/wxbot/impacts/2026-11-05-resident-diary-web.md`
- [小潮常驻与空闲刷抖音](#doc-6323d188bd37df) · `llm wiki/wxbot/impacts/2026-11-05-resident-xiaochao.md`
- [小潮在同一个 Edge 窗口等待验证](#doc-6cee41da4b9fa7) · `llm wiki/wxbot/impacts/2026-11-06-resident-visible-edge.md`
- [管理台查看小潮日记](#doc-f24e68fc0316c1) · `llm wiki/wxbot/raw/changes/2026-11-05-resident-diary-web.md`
- [复核常驻角色的 README 来源](#doc-3b5de0b90aca6b) · `llm wiki/wxbot/raw/changes/2026-11-05-resident-xiaochao-readme.md`
- [小潮常驻角色与空闲刷抖音](#doc-2d4efb23ee9751) · `llm wiki/wxbot/raw/changes/2026-11-05-resident-xiaochao.md`
- [修复小潮推荐流跳转到精选](#doc-b2141987114c61) · `llm wiki/wxbot/raw/changes/2026-11-06-resident-recommend-navigation.md`
- [小潮有窗口模式与同页验证恢复](#doc-eb3bb4d27e3f68) · `llm wiki/wxbot/raw/changes/2026-11-06-resident-visible-edge.md`

<a id="doc-68e9f87f4924a8"></a>

### 小潮常驻角色实施计划

来源：`docs/superpowers/plans/2026-11-05-resident-xiaochao.md:1`。

### 小潮常驻角色实施计划

**目标** 小潮跟随 Butler 启停，在空闲时短时看抖音，并将一条日记保存在本机。

**设计** [改前影响报告](resident.md#doc-6323d188bd37df)

**实现** Python 3.14、Playwright 的 Edge 持久会话、现有 Butler HTTP 入口。按以下顺序使用隔离测试验证。

- [x] `src/butler/config.py` 与 `src/butler/runtime/resident.py`。覆盖默认关闭、空闲 300 秒、每轮 180 秒、冷却 1800 秒和每日 900 秒。`ForegroundActivity.request()` 覆盖并发聊天。`ResidentRole.tick()` 先预留当日额度，结束后按浏览器活动用时退回未用的部分，失败和登录等待保留状态。
- [x] `src/butler/runtime/resident_douyin.py`。`DouyinBrowser.watch(limit, interrupted, observed)` 使用专用资料目录，只记录同一作品下实际推进的播放进度。登录验证时停止，换片后核对 ID。登录命令使用可见 Edge，活动由无窗口 Edge 执行。
- [x] `src/butler/server.py` 与 `src/butler/__main__.py`。测试开关关闭时不创建角色，启用时随 `serve()` 启停，同步和流式聊天共用前台活动计数。`resident-login` 使用配置的数据目录。角色文本放在插件内独立目录。日记从观察数据生成，支持纯文本后端时整理一次，否则写事实版。
- [x] 完成 36 项相关回归测试，实际 Edge 的离线 HTML 测试通过两条作品的播放和换片。真实抖音登录和推荐流需使用者在专用浏览器登录后验收。README 与知识图谱已更新。
<!-- end-migrated-part: doc-68e9f87f4924a8 -->

<a id="doc-5b4e90fba08643"></a>

### 管理台小潮日记

来源：`llm wiki/wxbot/impacts/2026-11-05-resident-diary-web.md:1`。

```yaml
type: impact
status: completed
date: 2026-11-05
```
### 管理台小潮日记

[symbols/resident-role](resident.md#doc-81303bd5af31f1) 记录日记命名和写入位置。现有 [modules/dashboard](dashboard.md#doc-bb47c9474691fe) 与 [modules/web](dashboard.md#doc-aeec90dfe23cd3) 没有读取日记的契约。

- `src/dashboard/api/resident_diary.py` 复用 `src/butler/runtime/resident.py:43` 的数据根路径和 `:204` 的日记格式。`src/dashboard/routes.py` 注册本机只读 GET，按页返回最新的实际日记、文件时间和可核对作品；路径来自配置，目录为空时返回空列表。
- `web/src/router.js` 与 `web/src/App.vue` 注册「用户与任务 → 小潮日记」，`web/src/views/ResidentDiaryView.vue` 消费分页结果。沿用现有深色主题、刷新和外部接入模式入口规则。正文走 Vue 文本插值，作品链接仅允许规范抖音作品地址。
- 文件读取独立于调度、SQLite 和联系人数据。忽略目录外的文件、链接、非日记文件与临时文件。无写入、迁移或新后台任务。回滚移除路由、读接口和页面即可。
- 验证用临时目录覆盖排序、分页、空态和路径边界，前端冒烟覆盖入口、正文、翻页、刷新及错误态。实际 Vue 路由单独预览。

实现与验证记录见 [raw/changes/2026-11-05-resident-diary-web](resident.md#doc-f24e68fc0316c1)。
<!-- end-migrated-part: doc-5b4e90fba08643 -->

<a id="doc-6323d188bd37df"></a>

### 小潮常驻与空闲刷抖音

来源：`llm wiki/wxbot/impacts/2026-11-05-resident-xiaochao.md:1`。

```yaml
type: impact
status: completed
date: 2026-11-05
```
### 小潮常驻与空闲刷抖音

#### 首版行为

小潮是 Butler 内的独立角色，语气温柔，偶尔开玩笑。启用后随 Butler 服务启停，不需要绑定联系人。第一项活动是空闲时看抖音网页版推荐流。每轮有观看证据就生成一条本机短日记，附实际看到的作品标题和链接。日记归小潮自己，可供用户在本机查看。

建议默认值为前台连续空闲 5 分钟后允许启动，每轮最多 3 分钟，两轮至少间隔 30 分钟，每天最多观看 15 分钟。以服务端收到有效聊天请求作为前台忙碌信号，已收到的请求在处理完成前保持忙碌。首版的信号范围是 Butler 已接收的请求。新请求到来后，在下一条浏览操作前让路，已开始的操作设短超时。关闭 Butler 时停止浏览并退出专用浏览器会话。预算按实际观看时间记账，重启后沿用当日累计。

#### 实现方式

- Butler 内置调度与浏览器适配。由 `runtime/` 管理后台生命周期和任务状态，Playwright 控制单独的 Edge 浏览器资料目录。日常观看使用无窗口模式，以免抢占微信窗口焦点。首次登录或需要验证时暂停活动，由用户显式打开专用浏览器处理，同一份资料同一时间只允许一个实例使用。
- 也可通过第三方抖音工具的本机 HTTP 接口启动和停止观看。该方式能复用现成的观看逻辑，但运行和配置依赖独立服务。首版采用内置方案，以符合只启动 Butler 的要求。

日记整理最多调用一次当前模型，通过隔离的只读入口，输入只含本轮实际取得的标题、链接和可核实的观察。网页内容作为数据处理。模型不可用时保留事实版日记，并明确记录观察范围。角色文本和模型输出均不能授权外发、公开互动或新的工作。首版只提供打开、播放、换片和观察推荐视频所需的操作。

#### 改动位置与调用边界

- `src/butler/server.py:510` 的 `serve` 是启停入口，停止后台任务之后再关闭模型后端。`src/butler/server.py:390` 处的同步与流式聊天共享活动计数，避免重复实现。继续使用现有鉴权及结果契约。[apis/butler-handle](butler.md#doc-4f70359e7ae440) · [apis/butler-handle-stream](butler.md#doc-5135f5350303bc)
- `src/butler/runtime/heartbeat.py:116` 的现有心跳依据联系人策略选择私聊目标。常驻角色有独立状态，调度可参考 `src/butler/runtime/knowledge_auto.py:276` 的单线程、停止信号和失败退避。[modules/runtime](butler-functions.md#doc-241e7c8bdd1c05) · [symbols/knowledge-auto](conversation-extraction.md#doc-8d31785e6eb1e7)
- 角色文本归 `plugins/butler-wechat/`，使用独立运行入口。活动登记和定时归 `src/butler/runtime/`，浏览器操作与角色提示词分开。沿用当前模型配置，日记的模型调用不授予联系人身份或业务工具。[modules/plugin](resident-skills.md#doc-709338d3e083eb) · [concepts/identity-authority](identity-tools.md#doc-8dc39a23945b37)
- 配置复用 Butler 本地 TOML 的解析方式。计划提供开关、空闲时间、每轮时长、冷却和每日时长，启用由用户显式配置。第一版用配置和本地日志查看状态，不新增页面或 API 字段。

#### 持久化、验证与回滚

专用浏览器资料、运行状态和日记保存在 `data/` 下的独立目录。使用一次运行一个编号，写入原子化，以免中断或重试重复生成日记。联系人数据库、消息队列和现有知识库没有 schema 迁移。浏览器资料仅保存在本机。首次没有登录或遇到验证时明确记录等待原因，后续浏览取决于人工处理结果。

离线测试使用假的时间、浏览器和模型，验证服务启停、无联系人启动、聊天优先、并发请求、每日预算、日志与日记、模型失败及登录验证暂停。真正网页的登录和换片另行验证。关闭开关后由用户重启 Butler 即可停用，已生成的日记仍可查看。

现有项目图谱覆盖聊天处理和知识提炼调度，缺少独立角色、空闲任务和浏览器适配。实现后为这些职责补充来源与契约。

参考 [Playwright 持久浏览器会话](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context) · [DSH 抖音助手本机 API](https://github.com/LockyBee/dsh-douyin-agent/blob/main/docs/standalone-api.md)

实现见 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751)。额度计入加载和换片时间，以覆盖暂时未取得作品身份的播放。
<!-- end-migrated-part: doc-6323d188bd37df -->

<a id="doc-6cee41da4b9fa7"></a>

### 小潮在同一个 Edge 窗口等待验证

来源：`llm wiki/wxbot/impacts/2026-11-06-resident-visible-edge.md:1`。

```yaml
type: impact
status: completed
date: 2026-11-06
```
### 小潮在同一个 Edge 窗口等待验证

本机复现显示，已保存的专用浏览器登录态可在无窗口 Edge 中读取。推荐页随后出现可见的安全验证框，触发 [symbols/resident-role](resident.md#doc-81303bd5af31f1) 的登录等待。用户已同意使用有窗口的专用浏览器。

- `src/butler/config.py:22` 新增 `[resident_role].visible_browser`，缺省沿用无窗口模式。本机通过显式配置使用有窗口模式。`src/butler/runtime/resident_douyin.py:122` 在同一浏览器中留出最长 10 分钟等待人工处理登录或验证，识别到已登录且作品页面可用后恢复。停止服务、关闭窗口和等待超时有独立退出路径。
- `src/butler/runtime/resident.py:140` 在状态中记录窗口模式。旧状态缺少字段时按无窗口处理，切换模式可以重新尝试。等待期间停止换片，暂扣的观看额度在本轮结束时按实际活动扣除。恢复浏览前复核前台忙碌与当天额度的时间边界。
- HTTP、管理台页面、日记接口、数据库迁移不涉及。预计触及配置解析、角色线程和独立浏览器。离线使用假时间、页面与浏览器验证恢复、等待上限、暂停和额度。启用需要使用者手动重启 Butler。回滚可将窗口配置关闭。

实现与验证见 [raw/changes/2026-11-06-resident-visible-edge](resident.md#doc-eb3bb4d27e3f68)。
<!-- end-migrated-part: doc-6cee41da4b9fa7 -->

<a id="doc-f24e68fc0316c1"></a>

### 管理台查看小潮日记

来源：`llm wiki/wxbot/raw/changes/2026-11-05-resident-diary-web.md:1`。

```yaml
type: change
title: 管理台查看小潮日记
pages:
- apis/dashboard-resident-diary
- modules/dashboard
- modules/web
- modules/wiki
- symbols/resident-role
- concepts/development-baseline
- apis/dashboard-knowledge
- apis/dashboard-queue
- apis/dashboard-voice-assets
- apis/dashboard-workflow
- tables/knowledge-vault
```
### 管理台查看小潮日记

#### 目标与背景

在本机管理台提供「小潮日记」，读取常驻角色已完成的 Markdown 文件。改前核对见 [impacts/2026-11-05-resident-diary-web](resident.md#doc-5b4e90fba08643)。

#### 文件与代码位置

`src/dashboard/api/resident_diary.py:16` 解码实际日记结构，`:38` 读取并分页。`src/dashboard/routes.py:20,64` 注册本机业务 GET。`web/src/router.js:13`、`web/src/App.vue:26` 注册页面，`web/src/views/ResidentDiaryView.vue:25` 调用接口。

#### 接口与字段

`GET /api/resident/diary?page=1` 返回 `entries`、`page`、`pages`、`total`。每页 20 条。条目含 `id`、`date`、`updated_at`、`note`、`videos`。文件目录来自 Butler 配置。目录不存在返回空列表，外部模式沿用业务路由的 503。共享路由中的其他接口已核对。

#### 数据库与迁移

数据库和迁移不涉及。源文件由 [symbols/resident-role](resident.md#doc-81303bd5af31f1) 写入，管理台只读。日期和 ID 来自文件名，显示时间来自文件修改时间。只读取固定目录中的常规日记文件。

#### 前端消费点

「用户与任务 → 小潮日记」展示日期、正文、可核对的抖音作品与播放时长。正文以文本渲染。刷新沿用主壳，页码保存在地址栏。包含加载、空、错误和正常状态。按项目流程构建 `web/dist/`。

#### 测试与异步任务

离线测试覆盖路径边界、非预期 URL、排序、分页和空态。管理台冒烟覆盖页面入口、文本安全、视频链接、翻页、刷新失败与重试空态。独立预览用隔离日记核对桌面与窄屏布局。新增异步任务不涉及。

#### 风险与回滚

日记格式改版时，无法识别的内容以文本展示。回滚移除管理台入口、接口和对应构建产物即可，原日记可继续读取。
<!-- end-migrated-part: doc-f24e68fc0316c1 -->

<a id="doc-3b5de0b90aca6b"></a>

### 复核常驻角色的 README 来源

来源：`llm wiki/wxbot/raw/changes/2026-11-05-resident-xiaochao-readme.md:1`。

```yaml
type: change
title: 复核常驻角色的 README 来源
pages:
- modules/wiki
```
### 复核常驻角色的 README 来源

#### 目标与背景

补充 [raw/changes/2026-11-05-resident-xiaochao](resident.md#doc-2d4efb23ee9751) 的 README 来源核对。

#### 文件与代码位置

`README.md:819` 追加小潮的使用说明。`README.md:786` 的图谱维护章节经核对未移动，图谱工具仍沿用该入口。

#### 接口与字段

不涉及图谱接口和字段。

#### 数据库与迁移

不涉及数据库和迁移。

#### 前端消费点

不涉及前端消费。

#### 测试与异步任务

以 `wiki.py ingest` 和 `wiki.py lint` 核对来源。此条不涉及运行测试或异步任务。

#### 风险与回滚

此条登记 README 证据快照，后续修订沿用追加记录的回滚方式。
<!-- end-migrated-part: doc-3b5de0b90aca6b -->

<a id="doc-2d4efb23ee9751"></a>

### 小潮常驻角色与空闲刷抖音

来源：`llm wiki/wxbot/raw/changes/2026-11-05-resident-xiaochao.md:1`。

```yaml
type: change
title: 小潮常驻角色与空闲刷抖音
pages:
- symbols/resident-role
- modules/runtime
- modules/plugin
- modules/butler
- apis/butler-handle
- apis/butler-handle-stream
- apis/dashboard-knowledge
- apis/index-tts
- concepts/development-baseline
- concepts/model-error-contract
- symbols/butler-handle
- symbols/butler-result
- symbols/knowledge-auto
- symbols/knowledge-extract
- tables/kb-episodes
```
### 小潮常驻角色与空闲刷抖音

#### 目标与背景

小潮随本机 Butler 启停。服务空闲时短时浏览抖音推荐流，仅将本轮核对的播放记录写入本机日记。改前设计见 [impacts/2026-11-05-resident-xiaochao](resident.md#doc-6323d188bd37df)。

#### 文件与代码位置

`src/butler/config.py:22` 定义配置。`src/butler/server.py:425` 记录两个聊天入口的前台活动，`:513` 管理启停。`src/butler/runtime/resident.py:91` 管理调度和日记，`src/butler/runtime/resident_douyin.py:89` 通过可选 Playwright 控制专用 Edge。`src/butler/__main__.py:47` 提供显式登录，角色正文在 `plugins/butler-wechat/resident/xiao-chao.md:1`。

#### 接口与字段

TOML `[resident_role]` 新增 `enabled`、`idle_seconds`、`round_seconds`、`cooldown_seconds`、`daily_seconds`，默认依次为 `false`、300、180、1800、900。CLI 新增 `resident-login`。HTTP 请求与响应字段不涉及，已复核鉴权、流式响应和共享文件内其余接口的来源。`pyproject.toml` 新增可选依赖 `resident`。

#### 数据库与迁移

数据库和迁移不涉及。角色状态、登录恢复标记、Edge 资料及日记存放在 `data/resident/xiao-chao/`。运行前原子写入额度预留和下次时间，结束后按浏览器活动用时归还未使用的部分。跨进程单飞锁保护运行状态。

#### 前端消费点

不涉及管理台页面。使用者按 README 配置开关，通过本机日志、状态 JSON 和 Markdown 日记核对运行。

#### 测试与异步任务

离线测试覆盖同步／流式聊天前台信号、生命周期、并发聊天、冷却、每日额度、登录恢复和短日记。后台线程空闲时唤醒，收到聊天时在下一次浏览操作前让路。兼容纯文本后端最多整理一次，其他后端写事实版日记。

#### 风险与回滚

网页结构、登录和无窗口播放影响实际运行。只记录可核对的作品和播放进度，登录或验证交回使用者。停用开关并由用户重启 Butler 可回滚行为，浏览器资料和日记在本机保留。
<!-- end-migrated-part: doc-2d4efb23ee9751 -->

<a id="doc-b2141987114c61"></a>

### 修复小潮推荐流跳转到精选

来源：`llm wiki/wxbot/raw/changes/2026-11-06-resident-recommend-navigation.md:1`。

```yaml
type: change
title: 修复小潮推荐流跳转到精选
pages:
- symbols/resident-role
```
### 修复小潮推荐流跳转到精选

#### 目标与背景

旧入口 `/?recommend=1` 在可见 Edge 中跳转到 `/jingxuan`，此时没有可识别的推荐流播放器，轮次记录为 `no_playback`。尝试直接访问 `/recommend` 也出现同样的跳转。恢复从站内推荐入口寻找播放器。

#### 文件与代码位置

`src/butler/runtime/resident_douyin.py:11` 的 `FEED_URL` 带上 `from_nav=1`。`src/butler/runtime/resident_douyin.py:126` 的 `_follow_recommend_link` 限制来源、可访问名称、站内目标和停止条件。`src/butler/runtime/resident_douyin.py:144` 的 `_wait_for_access` 与 `src/butler/runtime/resident_douyin.py:165` 的 `watch` 在精选无作品时允许站内回退。

#### 接口与字段

HTTP API、配置字段和状态格式无变化。

#### 数据库与迁移

不涉及数据库和迁移。

#### 前端消费点

不涉及前端变更。日记仍只显示实际记录到播放的轮次。

#### 测试与异步任务

本地回归模拟精选跳转、站内回退与拦截站外链接。常驻角色、心跳及日记 API 共 38 个测试通过。导航沿用现有的前台活动、时限和冷却规则。

#### 风险与回滚

抖音页面结构变化可能影响链接和作品识别。新入口在真实已登录浏览器中的复测遇到自动审批超时。运行中的 Butler 需重新启动以加载代码。回滚仅涉及推荐 URL 和导航回退逻辑，无数据迁移。
<!-- end-migrated-part: doc-b2141987114c61 -->

<a id="doc-eb3bb4d27e3f68"></a>

### 小潮有窗口模式与同页验证恢复

来源：`llm wiki/wxbot/raw/changes/2026-11-06-resident-visible-edge.md:1`。

```yaml
type: change
title: 小潮有窗口模式与同页验证恢复
pages:
- symbols/resident-role
- concepts/development-baseline
- modules/wiki
```
### 小潮有窗口模式与同页验证恢复

#### 目标与背景

为 [symbols/resident-role](resident.md#doc-81303bd5af31f1) 增加有窗口浏览。复现表明无窗口推荐页可能在登录后要求安全验证，用户需要在同一浏览器处理。影响见 [impacts/2026-11-06-resident-visible-edge](resident.md#doc-6cee41da4b9fa7)。

#### 文件与代码位置

`src/butler/config.py:22` 校验新设置。`src/butler/runtime/resident_douyin.py:124` 等待页面和登录恢复，`:141` 在同一 Edge 会话内暂停及继续。`src/butler/runtime/resident.py:141` 判断模式、更新状态和计算额度。README 记载操作步骤。

#### 接口与字段

TOML 新增布尔值 `[resident_role].visible_browser`，缺省 `false`。无 HTTP 接口或 DTO 变化。`state.json` 保存 `visible_browser` 和临时状态 `verification_required`，旧记录缺省为无窗口。

#### 数据库与迁移

无数据库或迁移。旧的登录等待在窗口模式变化时允许按调度规则重新尝试。使用同一个已有的专用 Edge 登录资料目录。

#### 前端消费点

不涉及管理台页面。验证在活动实际使用的专用 Edge 中处理，服务日志提示当前操作。

#### 测试与异步任务

回归覆盖旧状态切换、等待额度、同一会话继续、前台聊天优先、停止和超时。等待保留后台线程和单飞锁，整轮累计最多 10 分钟，等待时间从活动额度排除。恢复前复核空闲与日界。

#### 风险与回滚

平台验证仍由用户处理。浏览器可见窗口可能获得焦点。设置 `visible_browser = false` 并由用户重启 Butler 可恢复无窗口模式，日记和账号资料保留。
<!-- end-migrated-part: doc-eb3bb4d27e3f68 -->
