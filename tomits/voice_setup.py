"""Download the local voice models, after telling you the size and asking.

    python -m tomits.voice_setup                  whisper model from settings + language model
    python -m tomits.voice_setup --whisper medium one Whisper size (for the benchmark, say)

Whisper models come from Hugging Face (public, no account). The language model
is pulled by Ollama (installed separately from ollama.com, no account). No
audio or text is ever sent anywhere; only the model files are downloaded.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


def ask(question: str) -> bool:
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def setup_whisper(size: str) -> bool:
    from .voice.stt import SttUnavailable, WhisperEngine, model_label
    try:
        WhisperEngine(size)
        print(f"{model_label(size)} is already downloaded.")
        return True
    except SttUnavailable:
        pass
    if not ask(f"Download {model_label(size)} for speech recognition?"):
        print("Skipped.")
        return False
    print("Downloading ... (this runs once)")
    try:
        WhisperEngine(size, download=True)
    except SttUnavailable as e:
        print(f"Failed: {e}")
        return False
    print("Done.")
    return True


def setup_llm(model: str) -> bool:
    from .voice.nlu import LLM_MODEL_SIZES_MB, OllamaBackend
    backend = OllamaBackend(model)
    reason = backend.available()
    if reason is None:
        print(f"The language model {model} is ready.")
        return True
    if shutil.which("ollama") is None and "isn't running" in reason:
        print("Ollama isn't installed. It's optional: without it tomits uses its built-in phrases.\n"
              "To understand rephrased commands, install Ollama from https://ollama.com/download (free, no account,\n"
              "runs only on this PC), then run voice_setup.bat again.")
        return False
    size = LLM_MODEL_SIZES_MB.get(model)
    if not ask(f"Download the language model {model}{f' (about {size} MB)' if size else ''} with Ollama?"):
        print("Skipped.")
        return False
    return subprocess.call(["ollama", "pull", model]) == 0


def main(argv=None) -> int:
    from .db import default_db_path
    from .settings import load_settings, settings_path
    args = argparse.ArgumentParser(description=__doc__).parse_known_args(argv)[1]
    settings = load_settings(settings_path(default_db_path()))
    if "--whisper" in args:
        return 0 if setup_whisper(args[args.index("--whisper") + 1]) else 1
    print("Step 1 of 2: speech recognition")
    setup_whisper(settings.stt_model)
    print("\nStep 2 of 2: understanding rephrased commands (optional)")
    if settings.llm_enabled:
        setup_llm(settings.llm_model)
    else:
        print("The local language model is turned off in settings.")
    print("\nNext: voice_mictest.bat to test your mic, voice_benchmark.bat to pick the best Whisper size.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
