"""Speech-to-text with faster-whisper (v1.5.1). Local, offline after the model
is downloaded once; no account, audio never leaves the PC.

Model size is a setting (`stt_model`). Multilingual models are used with
language="en": they handle Indian English better than the English-only
".en" models in our tests' design; the benchmark script checks this on your
own clips.
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

from ..db import PROJECT_ROOT
from .dialog import Heard

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

MODELS_DIR = PROJECT_ROOT / "data" / "whisper-models"
DEFAULT_MODEL = "small"
# approximate download sizes (MB) of the faster-whisper models
MODEL_SIZES_MB = {"tiny": 75, "base": 145, "small": 484, "medium": 1530, "large-v3-turbo": 1620,
                  "large-v3": 3100, "small.en": 484, "base.en": 145, "medium.en": 1530}
NO_SPEECH_LIMIT = 0.6      # segments Whisper itself thinks are silence are dropped


class SttUnavailable(Exception):
    pass


def model_label(size: str) -> str:
    mb = MODEL_SIZES_MB.get(size)
    return f"Whisper '{size}' (about {mb} MB)" if mb else f"Whisper '{size}'"


class WhisperEngine:
    def __init__(self, size: str = DEFAULT_MODEL, download: bool = False, threads: Optional[int] = None):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise SttUnavailable("faster-whisper isn't installed. Run run.bat to install it.") from None
        self.size = size
        try:
            self.model = WhisperModel(size, device="cpu", compute_type="int8", download_root=str(MODELS_DIR),
                                      local_files_only=not download, cpu_threads=threads or (os.cpu_count() or 4))
        except Exception as e:
            if not download:
                raise SttUnavailable(f"the {model_label(size)} model isn't downloaded yet. "
                                     "Run voice_setup.bat to download it.") from None
            raise SttUnavailable(f"couldn't load {model_label(size)}: {e}") from None

    def transcribe(self, audio16k: np.ndarray, hint: str = "") -> Heard:
        if len(audio16k) < 1600:  # under 0.1 s of speech
            return Heard("", 0.0)
        segments, _info = self.model.transcribe(
            audio16k, language="en", beam_size=5, temperature=0.0, word_timestamps=True,
            condition_on_previous_text=False, initial_prompt=hint or None, vad_filter=False)
        words, texts = [], []
        for seg in segments:
            if seg.no_speech_prob > NO_SPEECH_LIMIT and seg.avg_logprob < -0.8:
                continue
            texts.append(seg.text)
            words += [w.probability for w in (seg.words or [])]
        text = " ".join(t.strip() for t in texts).strip()
        conf = float(np.mean(words)) if words else (0.5 if text else 0.0)
        return Heard(text, conf)
