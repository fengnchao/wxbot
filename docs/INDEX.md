# 文档入口

仓库根 [`README.md`](../README.md) 只讲「是什么、怎么装、怎么起」。具体主题从这里进。

## 上手

| 文档 | 内容 |
|---|---|
| [`../README.md`](../README.md) | 项目定位、安装一行、三个进程的启动方式、目录地图 |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 进程与链路、职责边界、目录地图、关键路径、协议要点、配置 |
| [`CODEX_INSTALL.md`](CODEX_INSTALL.md) | 完整安装、故障排查、升级现有安装、旧部署切换与回退 |
| [`../src/butler/README.md`](../src/butler/README.md) | 原 Butler/Hermes 接口说明，仅供旧后端兼容参考 |

## 协议与业务

| 文档 | 内容 |
|---|---|
| [`MESSAGE_API.md`](MESSAGE_API.md) | butler 消息接口的请求/响应形状与鉴权 |
| [`CODEX_PROTOCOL.md`](CODEX_PROTOCOL.md) | 插件与业务工具协议、行动标记、skill 白名单 |
| [`USER_MEMORY.md`](USER_MEMORY.md) | 固定用户身份、长期记忆、群上下文与真正 @ |
| [`NEWS_DELIVERY.md`](NEWS_DELIVERY.md) | 综合新闻订阅、每日投递与状态记录 |
| [`WXBOT_UI.md`](WXBOT_UI.md) | 微信 UI 自动化：主窗口监听、队列、发送 |

## Telegram

| 文档 | 内容 |
|---|---|
| [`TELEGRAM_NEWS.md`](TELEGRAM_NEWS.md) | 联合早报文字转发到新闻分组 |
| [`TELEGRAM_BOT.md`](TELEGRAM_BOT.md) | Bot API 收件进 Butler |
| [`TELEGRAM_RELAY_SKILL.md`](TELEGRAM_RELAY_SKILL.md) | 频道窗口转发 Skill、图文投递与人工核对 |

## 管理台

| 文档 | 内容 |
|---|---|
| [`LOG_DASHBOARD.md`](LOG_DASHBOARD.md) | 当前页面说明：导航、实时工作流、收发队列、配置管理、接口兼容 |
| [`DASHBOARD.md`](DASHBOARD.md) | 管理台历史实现记录与数据来源（按日期留存，部分章节已过时） |
| [`../web/README.md`](../web/README.md) | 前端目录结构、构建与维护约定 |

## 验证记录

| 文档 | 内容 |
|---|---|
| [`CODEX_VERIFICATION.md`](CODEX_VERIFICATION.md) | Codex 接入的实现与验证、手动切换清单 |
| [`GROUP_NICKNAME_VERIFICATION.md`](GROUP_NICKNAME_VERIFICATION.md) | 群昵称、成员身份与会话隔离的核对方法 |
| [`WECHAT_MENTION_VERIFICATION.md`](WECHAT_MENTION_VERIFICATION.md) | 群 @ 提及判定与回复链路的核对方法 |

## 存档

[`superpowers/`](superpowers) 是按日期留存的实现计划、设计稿与验证记录，写于对应功能落地时，
不随后续重构更新；结论以当前代码与本文档目录中的正式文档为准。

## 维护约定

- 新增功能文档放 `docs/` 根目录，并在本页对应分组加一行。
- 路径描述必须与仓库实际布局一致：包在 `src/` 下、前端源码在 `web/`、测试分域在 `tests/`。
- 仓库级的约定与踩坑记录写在根 [`PROJECT_MEMORY.md`](../PROJECT_MEMORY.md)，不写进本页。
