"""Rendering and input helpers shared by the timetable and tracking screens."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from rich.console import Console
from rich.progress_bar import ProgressBar
from rich.prompt import Prompt
from rich.text import Text

from . import periods as P
from . import services as svc
from . import tracking as tr
from .models import Goal

console = Console()


def ask_text(label: str, required: bool = True) -> Optional[str]:
    while True:
        value = (Prompt.ask(label, default="", show_default=False) or "").strip()
        if value or not required:
            return value or None
        console.print("[red]This can't be empty.[/]")


def ask_duration(label: str = "Duration") -> int:
    while True:
        try:
            return svc.parse_duration(Prompt.ask(label))
        except svc.TaskError as e:
            console.print(f"[red]{e}[/]")


def ask_time(label: str) -> Optional[time]:
    """Blank means no time."""
    while True:
        raw = (Prompt.ask(label, default="", show_default=False) or "").strip()
        if not raw:
            return None
        try:
            return svc.parse_time(raw)
        except svc.TaskError as e:
            console.print(f"[red]{e}[/]")


def parse_day(raw: str, today: date) -> date:
    raw = (raw or "").strip().lower()
    if raw in ("", "today", "t"):
        return today
    if raw in ("tomorrow", "tm"):
        return today + timedelta(days=1)
    if raw in ("yesterday", "y"):
        return today - timedelta(days=1)
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise svc.TaskError("Use today, tomorrow, yesterday or a date like 2026-10-01.") from None


def ask_day(today: date, label: str = "Which day?") -> date:
    while True:
        try:
            return parse_day(Prompt.ask(label, default="today"), today)
        except svc.TaskError as e:
            console.print(f"[red]{e}[/]")


def ask_amount(label: str, default: Optional[str] = None) -> float:
    while True:
        raw = Prompt.ask(label, default=default, show_default=default is not None)
        try:
            return tr.parse_amount(raw)
        except svc.TaskError as e:
            console.print(f"[red]{e}[/]")


def goal_bar(goal: Goal) -> ProgressBar:
    p = tr.progress(goal)
    return ProgressBar(total=1000, completed=int(p.fraction * 1000), width=None)


def goal_status_text(goal: Goal) -> Text:
    p = tr.progress(goal)
    return Text(p.text, style="green" if p.done else "")


def goal_where(goal: Goal) -> str:
    return P.short_label(goal.kind, goal.period_start)


def goal_line(goal: Goal) -> str:
    """Goal ID, title, period and progress on one line (for pick lists)."""
    return f"[cyan]{goal.id}[/] {goal.title} [dim]({goal_where(goal)}, {tr.progress(goal).text})[/]"


def rollup_line(goal: Goal) -> str:
    """The goal's progress followed by each linked goal above it."""
    parts = [f"'{goal.title}' {tr.progress(goal).text}"]
    for g in tr.ancestors(goal):
        parts.append(f"{g.kind.value} '{g.title}' {tr.progress(g).text}")
    return "  ->  ".join(parts)
