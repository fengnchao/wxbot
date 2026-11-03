---
type: change
title: IndexTTS 入队不再写入 P1 假音频路径
pages:
  - concepts/delivery-state
  - concepts/message-pipeline
  - concepts/model-error-contract
  - concepts/voice-asset-binding
  - modules/wxbot
  - symbols/model-worker
  - tables/queue-outbox
---
# IndexTTS 入队不再写入 P1 假音频路径

## 目标与背景

`tts_provider=indextts` 且联系人 mode=replace、有可用 `asset_id` 时，微信仍播放 P1 假音频。原因是模型线程和主动推送入队时无条件把 `policy.fixture_wav` 写入 `outbox.media_path`。`DeliveryPump._prepare_voice_audio` 见非空路径就 `load_wav_file`，不再调用 `build_tts_source` / `IndexTtsSource.prepare`。

修正：只有 `tts_provider=fixture` 写入假音频路径；其它在投递时合成的提供者把 `media_path` 留空。无可用绑定仍只回文字，不合成、不走 RALT。产品默认、管理台和运行中的服务都不改。

## 文件与代码位置

- `src/wxbot/voice/policy.py:115` `VoicePolicy.queued_media_path`：fixture 返回 `fixture_wav`，否则返回空字符串。
- `src/wxbot/voice/policy.py:126` `resolve_queued_media_path`：有该方法时调用它；旧替身对象仅在 provider 缺省或 fixture 时回退到 `fixture_wav`。
- `src/wxbot/queue_worker.py:166`：`voice_mode != off` 时用上述解析结果作为 `voice_media_path`。绑定门控仍走 `delivery_mode_for`（约 159 行）。
- `src/wxbot/delivery.py:74`：`DeliveryPump.enqueue` 的 `kind=voice` 同样不再无条件写 `fixture_wav`。
- `src/wxbot/delivery.py:183` `_prepare_voice_audio` 未改：空 `media_path` 继续 `source.prepare`，非空继续 `load_wav_file`。
- `tools/smoke_voice_enqueue_media.py`：离线断言入队路径与 prepare 是否被调用。

## 接口与字段

不涉及新接口。`outbox.media_path` 含义收紧：fixture 语音条仍是假 WAV 路径；indextts 语音条为空，正文仍留在 `text` 供合成和失败回退。`/send` 的 `voice: true` 字段不变。

## 数据库与迁移

不涉及。不新增列、不改 `queue_schema`。空路径使用已有 `media_path TEXT NOT NULL DEFAULT ''`。

## 前端消费点

不涉及。管理台不展示或编辑这条路径，页面与 `web/dist` 未改。

## 测试与异步任务

`PYTHONPATH=src python3 tools/smoke_voice_enqueue_media.py`：indextts 的 replace/coexist/outbound `media_path` 为空且 `prepare` 被调用；fixture 的 `media_path` 为 `p1-tone.wav` 且不调用 `prepare`；无绑定只入文字。`tools/smoke_voice002_tts.py` 仍通过。未做真实微信发送。无新异步任务。

## 风险与回滚

已入队、`media_path` 已写成假 WAV 的旧语音条仍会播 P1 音调；需要新回复或重新入队才走 IndexTTS。流式 typing 路径本来就不挂 `voice_mode`，本次未改。回滚：还原上述文件，或把 `tts_provider` 设回 `fixture`。
