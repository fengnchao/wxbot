# wxbot — 微信机器人（单项目 · 双模块）

一个仓库里包含微信机器人的两个协作模块，**共用同一个虚拟环境 `.venv`，依赖只需安装一次**。

| 模块 | 目录 | 角色 | 通俗比喻 | 第三方依赖 |
|---|---|---|---|---|
| **管家 butler** | `butler/` | 决策编排层：收消息 → 投递大模型 → 判断是否调 skill → 出最终文案 | 大脑 | 无（纯标准库） |
| **UI 自动化 wxbot** | `wxbot/` | 收发层：监控微信窗口、读消息、模拟键盘发送回复 | 手和眼 | uiautomation / requests / pillow |

## 架构

```
微信客户端
   │  ①对方发消息
   ▼
wxbot（wxbot/ 包，UI 自动化）
   │  ②HTTP POST → 管家
   ▼
butler 管家（butler/ 包，决策层，端口 8770）
   │  ③投递大模型
   ▼
Hermes 网关（大模型 + skill 运行时，端口 8642）
   │  ④AI 回复
   ▼
butler 管家 →（加工/判断 skill）→ wxbot →（自动打字）→ 微信客户端
```

> wxbot 也可以**绕过管家**直连大模型：在 `config.wxbot.toml` 里把 `backend` 设为
> `hermes` / `openai` / `ollama` / `echo`（`echo` 用于调试，原样返回）。

## 目录结构

```
wxbot/                          项目根（唯一 pyproject.toml / requirements.txt / .venv）
├── butler/        ★管家模块★   决策编排层（server.py 为 HTTP 入口）
│   └── README.md               管家详细文档（架构、接口契约、行动协议）
├── wxbot/         ★UI 模块★    微信自动化（main.py 为主循环入口）
│   ├── main.py                 轮询→发现新消息→处理→回复
│   ├── wechat/                 窗口定位、读消息、发消息
│   └── processor/              后端路由：hermes/openai/ollama/echo
├── heartbeat/                  看门狗：进程挂了自动重启
├── log/                        日志看板服务（8788 端口）
├── scripts/                    运维脚本（投递/提醒/栈启停）
├── tools/                      probe.py 控件探测 + debug_read.py 调试
├── tests/                      管家主流程测试（pytest，全离线）
├── config.butler.toml          管家配置（含密钥，不进版本库）
├── config.butler.example.toml  管家配置模板
├── config.wxbot.toml           UI 自动化配置（不进版本库）
├── config.wxbot.example.toml   UI 自动化配置模板
├── requirements.txt            ★统一依赖清单★
├── pyproject.toml              项目声明 + pytest 配置
├── README.wxbot.md             UI 自动化模块详细文档（校准控件等）
└── .venv/                      唯一虚拟环境（Python 3.14）
```

## 快速开始

### 1. 安装依赖（只做一次，两个模块共用）

要求 **Python 3.14+**。本项目用 [uv](https://github.com/astral-sh/uv) 管理环境：

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt
```

（若用普通 pip：`.\.venv\Scripts\python -m pip install -r requirements.txt`）

### 2. 准备配置

```powershell
copy config.butler.example.toml config.butler.toml   # 填 server.token / hermes.api_key
copy config.wxbot.example.toml  config.wxbot.toml     # 填 bound_users；要监听群聊时再填 bound_groups / mention_names
```

> 两个配置文件格式不同、用途不同，**不要合并**。含密钥，已在 `.gitignore` 中忽略。

### 3. 启动（开两个终端，因为它们是独立进程）

```powershell
# 终端 1：管家 butler（决策层）
.\.venv\Scripts\python -m butler.server --config config.butler.toml
.\.venv\Scripts\python -m butler.server --status        # 仅探活后退出

# 终端 2：wxbot UI 自动化（先在微信里双击联系人打开独立聊天窗口）
.\.venv\Scripts\python -m wxbot.main
```

群聊监听：在 `[bot]` 配置 `bound_groups = ["群聊窗口标题"]` 和 `mention_names = ["机器人昵称"]`，并在微信中打开对应群聊独立窗口。只有明确包含 `@机器人昵称` 提及的群消息会进入同一处理器流程并在群内回复。

> 首次使用 UI 自动化，建议先把 `config.wxbot.toml` 里 `backend = "echo"` 测试收发，
> 并用 `python tools\probe.py` 校准微信控件。详见 `README.wxbot.md`。

### 4. 跑测试

```powershell
.\.venv\Scripts\python -m pytest
```

## 详细文档

- 管家（决策层）架构与接口：[`butler/README.md`](butler/README.md)
- UI 自动化安装、控件校准、工作原理：[`README.wxbot.md`](README.wxbot.md)

## 注意

- ⚠️ 微信自动化为**非官方用法，有账号风险**：建议用小号、只绑少数好友、保持低频。
- UI 自动化运行期间，独立聊天窗口须**保持打开、不被遮挡、不最小化**，电脑不能锁屏。
- 配置中若含硬编码绝对路径（如 `D:/ai/hermes`），需按本机实际路径修改。
