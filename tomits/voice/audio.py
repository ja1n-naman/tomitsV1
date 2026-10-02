"""Microphone audio for speech recognition (v1.5.1).

Everything the recognizer gets is mono 16 kHz float32, volume-normalized,
silence-trimmed, with a short padding at the end so the last word isn't cut.
The pure functions here are tested without a microphone; record() / play()
need sounddevice.
"""

from __future__ import annotations

import queue
import time as _time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np

# ---------- tuning ----------
SAMPLE_RATE = 16000        # what Whisper expects
END_PADDING_S = 0.3        # silence added after the last word
KEEP_MARGIN_S = 0.15       # audio kept around the speech when trimming
TARGET_PEAK = 0.9          # normalize loudest sample to this
FRAME_S = 0.03             # 30 ms frames for level / silence detection
SILENCE_RATIO = 0.1        # a frame is silent below 10% of the loudest frame's level...
SILENCE_FLOOR = 0.004      # ...or below this absolute level
STOP_AFTER_SILENCE_S = 1.0 # push-to-talk: stop this long after you stop speaking
MAX_RECORD_S = 10.0
START_TIMEOUT_S = 6.0      # give up if nothing is said
LOW_RATE_WARN_HZ = 16000   # devices offering less than this are warned about


def to_mono(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    return x.mean(axis=1) if x.ndim == 2 else x


def resample(x: np.ndarray, sr_from: int, sr_to: int = SAMPLE_RATE) -> np.ndarray:
    if sr_from == sr_to or len(x) == 0:
        return x.astype(np.float32)
    n = int(round(len(x) * sr_to / sr_from))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def normalize(x: np.ndarray, target: float = TARGET_PEAK) -> np.ndarray:
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak < 1e-4:
        return x.astype(np.float32)
    return (x * (target / peak)).astype(np.float32)


def frame_levels(x: np.ndarray, sr: int = SAMPLE_RATE, frame_s: float = FRAME_S) -> np.ndarray:
    n = max(1, int(sr * frame_s))
    frames = len(x) // n
    if frames == 0:
        return np.array([float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0])
    return np.sqrt(np.mean(x[: frames * n].reshape(frames, n) ** 2, axis=1))


def trim_silence(x: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    levels = frame_levels(x, sr)
    if len(levels) == 0 or levels.max() < SILENCE_FLOOR:
        return x[:0]
    voiced = np.where(levels >= max(SILENCE_FLOOR, SILENCE_RATIO * levels.max()))[0]
    n = int(sr * FRAME_S)
    keep = int(sr * KEEP_MARGIN_S)
    start = max(0, voiced[0] * n - keep)
    end = min(len(x), (voiced[-1] + 1) * n + keep)
    return x[start:end]


def pad_end(x: np.ndarray, sr: int = SAMPLE_RATE, seconds: float = END_PADDING_S) -> np.ndarray:
    return np.concatenate([x, np.zeros(int(sr * seconds), dtype=np.float32)]).astype(np.float32)


def prepare(x: np.ndarray, sr: int) -> np.ndarray:
    """Raw recording -> what the recognizer gets. Empty if there's no speech."""
    x = resample(to_mono(x), sr, SAMPLE_RATE)
    x = trim_silence(normalize(x))
    return pad_end(x) if len(x) else x


def level_db(block: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.asarray(block, dtype=np.float32) ** 2))) if len(block) else 0.0
    return 20 * np.log10(max(rms, 1e-6))


def save_wav(path, x: np.ndarray, sr: int = SAMPLE_RATE) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(to_mono(x), -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data)
    return path


def load_wav(path) -> Tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    elif width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    else:
        raise ValueError(f"unsupported sample width {width}")
    if ch > 1:
        x = x.reshape(-1, ch)
    return to_mono(x), sr


# ---------- devices ----------

@dataclass
class DeviceInfo:
    index: Optional[int]
    name: str
    samplerate: int
    channels: int

    @property
    def warning(self) -> Optional[str]:
        low = self.samplerate < LOW_RATE_WARN_HZ
        handsfree = any(w in self.name.lower() for w in ("hands-free", "handsfree", "hands free", "headset"))
        if low:
            return (f"'{self.name}' only records at {self.samplerate} Hz. Bluetooth earphones switch to call mode "
                    "(8 kHz) when the mic is used, which drops the sounds that tell words apart, so recognition "
                    "will be poor. A wired mic, the laptop mic, or a USB headset gives 16 kHz or better.")
        if handsfree:
            return (f"'{self.name}' looks like a Bluetooth hands-free (call mode) input. If recognition is poor, "
                    "try the laptop mic or a wired / USB mic.")
        return None

    def describe(self) -> str:
        return f"{self.name} ({self.samplerate} Hz, {self.channels} ch)"


def _sd():
    import sounddevice as sd
    return sd


def list_input_devices() -> List[DeviceInfo]:
    sd = _sd()
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0:
            out.append(DeviceInfo(i, d["name"], int(d.get("default_samplerate") or 0), int(d["max_input_channels"])))
    return out


def input_device(device=None) -> DeviceInfo:
    sd = _sd()
    d = sd.query_devices(device if device not in ("", None) else None, kind="input")
    idx = device if isinstance(device, int) else d.get("index")
    return DeviceInfo(idx, d["name"], int(d.get("default_samplerate") or 0), int(d.get("max_input_channels", 1)))


def _best_rate(sd, device, info: DeviceInfo) -> int:
    try:
        sd.check_input_settings(device=device, samplerate=SAMPLE_RATE, channels=1)
        return SAMPLE_RATE
    except Exception:
        return info.samplerate or SAMPLE_RATE


def record(device=None, max_seconds: float = MAX_RECORD_S, stop_on_silence: bool = True,
           on_level: Optional[Callable[[float], None]] = None, fixed_seconds: Optional[float] = None
           ) -> Tuple[np.ndarray, int, DeviceInfo]:
    """Record from the mic. Push-to-talk: stops STOP_AFTER_SILENCE_S after you
    stop speaking, or after max_seconds; fixed_seconds records exactly that long."""
    sd = _sd()
    dev = device if device not in ("", None) else None
    info = input_device(dev)
    sr = _best_rate(sd, dev, info)
    q: "queue.Queue[np.ndarray]" = queue.Queue()

    def cb(indata, frames, t, status):
        q.put(indata.copy())

    chunks, began = [], _time.monotonic()
    speaking_at, quiet_since = None, None
    limit = fixed_seconds or max_seconds
    with sd.InputStream(device=dev, samplerate=sr, channels=1, dtype="float32", blocksize=int(sr * 0.1), callback=cb):
        while _time.monotonic() - began < limit:
            try:
                block = q.get(timeout=0.5)[:, 0]
            except queue.Empty:
                continue
            chunks.append(block)
            db = level_db(block)
            if on_level:
                on_level(db)
            if fixed_seconds:
                continue
            loud = db > -45
            if loud:
                speaking_at = speaking_at or _time.monotonic()
                quiet_since = None
            elif speaking_at:
                quiet_since = quiet_since or _time.monotonic()
                if stop_on_silence and _time.monotonic() - quiet_since >= STOP_AFTER_SILENCE_S:
                    break
            elif _time.monotonic() - began > START_TIMEOUT_S:
                break
    x = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    return x, sr, DeviceInfo(info.index, info.name, sr, info.channels)


def play(x: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    sd = _sd()
    sd.play(x, sr)
    sd.wait()
