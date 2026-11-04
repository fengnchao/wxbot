---
type: change
title: 音色资产页布局与状态打磨
pages:
- modules/web
- apis/dashboard-voice-assets
---
# 音色资产页布局与状态打磨

## 目标与背景

用户指定运行中的 `/app/?tab=voice-assets`。核对页面静态产物与源码后确认运行树为 `D:/work/code/wxbot-dev`，分支 `codex/grok-setup`，基线 `1e75ab4f2386709d53d26fbab0a9fd46b5b43323`，改前工作树干净。入口聊天目录是另一个较早的工作树，未把两个版本拼接。项目授权默认 Hallmark polish，保留既有深色系统与说明/上传/清单顺序。

根因是共享 `main` 双栏网格和窄屏 `body.list-open main` 把只有一个 section 的音色页压入侧栏轨道，专用样式又引用未定义的颜色令牌。共享 header 的样式也污染页内说明区。

## 文件与代码位置

- `web/src/views/VoiceAssetsView.vue:229`：原生文件/名称输入关联标签，读取状态、空态、失败态、按钮忙碌反馈及窄屏字段标签。
- `web/src/views/VoiceAssetsView.vue:45`：资产/绑定都成功读取才更新共享刷新时间。
- `web/src/styles/voice-assets.css:7`：限定当前页的一栏布局、共享 header 重置、现有主题令牌、44px 控件命中区、可见焦点、响应式清单和 reduced-motion。
- `web/dist/`：匹配上述源码的 Vite 产物。
- `llm wiki/wxbot/modules/web.md`、`apis/dashboard-voice-assets.md`、`coverage.md`：补齐页面布局/状态与既有字段血缘。原页已登记 App.vue/router.js/main.js，无新注册项。

## 接口与字段

不涉及 API/DTO 增删。列表仍读取 `/api/voice-assets`、`/api/voice-bindings`；资产字段来自 VoiceAdmin.list_assets / VoiceAsset.as_dict，绑定列由 contact_refs 中的 asset_id 反查。保留 register/rename/delete 请求体、预览路径、请求头、删除确认与处理器。仅成功读取后使用已有 markRefreshed 回调。

说明文案从“注册参考音（zero-shot），供会话绑定后合成；试听播放已注册参考 WAV，不触发 IndexTTS。”改为“添加参考音后，可在联系人设置中绑定会话。试听仅播放参考 WAV，不进行语音合成。”；限制从“上限 X MiB · 格式 WAV”改为“WAV 格式 / 最大 X MiB”。“上传一段本人授权的参考 WAV 后即可绑定到会话。”原文保留。

## 数据库与迁移

不涉及数据库、表、迁移、配置格式或音色存储格式。本轮无真实音色注册、删除、绑定或微信发送。

## 前端消费点

仅 VoiceAssetsView 与专用 CSS；App.vue 页面注册、router.js 导航、ContactDialog 绑定消费均不变。CSS 通过 `.voice-assets` 限定，未改共享 theme.css 或其它页面。

## 测试与异步任务

- `npm.cmd --prefix web run build`、`npm.cmd --prefix web run smoke`。
- 临时浏览器回归：四状态（加载/空/失败/有数据）× 六宽度（320/375/768/1280/1440/1920）× 两侧栏偏好，共 48 项；检查清单宽度、横向溢出、控件裁剪、错误/加载不误报空态、读取成功时间及键盘焦点。全部 API 在浏览器内拦截为假响应，禁止 POST；没有真实业务写入。脚本和截图为本次会话临时产物，不作为跨安装证据。
- Hallmark sloplint 针对两个修改源文件以 app scope 检查，并用真实 `/app/?tab=voice-assets` 渲染。页内已知焦点/边框 FAIL 修复；共享壳原有 10px 导航文字（75）与“消息监控”标题 4.29:1 对比度（40）仍属界外问题，未扩展修改。Vue 动态短按钮文案的 49 警告按实际 nowrap/浏览器布局复核为误报。
- 没有新增异步任务或定时器。读取仍并行、保留旧请求序号防护。

## 风险与回滚

低风险纯前端变更；表格窄屏仅改变呈现，DOM 保留表头与 scope。回滚这两个源文件并恢复匹配 dist 即可，不需迁移或服务重启。未验证真实音频播放/音色写入，原处理逻辑保留。

图谱 lint 原有 `pending-change: raw/changes/2026-11-03-feat-voice-002-indextts` 尚未入库，未擅自替它完成语义审核。机械 lint 不证明所有语义正确。
