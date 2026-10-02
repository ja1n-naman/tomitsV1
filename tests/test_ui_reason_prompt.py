"""The UI must keep asking until a non-empty reason is typed."""

import io

from rich.console import Console

from tomits import services as svc
from tomits import ui
from tomits.models import TaskStatus


def test_fail_prompt_loops_until_reason_given(db_file, monkeypatch):
    app = ui.App(db_file)
    with app.Session() as s:
        task_id = svc.add_task(s, "Write UI", 45).id

    answers = iter([str(task_id), "", "   ", "UI took longer"])
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(answers)))
    monkeypatch.setattr(ui, "console", Console(file=io.StringIO()))

    app.close_with_reason(TaskStatus.FAILED)

    with app.Session() as s:
        task = svc.get_task(s, task_id)
        assert task.status == "failed"
        assert task.latest_reason == "UI took longer"
