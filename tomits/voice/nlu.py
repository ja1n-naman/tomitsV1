"""Understanding what was meant (v1.5.1).

1. The rule patterns from v1.5 are tried first (fast, exact).
2. If nothing matches and the local language model is on, it gets the
   transcript, the list of registry commands with their fields, and the
   names of your current tasks and goals, and must answer with JSON:
   {"command": <registry name or "none">, "fields": {...}, "confidence": 0-1}.
3. That answer is validated: known command, only allowed fields, required
   fields present, allowed values, confidence high enough, a delete-like word
   actually said for destructive commands. It's rendered into a canonical
   sentence that must match the same command through the rule patterns.
   Anything else -> "not understood".

The model never runs anything. The backend is replaceable (see `LlmBackend`);
the default talks to Ollama on 127.0.0.1 only.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol

from . import parse as P
from . import registry as R
from .specs import DESTRUCTIVE_WORDS, SPECS, Spec

# ---------- tuning ----------
LLM_TIMEOUT_SECONDS = 8.0      # slower than this -> fall back to the rules
LLM_MIN_CONFIDENCE = 0.6       # the model's own confidence must reach this
OLLAMA_URL = "http://127.0.0.1:11434"   # local only
DEFAULT_LLM_MODEL = "qwen2.5:1.5b"
LLM_MODEL_SIZES_MB = {"qwen2.5:0.5b": 398, "qwen2.5:1.5b": 986, "qwen2.5:3b": 1900, "llama3.2:1b": 1300,
                      "llama3.2:3b": 2000, "gemma2:2b": 1600}
MAX_FIELD_CHARS = 120


@dataclass
class Interpretation:
    command: str
    groups: Dict[str, Optional[str]]
    canonical: str
    source: str                 # "rules" or "model"
    fields: Dict[str, str] = field(default_factory=dict)
    model_confidence: float = 1.0

    @property
    def plain(self) -> str:
        """What will happen, in plain words, for the screen."""
        text = re.sub(r"\bi\b", "I", self.canonical)
        return text[:1].upper() + text[1:]


class Invalid(Exception):
    """The model's answer can't be used."""


class LlmBackend(Protocol):
    name: str

    def available(self) -> Optional[str]:
        """None if ready, else a reason."""

    def complete(self, prompt: str, schema: dict, timeout: float) -> str:
        """Return the raw JSON text."""


class OllamaBackend:
    """Ollama running on this PC (http://127.0.0.1:11434). No account; text
    never leaves the computer."""

    def __init__(self, model: str = DEFAULT_LLM_MODEL, url: str = OLLAMA_URL):
        self.model, self.url, self.name = model, url.rstrip("/"), f"ollama:{model}"

    def _call(self, path: str, payload: Optional[dict], timeout: float) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"},
                                     method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def available(self) -> Optional[str]:
        try:
            tags = self._call("/api/tags", None, 2.0)
        except Exception:
            return "Ollama isn't running (install it from ollama.com; no account needed)"
        names = {m.get("name", "") for m in tags.get("models", [])}
        if not any(n == self.model or n.split(":")[0] == self.model and ":" not in self.model for n in names):
            if self.model not in names:
                return f"the model {self.model} isn't downloaded (run voice_setup.bat)"
        return None

    def complete(self, prompt: str, schema: dict, timeout: float) -> str:
        out = self._call("/api/generate", {"model": self.model, "prompt": prompt, "format": schema, "stream": False,
                                           "options": {"temperature": 0, "num_predict": 200}}, timeout)
        return out.get("response", "")


# ---------- prompt, schema, validation ----------

def build_schema() -> dict:
    return {"type": "object", "properties": {
        "command": {"type": "string", "enum": sorted(SPECS) + ["none"]},
        "fields": {"type": "object", "additionalProperties": {"type": "string"}},
        "confidence": {"type": "number"}}, "required": ["command", "fields", "confidence"]}


def build_prompt(transcript: str, tasks: List[str], goals: List[str]) -> str:
    lines = []
    for c in R.REGISTRY:
        spec = SPECS.get(c.name)
        if spec is None or R.MAIN not in c.contexts:
            continue
        fields = ", ".join(f"{f}{' (required)' if f in spec.required else ''}"
                           + (f" one of {'/'.join(spec.enums[f])}" if f in spec.enums else "") for f in spec.fields)
        lines.append(f"- {c.name}: {c.summary}. {spec.hint} fields: {fields or 'none'}")
    return (
        "You map what a user said to ONE command of a personal task app. The speech-to-text may contain errors "
        "(Indian English accent). Choose only from the commands below. If it's unclear, garbled, or not one of "
        "them, answer command \"none\". Never invent commands or fields. Use the user's own task and goal names "
        "when they match. Answer only JSON.\n\n"
        "Commands:\n" + "\n".join(lines) + "\n\n"
        f"Current tasks: {', '.join(tasks[:40]) or 'none'}\n"
        f"Current goals: {', '.join(goals[:40]) or 'none'}\n\n"
        f"User said: \"{transcript}\"\n"
        "JSON with keys command, fields (strings), confidence (0 to 1):"
    )


def validate(raw_text: str, transcript: str) -> Interpretation:
    try:
        raw = json.loads(raw_text)
    except (TypeError, ValueError):
        raise Invalid("not JSON") from None
    if not isinstance(raw, dict):
        raise Invalid("not an object")
    command, fields, conf = raw.get("command"), raw.get("fields", {}), raw.get("confidence", 0)
    if not isinstance(command, str) or command == "none":
        raise Invalid("no command")
    spec: Optional[Spec] = SPECS.get(command)
    if spec is None:
        raise Invalid(f"unknown command {command!r}")
    if not isinstance(fields, dict):
        raise Invalid("fields must be an object")
    if not isinstance(conf, (int, float)) or conf < LLM_MIN_CONFIDENCE:
        raise Invalid(f"model confidence too low ({conf})")
    clean: Dict[str, str] = {}
    for k, v in fields.items():
        if k not in spec.fields:
            raise Invalid(f"unexpected field {k!r} for {command}")
        if v is None or v == "":
            continue
        if not isinstance(v, (str, int, float)):
            raise Invalid(f"field {k!r} must be text")
        v = P.normalize(str(v))
        if len(v) > MAX_FIELD_CHARS or not v:
            raise Invalid(f"field {k!r} is empty or too long")
        if k in spec.enums and v not in spec.enums[k]:
            raise Invalid(f"field {k!r} must be one of {spec.enums[k]}")
        clean[k] = v
    for k in spec.required:
        if not clean.get(k):
            raise Invalid(f"missing required field {k!r}")
    norm = P.normalize(transcript)
    if spec.destructive and not any(re.search(rf"\b{w}\b", norm) for w in DESTRUCTIVE_WORDS):
        raise Invalid("a delete-type command needs a delete-type word in what was said")
    canonical = spec.render(clean)
    if canonical is None:
        raise Invalid("fields don't fit any form of the command")
    found = R.match(P.normalize(canonical))
    if found is None or found[0].name != command:
        raise Invalid(f"canonical form {canonical!r} doesn't map back to {command}")
    return Interpretation(command, found[1], canonical, "model", clean, float(conf))


class Understanding:
    """Rules first, then the local model (optional, with a timeout)."""

    def __init__(self, backend: Optional[LlmBackend] = None, timeout: float = LLM_TIMEOUT_SECONDS):
        self.backend = backend
        self.timeout = timeout
        self.last_note: Optional[str] = None     # why the model wasn't used / was rejected

    def interpret(self, transcript: str, tasks: List[str] = (), goals: List[str] = ()) -> Optional[Interpretation]:
        self.last_note = None
        norm = P.normalize(transcript)
        found = R.match(norm)
        if found is not None:
            return Interpretation(found[0].name, found[1], norm, "rules")
        if self.backend is None:
            self.last_note = "local model off"
            return None
        reason = self.backend.available()
        if reason:
            self.last_note = reason
            return None
        box: Dict[str, object] = {}

        def run():
            try:
                box["text"] = self.backend.complete(build_prompt(transcript, list(tasks), list(goals)),
                                                    build_schema(), self.timeout)
            except Exception as e:
                box["error"] = e

        th = threading.Thread(target=run, daemon=True)
        th.start()
        th.join(self.timeout)
        if th.is_alive():
            self.last_note = f"local model took longer than {self.timeout:g} s"
            return None
        if "error" in box:
            self.last_note = f"local model error: {box['error']}"
            return None
        try:
            return validate(box.get("text", ""), transcript)
        except Invalid as e:
            self.last_note = f"model answer rejected: {e}"
            return None
