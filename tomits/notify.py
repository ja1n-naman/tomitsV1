"""Desktop notification (toast). The alarm tone lives in ringer.py."""

from __future__ import annotations

import threading
from typing import Optional


class DesktopNotifier:
    """Shows a desktop toast (plyer) on its own short thread so a slow toast
    never delays anything. Failures are kept in `last_error`."""

    def __init__(self, app_name: str = "tomits") -> None:
        self.app_name = app_name
        self.last_error: Optional[str] = None

    def notify(self, title: str, message: str, urgent: bool = False) -> None:
        threading.Thread(target=self._toast, args=(title, message), daemon=True).start()

    def _toast(self, title: str, message: str) -> None:
        try:
            from plyer import notification

            # Windows limits: title 64 chars, message 256 chars.
            notification.notify(title=title[:64], message=message[:256], app_name=self.app_name, timeout=10)
        except Exception as e:  # plyer missing, no notification backend, etc.
            self.last_error = f"Desktop notification failed: {e}"
