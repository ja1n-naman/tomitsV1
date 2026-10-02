"""Tracking pages (v1.1): one page per day / week / month with goals,
sacrifices, process and review. The only place goals are created.
All rules live in tracking.py; this screen just asks and shows."""

from __future__ import annotations

from datetime import date
from typing import Optional

from rich.console import Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from . import periods as P
from . import tracking as tr
from .errors import TaskError
from .models import ProgressLog, SacrificeStatus
from .ui_common import ask_amount, ask_text, console, goal_bar, goal_status_text, goal_where, parse_day, rollup_line

Kind = P.PeriodKind

MENU = (
    "[bold]d[/]/[bold]w[/]/[bold]m[/] day/week/month   [bold][[/] previous   [bold]][/] next   [bold]c[/] current\n"
    "[bold]n[/] new goal   [bold]e[/] edit goal   [bold]x[/] delete goal   [bold]l[/] log progress   "
    "[bold]u[/] remove a log   [bold]k[/] mark goal done/not done\n"
    "[bold]p[/] process   [bold]s[/] add sacrifice   [bold]h[/] sacrifice made   [bold]del[/] delete sacrifice   [bold]r[/] review   "
    "[bold]v[/] talk   [bold]b[/] back to timetable"
)


class TrackingScreen:
    def __init__(self, app, kind: Kind = Kind.DAY):
        self.app = app
        self.kind = kind
        self.start = P.period_start(kind, app.today())

    # ----- rendering -----

    def _state_line(self, today: date) -> Text:
        k, s = self.kind, self.start
        end, cutoff = P.period_end(k, s), P.review_cutoff(k, s)
        if not P.has_started(k, s, today):
            return Text("Upcoming: you can plan goals, sacrifices and process now.", style="cyan")
        if not P.is_locked(k, s, today):
            return Text(f"Open until the end of {end:%a %d %b}. Review open until the end of {cutoff:%a %d %b}.", style="green")
        if not P.is_review_locked(k, s, today):
            return Text(
                f"Ended: goals, sacrifices, process and progress are read-only. "
                f"Review open until the end of {cutoff:%a %d %b}.", style="yellow")
        return Text("Closed: everything on this page is read-only.", style="red")

    def render(self) -> None:
        today = self.app.today()
        with self.app.Session() as s:
            entry = tr.get_entry(s, self.kind, self.start)
            goals = list(entry.goals) if entry else []

            gt = Table(title="Goals", title_justify="left", expand=True)
            gt.add_column("ID", justify="right", style="cyan", no_wrap=True)
            gt.add_column("Goal")
            gt.add_column("Linked to", style="dim")
            gt.add_column("Progress", ratio=1)
            gt.add_column("", justify="right", no_wrap=True)
            for g in goals:
                link = f"{g.parent.title} ({goal_where(g.parent)})" if g.parent else ""
                gt.add_row(str(g.id), g.title, link, goal_bar(g), goal_status_text(g))
            if not goals:
                gt.add_row("", Text("No goal yet (required). Press n.", style="red"), "", "", "")

            logs = sorted((l for g in goals for l in g.logs), key=lambda l: (l.logged_for, l.id))
            lt = Table(title="Progress logged here", title_justify="left", expand=True)
            for col in ("ID", "Date", "Goal", "Amount", "From"):
                lt.add_column(col, style="cyan" if col == "ID" else None)
            for l in logs:
                lt.add_row(str(l.id), f"{l.logged_for:%a %d %b}", l.goal.title,
                           f"{tr.fmt_amount(l.amount)} {l.goal.unit}", f"task {l.task_id}" if l.task_id else "")

            st = Table(title="Sacrifices", title_justify="left", expand=True)
            st.add_column("ID", justify="right", style="cyan", no_wrap=True)
            st.add_column("Item")
            st.add_column("Status", no_wrap=True)
            for item in (entry.sacrifices if entry else []):
                style = "green" if item.status == SacrificeStatus.MADE.value else "yellow"
                st.add_row(str(item.id), item.text, Text(item.status, style=style))

            process = entry.process if entry and entry.process else None
            review = entry.review if entry and entry.review else None
            parts = [
                self._state_line(today),
                gt,
                *([lt] if logs else []),
                st,
                Panel(Text(process) if process else Text("No process yet (required). Press p.", style="red"),
                      title="Process", title_align="left"),
                Panel(Text(review) if review else Text("No review yet.", style="dim"),
                      title="Review", title_align="left"),
            ]
            console.clear()
            console.print(Panel(Group(*parts), title=P.label(self.kind, self.start), border_style="magenta"))
            console.print(MENU)

    # ----- input helpers -----

    def _ask_goal_id(self, label: str = "Goal ID") -> Optional[int]:
        raw = Prompt.ask(f"{label} (blank = cancel)", default="", show_default=False).strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            raise TaskError("Enter a number from the ID column.") from None

    def _ask_target(self, label: str):
        """Returns (target, unit) or None for 'no target'."""
        raw = Prompt.ask(label, default="", show_default=False).strip()
        if not raw:
            return None
        target = tr.parse_amount(raw)
        unit = ask_text("Unit")
        return target, unit

    def _ask_parent(self, s, unit: Optional[str]) -> Optional[int]:
        parent_kind = P.PARENT_KIND[self.kind]
        if parent_kind is None:
            return None
        options = tr.link_candidates(s, self.kind, self.start, unit)
        if not options:
            unit_txt = f"unit '{unit}'" if unit else "no target"
            console.print(f"[dim]No {parent_kind.value} goals with {unit_txt} to link to.[/]")
            return None
        console.print(f"Link to a {parent_kind.value} goal (optional):")
        for g in options:
            console.print(f"  [cyan]{g.id}[/] {g.title} [dim]({goal_where(g)}, {tr.progress(g).text})[/]")
        raw = Prompt.ask("Goal ID to link to (blank = none)", default="", show_default=False).strip()
        return int(raw) if raw else None

    # ----- actions -----

    def new_goal(self) -> None:
        with self.app.Session() as s:
            title = ask_text("Goal title")
            shape = self._ask_target("Target (optional)")
            target, unit = shape if shape else (None, None)
            parent_id = self._ask_parent(s, unit)
            goal = tr.create_goal(s, self.kind, self.start, title, target, unit, parent_id, today=self.app.today())
            console.print(f"[green]Goal {goal.id} created.[/]")

    def edit_goal(self) -> None:
        goal_id = self._ask_goal_id("ID of goal to edit")
        if goal_id is None:
            return
        with self.app.Session() as s:
            g = tr.get_goal(s, goal_id)
            console.print(f"Editing '{g.title}' ({tr.progress(g).text}). Blank keeps the current value.")
            changes = {}
            title = ask_text(f"Title [{g.title}]", required=False)
            if title:
                changes["title"] = title
            cur = f"{tr.fmt_amount(g.target)} {g.unit}" if g.has_target else "none"
            raw = Prompt.ask(f"Target [{cur}] ('-' = none)", default="", show_default=False).strip()
            if raw == "-":
                changes["target"] = None
            elif raw:
                changes["target"] = tr.parse_amount(raw)
                unit = ask_text(f"Unit [{g.unit or ''}]", required=not g.unit)
                if unit:
                    changes["unit"] = unit
            if P.PARENT_KIND[g.kind] is not None:
                cur_link = g.parent.title if g.parent else "none"
                raw = Prompt.ask(f"Linked to [{cur_link}] (goal ID, '-' = unlink)", default="", show_default=False).strip()
                if raw == "-":
                    changes["parent_id"] = None
                elif raw:
                    changes["parent_id"] = int(raw)
            if not changes:
                console.print("Nothing changed.")
                return
            tr.update_goal(s, goal_id, today=self.app.today(), **changes)
            console.print("[green]Goal updated.[/]")

    def delete_goal(self) -> None:
        goal_id = self._ask_goal_id("ID of goal to delete")
        if goal_id is None:
            return
        with self.app.Session() as s:
            tr.delete_goal(s, goal_id, today=self.app.today())
            console.print("[green]Goal deleted.[/]")

    def log_progress(self) -> None:
        goal_id = self._ask_goal_id("ID of goal to log progress on")
        if goal_id is None:
            return
        today = self.app.today()
        with self.app.Session() as s:
            g = tr.get_goal(s, goal_id)
            if not g.has_target:
                raise TaskError(f"'{g.title}' has no target; use k to mark it done.")
            amount = ask_amount(f"How many {g.unit}?")
            raw = Prompt.ask("Date (blank = today)", default="", show_default=False)
            tr.log_progress(s, goal_id, amount, on=parse_day(raw, today), today=today)
            s.refresh(g)
            console.print(f"[green]Logged.[/] {rollup_line(g)}")

    def remove_log(self) -> None:
        raw = Prompt.ask("ID of progress log to remove (blank = cancel)", default="", show_default=False).strip()
        if not raw:
            return
        with self.app.Session() as s:
            tr.delete_log(s, int(raw), today=self.app.today())
            console.print("[green]Log removed.[/]")

    def toggle_done(self) -> None:
        goal_id = self._ask_goal_id("ID of goal to mark done / not done")
        if goal_id is None:
            return
        with self.app.Session() as s:
            g = tr.get_goal(s, goal_id)
            done = not tr.progress(g).done
            tr.set_goal_done(s, goal_id, done, today=self.app.today())
            console.print(f"[green]'{g.title}' is now {'done' if done else 'not done'}.[/]")

    def set_process(self) -> None:
        with self.app.Session() as s:
            entry = tr.get_entry(s, self.kind, self.start)
            if entry and entry.process:
                console.print(Panel(entry.process, title="Current process"))
            text = ask_text("Process: how will you get there?")
            tr.set_process(s, self.kind, self.start, text, today=self.app.today())
            console.print("[green]Process saved.[/]")

    def add_sacrifice(self) -> None:
        with self.app.Session() as s:
            text = ask_text("Sacrifice (what you give up)")
            status = Prompt.ask("Status", choices=["planned", "made"], default="planned")
            tr.add_sacrifice(s, self.kind, self.start, text, status, today=self.app.today())
            console.print("[green]Sacrifice added.[/]")

    def _ask_sacrifice_id(self, action: str) -> Optional[int]:
        raw = Prompt.ask(f"ID of sacrifice to {action} (blank = cancel)", default="", show_default=False).strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            raise TaskError("Enter a sacrifice ID from the list.") from None

    def sacrifice_made(self) -> None:
        sid = self._ask_sacrifice_id("mark as made")
        if sid is None:
            return
        with self.app.Session() as s:
            item = tr.mark_sacrifice_made(s, sid, today=self.app.today())
            console.print(f"[green]'{item.text}' is marked as made.[/]")

    def remove_sacrifice(self) -> None:
        sid = self._ask_sacrifice_id("delete")
        if sid is None:
            return
        with self.app.Session() as s:
            tr.remove_sacrifice(s, sid, today=self.app.today())
            console.print("[green]Sacrifice deleted.[/]")

    def set_review(self) -> None:
        with self.app.Session() as s:
            entry = tr.get_entry(s, self.kind, self.start)
            if entry and entry.review:
                console.print(Panel(entry.review, title="Current review"))
            raw = Prompt.ask("Review (blank = keep, '-' = clear)", default="", show_default=False).strip()
            if not raw:
                return
            tr.set_review(s, self.kind, self.start, None if raw == "-" else raw, today=self.app.today())
            console.print("[green]Review saved.[/]")

    def switch_kind(self, kind: Kind) -> None:
        """Keep the date context: if the page being viewed contains today,
        open today's period of the new kind; otherwise the one containing
        the viewed page's first day."""
        today = self.app.today()
        anchor = today if P.contains(self.kind, self.start, today) else self.start
        self.kind = kind
        self.start = P.period_start(kind, anchor)

    # ----- loop -----

    # ----- navigation (typed keys come from the registry) -----

    def view_day_page(self):
        self.switch_kind(Kind.DAY)

    def view_week_page(self):
        self.switch_kind(Kind.WEEK)

    def view_month_page(self):
        self.switch_kind(Kind.MONTH)

    def go_prev(self):
        self.start = P.shift(self.kind, self.start, -1)

    def go_next(self):
        self.start = P.shift(self.kind, self.start, 1)

    def go_current(self):
        self.start = P.period_start(self.kind, self.app.today())

    def go_back(self):
        return "back"

    NAV = {"view_day_page", "view_week_page", "view_month_page", "go_prev", "go_next", "go_current", "go_back"}

    def voice(self) -> bool:
        """Push-to-talk on this page: voice knows which page is open."""
        st = self.app.voice_state
        st.view_kind, st.view_start = self.kind.value, self.start
        result = self.app.voice_turn()
        if result == "close_tracking":
            return False
        if st.view_kind:
            self.kind, self.start = Kind(st.view_kind), st.view_start
        return True

    # ----- loop -----

    def run(self) -> None:
        from .voice import registry as vreg
        actions = {k: getattr(self, m) for k, m in vreg.typed_map(vreg.TRACKING).items()}
        ptt = self.app.settings.push_to_talk_key
        while True:
            self.app.attend()  # ringing alarms and check-ins work here too
            self.render()
            try:
                choice = Prompt.ask("\ntracking >", choices=list(actions) + [ptt],
                                    default="", show_choices=False, show_default=False)
            except (KeyboardInterrupt, EOFError):
                return
            if choice == "":
                continue  # refresh
            if choice == ptt:
                if not self.voice():
                    self.app.voice_state.view_kind = None
                    return
                Prompt.ask("[dim]Press Enter to continue[/]", default="", show_default=False)
                continue
            method = vreg.typed_map(vreg.TRACKING)[choice]
            if method in self.NAV:
                if actions[choice]() == "back":
                    return
                continue
            try:
                actions[choice]()
            except KeyboardInterrupt:
                console.print("\n[yellow]Cancelled. Nothing was changed.[/]")
            except (TaskError, ValueError) as e:
                console.print(f"[red]{e}[/]")
            Prompt.ask("[dim]Press Enter to continue[/]", default="", show_default=False)
