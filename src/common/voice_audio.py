"""Bounded PCM conversion and segmentation, without Windows UI dependencies."""
from array import array
from io import BytesIO
import re
import sys
import wave

MAX_AUDIO_BYTES = 64 * 1024 * 1024
RATE = 16000


def split_text(text, limit=160):
    if not isinstance(text, str) or not text.strip() or len(text) > 6000:
        raise ValueError('朗读文字须为 1-6000 字')
    pieces, current = [], ''
    for sentence in re.findall(r'[^。！？!?；;\n]+[。！？!?；;\n]*|[。！？!?；;\n]+', text):
        while sentence:
            available = limit - len(current)
            if len(sentence) <= available:
                current += sentence
                break
            if current:
                pieces.append(current)
                current = ''
            if len(sentence) > limit:
                # Prefer a clause/word boundary, but bound an unbroken sentence too.
                cut = max(sentence.rfind(c, 0, limit + 1) + 1 for c in ('，', ',', ' ', '、', '：', ':'))
                cut = cut if cut >= limit // 2 else limit
                pieces.append(sentence[:cut])
                sentence = sentence[cut:]
    if current:
        pieces.append(current)
    return pieces


def _pcm(data):
    if not isinstance(data, bytes) or not 44 <= len(data) <= MAX_AUDIO_BYTES:
        raise ValueError('音频大小无效')
    try:
        with wave.open(BytesIO(data)) as stream:
            channels, width, rate, frames = stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()
            if channels not in (1, 2) or width != 2 or not 8000 <= rate <= 192000 or frames / rate > 600:
                raise ValueError('仅支持 10 分钟内的单/双声道 PCM16 WAV')
            raw = stream.readframes(frames)
            if len(raw) != frames * channels * width or not frames:
                raise ValueError('WAV 音频不完整')
    except (wave.Error, EOFError) as exc:
        raise ValueError('无效 PCM WAV') from exc
    samples = array('h', raw)
    if sys.byteorder != 'little':
        samples.byteswap()
    if channels == 2:
        samples = array('h', ((samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)))
    if rate != RATE:
        source = samples
        count = round(len(source) * RATE / rate)
        samples = array('h')
        for i in range(count):
            offset, fraction = divmod(i * rate, RATE)
            left = source[min(offset, len(source) - 1)]
            right = source[min(offset + 1, len(source) - 1)]
            samples.append(round(left + (right - left) * fraction / RATE))
    return samples


def _wav(samples):
    out = BytesIO()
    if sys.byteorder != 'little':
        samples = array('h', samples)
        samples.byteswap()
    with wave.open(out, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(samples.tobytes())
    return out.getvalue()


def prepare_voice_parts(data, max_seconds=55):
    samples = _pcm(data)
    if len(samples) < int(.4 * RATE):
        raise ValueError('语音不足 0.4 秒')
    limit = int(max_seconds * RATE)
    if not RATE <= limit <= 55 * RATE:
        raise ValueError('无效语音时长上限')
    parts, start = [], 0
    while len(samples) - start > limit:
        end = start + limit
        # Choose the quietest 20ms window near the limit; keep every PCM frame.
        lower = max(start + RATE, end - RATE)
        upper = min(end, len(samples) - int(.4 * RATE))
        cut = min(range(lower, upper + 1, 320),
                  key=lambda p: sum(abs(v) for v in samples[max(start, p - 160):p + 160]))
        parts.append(_wav(samples[start:cut]))
        start = cut
    parts.append(_wav(samples[start:]))
    return parts


def validate_voice_wav(data):
    """Wire/cache accepts the canonical format only, never arbitrary media."""
    if not isinstance(data, bytes) or not 44 <= len(data) <= 55 * RATE * 2 + 4096:
        raise ValueError('语音大小无效')
    try:
        with wave.open(BytesIO(data)) as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, RATE):
                raise ValueError('语音须为 16kHz 单声道 PCM16')
            frames = stream.getnframes()
            if not .4 <= frames / RATE <= 55 or len(stream.readframes(frames)) != frames * 2:
                raise ValueError('语音时长或内容无效')
            return frames / RATE
    except (wave.Error, EOFError) as exc:
        raise ValueError('无效语音 WAV') from exc
