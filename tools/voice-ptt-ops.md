# 虚拟麦 + Right Alt 语音条操作说明（FEAT-VOICE-001 P1）

## 目标路径

打开目标会话（复用现网发文字校准路径）→ 微信麦克风选中虚拟麦录音端 → 播放假音频到虚拟麦播放端 → **长按 Right Alt** → 松手后聊天出现语音条。

本单**不**依赖默认 UIA 可读会话列表/消息气泡来验条；自动化以 PTT 完成作为发送确认，**人工确认**聊天里出现语音条。

## 本机组件（仓外）

详见 `D:\work\tools\virtual-mic\INSTALL-NOTES-zh.md`（安装物不进 git）。

| 角色 | 设备名 |
|---|---|
| 播放端（向环回灌音） | CABLE Input（VB-Audio Virtual Cable） |
| 微信麦克风（采集） | CABLE Output（VB-Audio Virtual Cable） |

## 微信选麦

1. 微信 → 设置 → 设备 / 音频
2. 麦克风选择 **CABLE Output**
3. 不要选本机真实麦克风，避免环境噪声

## 配置开关（AC-10：仅配置文件，无管理台 UI）

在 `config.wxbot.toml`：

```toml
[voice]
enabled = true
fixture_wav = "tools/voice-fixtures/p1-tone.wav"
playback_device = "CABLE Input"
hold_padding_seconds = 0.3
min_seconds = 0.4
max_seconds = 60

# 白名单：仅列出的联系人/群会话名生效；未列出 = off
[voice.contacts]
"示例联系人" = "replace"   # off | replace | coexist
"示例群" = "coexist"
```

真值表：

| mode | 成功 | 失败 |
|---|---|---|
| off | 现网纯文字 | 同现网 |
| replace | 只发语音条，不另发正文 | 回退发一次文字 |
| coexist | 先文字分句，再语音条 | 文字不因语音失败重发 |

## Right Alt

- 键码：`uiautomation.SpecialKeyNames['RALT'] == 165`
- 动作：`PressKey` 保持 → 音频播放 → `ReleaseKey`
- **不得**擅自改成其它快捷键

## 主动推送（可选）

`POST /send` 增加可选字段 `"voice": true`（需同时有 `text` 作失败回退）。旧客户端不传该字段则行为不变。

Butler `push_to_wxbot(..., voice=True)` 透传。

## 卸载虚拟麦

见仓外 `INSTALL-NOTES-zh.md`：管理员运行 VB-Cable Setup 卸载并重启，微信麦改回原设备。

## TTS 输入合同（P1）

- WAV / PCM / mono / 16-bit / 16000 或 48000 Hz
- 时长默认 0.4–60 秒
- 文件路径或 bytes；同步 `prepare`
- 非法输入：不按 RALT，走文字回退
- P2 IndexTTS 另单接入同一合同

## P2 IndexTTS

见 `tools/indextts-ops.md`。配置 `voice.tts_provider = "indextts"`；排障可改回 `fixture`。本单不改开会话/RALT/虚拟麦路径。

