# IndexTTS 安装与接入（FEAT-VOICE-002 · 仓外）

本说明描述沙盒机仓外安装 IndexTTS、权重获取/校验、卸载，以及 wxbot 配置键。
**安装物、权重、参考音一律不进 git。**

## 禁止未授权克隆

- 参考音必须是**你自有或已获授权**的音色素材。
- **禁止**未授权克隆他人音色用于生产或外发。
- IndexTTS 官方 `examples/` 仅可用于本机工程冒烟（合成+合同校验），不得当作生产音色资产。
- 管理台音色资产绑定属 FEAT-VOICE-003，本单不做 UI。

## 本机路径（建议）

| 用途 | 路径 |
|---|---|
| IndexTTS 源码+uv 环境 | `D:\work\tools\index-tts\` |
| 权重（IndexTTS-2.5） | `D:\work\tools\index-tts\checkpoints\` |
| 授权参考音（自备） | `D:\work\tools\index-tts\refs\`（自建；不进 git） |
| 合成举证输出（可选） | `D:\work\tools\index-tts\proof\`（自建；不进 git） |

仓库内 worker：`tools/indextts_worker.py`（经 `uv run --directory <repo_dir>` 调用仓外环境）。

## 安装步骤

1. 需要：Windows、NVIDIA GPU（本沙盒 RTX 4070）、驱动、`uv`、`git`。
2. 克隆（仓外）：

```powershell
New-Item -ItemType Directory -Force D:\work\tools | Out-Null
Set-Location D:\work\tools
git clone https://github.com/index-tts/index-tts.git index-tts
Set-Location .\index-tts
git rev-parse HEAD   # 本沙盒钉扎: d9e41aac89fd00b3d71497fddb287b7f24613712
```

3. 依赖（隔离环境，勿装进 wxbot `.venv`）：

```powershell
# Windows 建议不要 --all-extras（DeepSpeed 难装）
uv sync --extra webui
# 或国内镜像：
# $env:UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple"
# uv sync --extra webui
```

4. 权重（任选其一）：

```powershell
uv tool install "huggingface-hub"
hf download IndexTeam/IndexTTS-2.5 --local-dir=checkpoints
# 或 ModelScope：
# uv tool install modelscope-hub
# modelscope download --model IndexTeam/IndexTTS-2.5 --local_dir checkpoints
```

5. GPU 自检：

```powershell
uv run tools/gpu_check.py
nvidia-smi
```

6. License：阅读仓内 `LICENSE` / `DISCLAIMER`（bilibili Model Use License）。大客户条款见协议 2.2。

## 卸载 / 回滚

1. wxbot 配置把 `voice.tts_provider` 改回 `"fixture"`（或 `enabled=false`）。
2. 删除仓外目录：`Remove-Item -Recurse -Force D:\work\tools\index-tts`
3. 如用 huggingface 缓存，可另清 `%USERPROFILE%\.cache\huggingface`（按需）。
4. 不改微信选麦 / 虚拟麦；那些属 P1 文档 `tools/voice-ptt-ops.md`。

## wxbot 配置示例

```toml
[voice]
enabled = true
tts_provider = "indextts"   # 排障可改回 "fixture"
fixture_wav = "tools/voice-fixtures/p1-tone.wav"
playback_device = "CABLE Input"
hold_padding_seconds = 0.3
min_seconds = 0.4
max_seconds = 60

[voice.indextts]
repo_dir = "D:/work/tools/index-tts"
model_dir = "D:/work/tools/index-tts/checkpoints"
cfg_path = "D:/work/tools/index-tts/checkpoints/config.yaml"
uv_bin = "uv"
timeout_seconds = 180
use_cuda = true
use_bf16 = true
sample_rate = 16000
default_ref_wav = ""          # 可选全局参考音；生产请用授权素材
default_lang = "ZH"
worker_script = "tools/indextts_worker.py"

[voice.contacts]
"示例联系人" = "replace"

# 按联系人参考音；asset_id 预留 003，本单不做管理台
[voice.contact_refs."示例联系人"]
ref_wav = "D:/work/tools/index-tts/refs/example-authorized.wav"
asset_id = ""
lang = "ZH"
```

## 行为真值（相对 P1）

| 条件 | 行为 |
|---|---|
| `tts_provider=fixture` | 忽略正文，播假音频（排障） |
| `indextts` + 有参考音 | 按**正文**合成合同 WAV → 既有投递 |
| `indextts` + 无参考音/无绑定 | **不合成、不按 RALT** → 文字回退 |
| OOM/超时/坏参考音/非合同/进程失败 | ValueError → 文字回退；遵守 replace/coexist |

## P1 WAV 合同

RIFF PCM mono 16-bit；16k 或 48k；默认 0.4s～60s。非法 → `ValueError`，调用方不得按 RALT。

## 参考音占位

若尚无授权参考音：在 `D:\work\tools\index-tts\refs\README.txt` 写明「放置自有授权 wav；禁止未授权克隆」。自动化测无参考音回退路径即可。

