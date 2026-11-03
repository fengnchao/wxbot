#!/usr/bin/env python3
"""IndexTTS worker：在仓外 IndexTTS 的 uv 环境中按正文合成，并重采样为 P1 合同 WAV。

由 wxbot IndexTtsSource 通过 `uv run --directory <index-tts> python <this>` 调用。
权重/参考音路径仅本机；禁止未授权克隆他人音色。
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path


def _to_contract_wav(src: Path, dest: Path, sample_rate: int) -> None:
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio

    audio, sr = sf.read(str(src), always_2d=True)
    # mono
    if audio.shape[1] > 1:
        audio = audio.mean(axis=1, keepdims=True)
    else:
        audio = audio[:, :1]
    tensor = torch.from_numpy(audio.T.astype("float32"))  # (1, n)
    if int(sr) != int(sample_rate):
        tensor = torchaudio.functional.resample(tensor, int(sr), int(sample_rate))
    pcm = tensor.squeeze(0).detach().cpu().numpy()
    pcm = np.clip(pcm, -1.0, 1.0)
    pcm_i16 = (pcm * 32767.0).astype("<i2")
    # soundfile writes PCM_16 WAV (RIFF)
    sf.write(str(dest), pcm_i16, int(sample_rate), subtype="PCM_16")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="wxbot IndexTTS contract WAV worker")
    parser.add_argument("--cfg-path", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--prompt-wav", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--lang", default="ZH")
    parser.add_argument("--sample-rate", type=int, default=16000, choices=(16000, 48000))
    parser.add_argument("--use-cuda", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--use-bf16", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)

    prompt = Path(args.prompt_wav)
    if not prompt.is_file():
        print(f"prompt wav missing: {prompt}", file=sys.stderr)
        return 2
    text = str(args.text or "").strip()
    if not text:
        print("empty text", file=sys.stderr)
        return 2

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw_out = out.with_suffix(".raw.wav")

    try:
        # Prefer IndexTTS-2.5 API; fall back to IndexTTS-2.
        tts = None
        device = None if args.use_cuda else "cpu"
        try:
            from indextts.infer_v2_5 import IndexTTS2 as IndexTTS25

            tts = IndexTTS25(
                cfg_path=args.cfg_path,
                model_dir=args.model_dir,
                use_bf16=bool(args.use_bf16) and bool(args.use_cuda),
                device=device,
                use_cuda_kernel=False,
                use_deepspeed=False,
            )
            use_v25 = True
        except Exception:
            from indextts.infer_v2 import IndexTTS2

            kwargs = dict(
                cfg_path=args.cfg_path,
                model_dir=args.model_dir,
                use_fp16=bool(args.use_bf16) and bool(args.use_cuda),
                use_cuda_kernel=False,
                use_deepspeed=False,
            )
            # IndexTTS2 may or may not accept device=
            try:
                tts = IndexTTS2(**kwargs, device=device) if device else IndexTTS2(**kwargs)
            except TypeError:
                tts = IndexTTS2(**kwargs)
            use_v25 = False

        if use_v25:
            tts.infer(
                spk_audio_prompt=str(prompt),
                text=text,
                lang=str(args.lang or "ZH"),
                output_path=str(raw_out),
                verbose=False,
            )
        else:
            tts.infer(
                spk_audio_prompt=str(prompt),
                text=text,
                output_path=str(raw_out),
                verbose=False,
            )

        if not raw_out.is_file():
            print("infer produced no file", file=sys.stderr)
            return 3
        _to_contract_wav(raw_out, out, int(args.sample_rate))
        try:
            raw_out.unlink(missing_ok=True)
        except OSError:
            pass
        if not out.is_file():
            print("contract wav missing after resample", file=sys.stderr)
            return 4
        return 0
    except Exception as exc:  # noqa: BLE001 - surface full reason to parent
        traceback.print_exc()
        print(f"indextts_worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
