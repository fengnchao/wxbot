# wxbot

基于 Windows UI Automation 的个人微信自动回复工具：
监听绑定联系人的消息，以及群聊中明确 @机器人的消息 → 本地智能体（Hermes Agent）或本地模型（Ollama）处理 → 自动回复。

> ⚠️ 非官方用法，有账号风险。建议用小号，只绑定少数好友，保持低频。

## 目录结构

```
wxbot/
├── config.example.toml     # 配置模板（复制为 config.toml）
├── requirements.txt
├── tools/
│   └── probe.py            # 控件树探测（默认脱敏），用来校准控件定位
└── wxbot/
    ├── main.py             # 主循环：轮询 → 识别新消息 → 处理 → 回复
    ├── config.py           # 读取配置
    ├── log.py
    ├── state.py            # 新消息检测（对比前后两次消息列表）
    ├── wechat/
    │   ├── locator.py      # 按配置条件查找控件
    │   └── chat_window.py  # 独立聊天窗口：读取消息、发送消息
    └── processor/
        ├── base.py         # 处理器接口 + Echo 调试处理器
        ├── openai_compat.py # Hermes Agent / OpenAI 兼容接口
        ├── ollama.py       # 本地模型（Ollama）
        └── router.py       # /命令 路由
```

## 使用步骤

在配置的 `[bot]` 中，`bound_users` 填联系人窗口标题，`bound_groups` 填群聊窗口标题，`mention_names` 填机器人在微信中的昵称（可多个）。群聊只有包含明确 `@昵称` 提及的文字消息会进入处理器，@昵称会从消息正文移除，回复发回对应群聊。联系人和群聊标题不要重复。

### 1. 安装

需要 Windows 10/11、Python 3.10+。

```bash
pip install -r requirements.txt
copy config.example.toml config.toml
```

处理端二选一：

- **Hermes Agent**：在 Hermes 的环境配置里开启 API Server（默认端口 8642），运行 `hermes gateway`，
  看到 `API server listening on http://127.0.0.1:8642` 即可。配置里 `backend = "hermes"`。
- **Ollama**：安装后拉取模型，例如 `ollama pull qwen2.5:7b`，配置里 `backend = "ollama"`。

> ⚠️ Hermes 带有终端、文件操作等工具。好友发来的消息会直接交给它，
> 务必为这个用途关闭或限制危险工具，避免别人通过聊天让它在你电脑上执行命令。

### 2. 校准控件（必做）

`config.toml` 里 `[wechat.*]` 的控件定位只是初始猜测，需要按你的微信版本校准：

1. 在微信里双击一个联系人，打开独立聊天窗口
2. `python tools/probe.py --list`，确认窗口标题和类名
3. `python tools/probe.py --window 联系人名 --depth 12`，查看控件树
4. 找到：消息列表（通常是 ListControl，子项是一条条消息）、输入框（通常是 EditControl）、
   消息条目里的头像（通常是 ButtonControl），把对应特征填进配置

探测默认脱敏，输出可以放心贴给别人分析。

### 3. 先用 echo 模式测试

`config.toml` 里设 `backend = "echo"`，运行：

```bash
python -m wxbot.main
```

让好友发一条消息，机器人应回复"收到：xxx"。确认收发都正常后再改回 `ollama`。

## 工作原理

- 每个绑定联系人或群聊对应一个独立聊天窗口，程序轮询读取窗口里的消息列表
- 群聊只处理其他成员发出且包含已配置 `@昵称` 的文字消息；未提及机器人的群消息会跳过
- 对比上一次的快照找出新消息；微信 4.x 不暴露头像控件，所以截取消息条目，按头像在左/右判断是对方还是自己发的
- 只处理对方的新消息，启动时已有的历史消息不会回复
- 发送时激活窗口、点击输入框、剪贴板粘贴、回车

## 注意

- 运行期间独立窗口要保持打开、完整显示在屏幕上（不能被其他窗口遮挡、不能最小化），电脑不能锁屏
- 发送时会抢占焦点和剪贴板，运行时尽量不要同时用这台电脑打字
- 微信更新后控件可能变化，重新用 probe.py 校准即可
