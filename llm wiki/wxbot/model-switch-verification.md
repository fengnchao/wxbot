# 统一模型链路验证

日期：2026-10-31。仅临时配置、临时业务库、假模型和回环测试 HTTP；未调用真实模型、发送微信或重启业务进程。

## 专项检查

- 安装与旧 direct 配置显式迁移：36 passed；原始配置保留本机备份，Key 不留在 wxbot 的 model 中。
- 后端协议/工具：原生 OpenAI/Responses 工具使用真实 ToolService 和临时库验证；身份伪造、越权、心跳只读、失败后的副作用与禁止重放均有回归。
- 请求代际切换：12 passed，包含在途固定代际、关闭时机、失败候选、不变的服务/存储参数，以及本地运行方式切换 Hermes 的 URL 兼容。
- 配置保存与页面元信息：53 项专项通过；旧 Hermes 首次转入本地模式需重启，普通模型字段热生效，home/plugin 等字段仍需重启。
- SSE 传输：25 项通过；只有提交前的 model_configuration 且无模型事件时保留安全重试标记。
- 独立代码审查发现的旧 Hermes 保存提示和 SSE 安全重试问题均已修复并复核。
## 前端

执行 `npm.cmd --prefix web run build`、`npm.cmd --prefix web run smoke`，均通过；dist 随源码更新。smoke 包含草稿 openai→cursor→openai、适用字段变化和草稿保留。

Hallmark 针对 ConfigurationView.vue，以独立假数据预览 `/app/?tab=configuration` 渲染 5 种视口：0 FAIL，2 REFLEX，2 WARN。现有两行分类导航高度与全局 10px 分组标题保留并记录豁免；剩余 WARN 是现有壳层 4.29:1 对比度和字体字重数量。新增字段边框使用已有 --fg3 token，分类控件有键盘/焦点状态。详见项目 `.hallmark/model-configuration-review.txt`。未扩展为全站重设计。

## 接入方式下拉（2026-10-31 补充）

上一轮把运行时打通，页面仍只列 8 种协议，DeepSeek 和自定义 API 只在 CLI 向导里能选。本轮把页面收敛成单一「接入方式」，由服务端推导 `[agent].provider` 与 `[model].backend`。

- 保存展开实测 5 种：deepseek → `agent=openai / model.provider=deepseek / model.backend=openai`；custom+responses → `agent=responses`；codex → 删除 `[model].backend`；hermes、ollama 各自写入对应协议。
- 运行时回退：`model.provider=deepseek` 且 url/model 留空 → `https://api.deepseek.com/v1/chat/completions` + `deepseek-chat`；openai 同样回退官方地址，不会串到别家。
- 回归：`pytest tests/dashboard tests/butler tests/unit/codex` 736 passed / 0 failed。
- 前端：`npm.cmd --prefix web run build` 与 `npm.cmd --prefix web run smoke` 通过；smoke 改为按 `deepseek` 选项定位接入方式下拉，并断言空值回退到当前接入方式、openai/cursor 字段切换与草稿保留。
- Hallmark `sloplint.mjs --scope app --render` 在隔离假数据预览上得分 0 FAIL、2 REFLEX、1 WARN；REFLEX 39b/75 与 WARN 40 均为既有壳层条目，沿用上次豁免。`ConfigField.vue` 单文件扫描报的 26a 是看不到全局样式所致：焦点环由 `web/src/styles/theme.css:125` 与 `web/src/styles/dashboard.css:231` 统一提供。

## 全量回归

最终全量测试结果在执行完毕后追加；不得把专项通过误报为整个工作树通过。之前全量运行已修正本次架构变更导致的旧 direct 假设和测试服务绑定隔离问题；与本次无关的队列生命周期旧用例另列。

## 交付界限

真实 Codex/Hermes/Cursor/API 的可用性与权限取决于本机登录、Key 和远端配置，离线测试不证明真实连接。首次加载本次代码需要使用者自己重启 Butler、管理台和 wxbot；此后按页面提示切换。图谱和修改记录按本次实际来源快照入库。
