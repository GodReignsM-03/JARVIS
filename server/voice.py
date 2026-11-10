"""Jarvis's voice: Kokoro (free, local) + the locked AI 2.5 processing chain. See voice/VOICE.md."""
import io
import subprocess
from functools import lru_cache

import numpy as np
import soundfile as sf

from . import config

BLEND = {"bm_daniel": 0.85, "bm_george": 0.15}
SPEED = float(__import__("os").environ.get("JARVIS_VOICE_SPEED", "0.95"))  # approved 0.88 for dramatic lines; 0.95 for conversation
FILTERS = {
    "2": "highpass=f=90,equalizer=f=250:t=q:w=1:g=2,equalizer=f=3000:t=q:w=1.2:g=4,"
         "acompressor=threshold=-20dB:ratio=3:attack=3:release=60:makeup=3,"
         "chorus=0.8:0.9:22:0.3:0.5:1.5,aecho=0.8:0.7:22|37:0.18|0.1,volume=10.8dB,alimiter=limit=0.95",
    "2.5": "highpass=f=90,equalizer=f=250:t=q:w=1:g=2,equalizer=f=3000:t=q:w=1.2:g=4,"
           "acompressor=threshold=-20dB:ratio=3:attack=3:release=60:makeup=3,"
           "flanger=delay=1:depth=1.2:regen=5:width=25:speed=0.25,chorus=0.8:0.9:22:0.32:0.5:1.6,"
           "aecho=0.8:0.7:22|37:0.2|0.11,volume=10.8dB,alimiter=limit=0.95",
    "3": "highpass=f=90,equalizer=f=250:t=q:w=1:g=2,equalizer=f=3000:t=q:w=1.2:g=4,"
         "acompressor=threshold=-20dB:ratio=3:attack=3:release=60:makeup=3,"
         "flanger=delay=1:depth=1.5:regen=10:width=45:speed=0.25,chorus=0.8:0.9:22:0.35:0.5:1.8,"
         "aecho=0.8:0.7:22|37:0.22|0.12,volume=10.8dB,alimiter=limit=0.95",
}
DEFAULT_TONE = "2.5"

_engine = None
_style = None


def load() -> bool:
    """Load the voice model once. Returns False (not an exception) if the files are missing."""
    global _engine, _style
    if _engine is not None:
        return True
    d = config.VOICE_MODEL_DIR
    if not (d / "model.onnx").exists() or not (d / "voices.npz").exists():
        return False
    from kokoro_onnx import Kokoro

    _engine = Kokoro(str(d / "model.onnx"), str(d / "voices.npz"))
    _style = sum(w * _engine.get_voice_style(n) for n, w in BLEND.items())
    return True


def loaded() -> bool:
    return _engine is not None


@lru_cache(maxsize=256)
def speak(text: str, tone: str = DEFAULT_TONE) -> bytes:
    """Text -> processed MP3 bytes. Cached so repeated lines ("Hello, sir.") are instant."""
    if not load():
        raise RuntimeError("voice model not installed")
    audio, sr = _engine.create(text, voice=_style, speed=SPEED, lang="en-gb")
    # Short lead-in silence keeps the compressor/echo from clipping the first syllable.
    audio = np.concatenate([np.zeros(int(0.03 * sr), dtype=audio.dtype), audio])
    wav = io.BytesIO()
    sf.write(wav, audio, sr, format="WAV")
    proc = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-af", FILTERS.get(tone, FILTERS[DEFAULT_TONE]),
         "-ar", "24000", "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "pipe:1"],
        input=wav.getvalue(), capture_output=True, check=True, timeout=30,
    )
    return proc.stdout
