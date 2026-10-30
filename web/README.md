# 管理台前端

本目录是管理台的 Vue 3 + Vite 实现，由 `src/dashboard/server.py` 挂在
`http://127.0.0.1:8788/app/`；根路径 `/` 会 302 到 `/app/`。

## 目录

```
web/
  index.html           Vite 入口（构建后由服务端在 /app/ 返回）
  vite.config.js       base=/app/，开发时把 /api 代理到 8788
  src/App.vue          导航壳：分组、标题、刷新、自动刷新、列表折叠、全局搜索
  src/router.js        扁平标签表：导航顺序、分组与 ?tab= 路由
  src/api.js           GET/POST 封装与时间格式化
  src/prefs.js         仅展示偏好的 localStorage 读写（白名单控制）
  src/flow.js          工作流流转文案、事件分组与队列诊断共用纯函数
  src/workflowState.js 工作流页跨标签页保留的快照、选中与概览状态
  src/contactState.js  联系人页共享状态与动作头请求封装
  src/configDraft.js   配置页草稿、保存状态与文件版本
  src/queueFocus.js    工作流 → 收发队列的一次性筛选传递
  src/styles/dashboard.css 基础布局与组件类
  src/styles/workflow.css  工作流页专用样式
  src/styles/theme.css     主题层：设计令牌、导航、控件与卡片皮肤
  src/views/           页面组件（六页全部在此）
  src/components/      结构化编辑器、联系人弹窗、工作流节点与流转详情
  scripts/smoke.mjs    jsdom 冒烟测试（只读，固定假数据）
  dist/                构建产物，随仓库发布
```

## 命令

```bash
cd web
npm install
npm run dev      # http://127.0.0.1:5173/app/?tab=telegram-relay ，/api 代理到 8788
npm run build    # 输出 dist/，重启不需要，刷新 /app/ 即可
npm run smoke    # 需先 build；用 jsdom 校验壳与全部页面能渲染
```

修改 `src/` 或样式后必须 `npm run build` 并提交 `dist/`，否则 `/app/` 仍是旧产物
（产物缺失时服务端返回构建提示页）。

## 维护约定

1. 新增页面：在 `src/views/` 新增组件，在 `src/App.vue` 的 `VIEWS` 注册，
   并在 `src/router.js` 的 `TABS` 里加上导航项。
2. 不改接口：服务端只读 GET、写操作要求动作头（如 `X-Wxbot-Relay-Action`）的约定保持原样。
3. 样式分层：`styles/dashboard.css`、`workflow.css` 是布局与组件基线，Vue 侧的视觉调整统一写在
   `styles/theme.css`，不把业务样式复制到组件里。
4. 改页面后补 `scripts/smoke.mjs` 的断言，保证没有浏览器也能回归。
5. 页头专属控件（如「显示已完成」、「队列状态」）用 `<Teleport to="#page-tools">` 渲染，
   不要改动 `App.vue` 的工具栏顺序。
6. 页内筛选统一读 `inject('logWebCtx').search[tab]`，与页头搜索框保持同一份状态。
7. 需要跨标签页保留的草稿或筛选放在模块级状态文件里（`configDraft.js`、`contactState.js`、
   `workflowState.js`），定时器与请求控制器留在视图内，卸载时立即停止。

六个页面全部在此实现：实时工作流、收发队列、联系人、定时任务、配置管理、Telegram 转发。
服务端不再提供第二个页面入口，所有导航均在同一份 `src/router.js` 内维护。
