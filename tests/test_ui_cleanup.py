"""Guards for the v1.2 fixes: no goals table on the timetable, no example
text in prompts, no sample goals saved."""

import io
import re
from datetime import datetime, time
from pathlib import Path

from rich.console import Console

from tomits import tracking as tr
from tomits import ui
from tomits.periods import PeriodKind

SRC = Path(ui.__file__).parent


def test_timetable_home_screen_has_no_goals_table(db_file, monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(ui, "console", Console(file=out, width=140))
    app = ui.App(db_file, clock=lambda: datetime(2026, 10, 1, 9, 0))
    with app.Session() as s:
        tr.create_goal(s, PeriodKind.DAY, app.today(), "my visible goal", today=app.today())
        tr.set_process(s, PeriodKind.DAY, app.today(), "p", today=app.today())
    app.dashboard()
    text = out.getvalue()
    assert "my visible goal" not in text and "Goals now" not in text
    assert not hasattr(ui, "_goals_table")


def test_no_example_text_in_prompts():
    """'e.g.' and sample numbers are gone from prompts; only error messages
    (raised TaskError) may still list accepted formats."""
    for path in SRC.glob("*.py"):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if "raise TaskError" in line or "Try " in line:
                continue
            assert "e.g." not in line, f"{path.name}:{n}: {line.strip()}"
            assert not re.search(r"\b(500|110)\b", line), f"{path.name}:{n}: {line.strip()}"
            assert "YYYY" not in line, f"{path.name}:{n}: {line.strip()}"


def test_new_database_has_no_sample_goals(session):
    assert tr.open_goals(session) == []
