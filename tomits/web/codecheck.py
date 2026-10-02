"""Keeps the page and the server from drifting apart.

The server's Python code (and so its command registry) is loaded once, when
it starts. If the page files were read from disk on every request, updating
tomits while it runs would give the browser new buttons that the old server
doesn't know ("Unknown action"). So:

- FrontEnd takes a snapshot of the static files when the server starts and
  serves only that, so the page always matches the running registry;
- Fingerprint notices when the code on disk changes after the start, and the
  page then shows "restart tomits to finish the update".
"""

from __future__ import annotations

import hashlib
import mimetypes
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

PACKAGE = Path(__file__).resolve().parent.parent          # tomits/
STATIC = Path(__file__).resolve().parent / "static"


class FrontEnd:
    """The page files as they were when the server started."""

    def __init__(self, root: Path = STATIC) -> None:
        self.files: Dict[str, Tuple[bytes, str]] = {}
        for p in sorted(root.rglob("*")):
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                kind = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                if kind.startswith("text/") or kind in ("application/javascript", "image/svg+xml"):
                    kind += "; charset=utf-8"
                self.files[rel] = (p.read_bytes(), kind)

    def get(self, rel: str) -> Optional[Tuple[bytes, str]]:
        return self.files.get(rel)


def fingerprint(root: Path = PACKAGE) -> str:
    """Names, sizes and change times of tomits' code and page files."""
    h = hashlib.sha1()
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in (".py", ".js", ".css", ".html") and "__pycache__" not in p.parts:
            st = p.stat()
            h.update(f"{p.relative_to(root).as_posix()}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


class Fingerprint:
    """Has the code on disk changed since the server started? Checked at
    most every `every` seconds (a few hundred file stats)."""

    def __init__(self, root: Path = PACKAGE, every: float = 5.0) -> None:
        self.root, self.every = root, every
        self.at_start = fingerprint(root)
        self._checked, self._changed = time.monotonic(), False
        self._lock = threading.Lock()

    def changed(self) -> bool:
        with self._lock:
            if not self._changed and time.monotonic() - self._checked >= self.every:
                self._checked = time.monotonic()
                self._changed = fingerprint(self.root) != self.at_start
            return self._changed
