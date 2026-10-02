"""Day / week / month periods. Pure date math, no database.

Weeks start on Sunday. A period "ends" at local midnight after its last
day: from then on it is locked. Its review stays open one more day.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from enum import Enum
from typing import List, Optional


class PeriodKind(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


PARENT_KIND = {PeriodKind.DAY: PeriodKind.WEEK, PeriodKind.WEEK: PeriodKind.MONTH, PeriodKind.MONTH: None}
ORDER = {PeriodKind.DAY: 0, PeriodKind.WEEK: 1, PeriodKind.MONTH: 2}


def period_start(kind, d: date) -> date:
    kind = PeriodKind(kind)
    if kind is PeriodKind.DAY:
        return d
    if kind is PeriodKind.WEEK:
        return d - timedelta(days=(d.weekday() + 1) % 7)  # Mon=0 .. Sun=6
    return d.replace(day=1)


def period_end(kind, d: date) -> date:
    kind = PeriodKind(kind)
    start = period_start(kind, d)
    if kind is PeriodKind.DAY:
        return start
    if kind is PeriodKind.WEEK:
        return start + timedelta(days=6)
    return start.replace(day=calendar.monthrange(start.year, start.month)[1])


def contains(kind, start: date, d: date) -> bool:
    return period_start(kind, start) <= d <= period_end(kind, start)


def has_started(kind, start: date, today: date) -> bool:
    return today >= period_start(kind, start)


def is_locked(kind, start: date, today: date) -> bool:
    """Goals, sacrifices, process and progress logs are read-only."""
    return today > period_end(kind, start)


def review_cutoff(kind, start: date) -> date:
    """Last day on which the review can still be written."""
    return period_end(kind, start) + timedelta(days=1)


def is_review_locked(kind, start: date, today: date) -> bool:
    return today > review_cutoff(kind, start)


def parent_starts(kind, start: date) -> List[date]:
    """Starts of the periods a goal of this period may link up to.
    A week spanning two months may link to either month."""
    kind = PeriodKind(kind)
    start = period_start(kind, start)
    if kind is PeriodKind.DAY:
        return [period_start(PeriodKind.WEEK, start)]
    if kind is PeriodKind.WEEK:
        return sorted({start.replace(day=1), period_end(kind, start).replace(day=1)})
    return []


def shift(kind, start: date, n: int) -> date:
    kind = PeriodKind(kind)
    start = period_start(kind, start)
    if kind is PeriodKind.DAY:
        return start + timedelta(days=n)
    if kind is PeriodKind.WEEK:
        return start + timedelta(weeks=n)
    months = start.year * 12 + (start.month - 1) + n
    return date(months // 12, months % 12 + 1, 1)


def label(kind, start: date) -> str:
    kind = PeriodKind(kind)
    start = period_start(kind, start)
    if kind is PeriodKind.DAY:
        return f"{start:%a %d %b %Y}"
    if kind is PeriodKind.WEEK:
        end = period_end(kind, start)
        return f"Week {start:%a %d %b} - {end:%a %d %b %Y}"
    return f"{start:%B %Y}"


def short_label(kind, start: date) -> str:
    kind = PeriodKind(kind)
    start = period_start(kind, start)
    if kind is PeriodKind.DAY:
        return f"{start:%a %d %b}"
    if kind is PeriodKind.WEEK:
        return f"week of {start:%d %b}"
    return f"{start:%b %Y}"
