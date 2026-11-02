---
type: change
title: 管理台全局搜索增加清空按钮
pages:
- modules/web
---
# 管理台全局搜索增加清空按钮

## 目标与背景

管理台顶栏 `#view-search` 按页保存关键词，但有内容时缺少显式清空入口，只能手工删字。WEB-001 要求在搜索框旁增加「清空」，只清当前页搜索词并回焦，配置页/转发页等原本隐藏全局搜索的页面也不显示该按钮。

## 文件与代码位置

- `web/src/App.vue`：新增 `searchValue` / `clearSearch`；工具栏用 `.global-search` 包裹 `#view-search` 与 `#view-search-clear`（`aria-label="清空搜索"`），随 `searchHidden` 与是否有内容显示。
- `web/src/styles/theme.css`：补充 `.global-search` 行内布局，窄屏不抢占其他工具栏控件。
- `web/scripts/smoke.mjs`：补定时任务/工作流/对话记录的清空交互与跨页保留断言；配置页断言无全局清空按钮。
- `web/dist/`：随本次 `npm run build` 更新。

## 接口与字段

不涉及后端接口或写请求。搜索仍只写 `provide('logWebCtx').search` 的按 tab 键值。

## 数据库与迁移

不涉及。

## 前端消费点

各业务页继续通过注入的 `search[activeTab]` 做原有筛选/加载；清空只把当前 tab 的值置空，不改其他筛选控件状态。

## 测试与异步任务

`npm.cmd --prefix web run build` 与 `npm.cmd --prefix web run smoke`（假数据）。Hallmark 对改动源码做静态/scope 检查。

## 风险与回滚

风险低：仅壳层工具栏交互。回滚删除本记录对应提交中的 App.vue / theme.css / smoke / dist 改动即可。
