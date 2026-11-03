---
title: FEAT-VOICE-002 IndexTTS 可插 TTS 源
date: 2026-11-03
---

## 目标 / 背景

在 P1 可插 TTS 合同上接入 IndexTTS：按正文合成 RIFF PCM mono 16-bit（16k/48k）WAV，失败或不具备参考音时不按 RALT、回退文字。仓外安装权重；不做 003 UI；不改开会话/虚拟麦/RALT。

## 文件 / 位置

- `src/wxbot/voice/policy.py`：`tts_provider`、`IndexTtsSettings`、`contact_refs`（含预留 `asset_id`）
- `src/wxbot/voice/tts.py`：`IndexTtsSource`、`build_tts_source`；`FixtureTtsSource.prepare` 保留
- `src/wxbot/voice/__init__.py`：导出
- `src/wxbot/inbox.py` / `src/wxbot/delivery.py`：经 factory 选源；`prepare(..., contact=)`
- `tools/indextts_worker.py`：uv 环境内合成+重采样到合同
- `tools/indextts-ops.md`：安装/校验/卸载；禁止未授权克隆
- `tools/smoke_voice002_tts.py`：本地冒烟

## API / DTO

- 配置新增 `voice.tts_provider`、`voice.indextts.*`、`voice.contact_refs.*`
- 出站 wire / RALT / 虚拟麦：**无变更**
- TTS `prepare(text, *, data=None, contact="")` 可选 `contact`

## DB / 迁移

不涉及。

## 前端消费

不涉及（AC-10 仍配置文件；003 另单）。

## 测试 / 异步

- `tools/smoke_voice002_tts.py`：fixture、无参考音回退、bytes 注入、policy
- 真机微信发测：另授；P1 人工验仍挂时 AC-09 标阻塞

## 风险 / 回滚

- IndexTTS 权重与 CUDA 仅本机；OOM/超时回退文字
- 回滚：`tts_provider=fixture` 或还原本分支；仓外目录可删

## 不适用

管理台音色资产、ASR、云 TTS、推 main/合并。
