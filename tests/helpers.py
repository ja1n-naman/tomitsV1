"""Shared dates. Sep 2026: the week Sun 27 Sep - Sat 3 Oct spans two months."""

from datetime import date

from tomits import tracking as tr
from tomits.periods import PeriodKind

DAY, WEEK, MONTH = PeriodKind.DAY, PeriodKind.WEEK, PeriodKind.MONTH

SUN_27_SEP = date(2026, 9, 27)
MON_28_SEP = date(2026, 9, 28)
TUE_29_SEP = date(2026, 9, 29)
WED_30_SEP = date(2026, 9, 30)
THU_1_OCT = date(2026, 10, 1)
FRI_2_OCT = date(2026, 10, 2)
SAT_3_OCT = date(2026, 10, 3)
SUN_4_OCT = date(2026, 10, 4)
MON_5_OCT = date(2026, 10, 5)
SEP, OCT = date(2026, 9, 1), date(2026, 10, 1)


def reading_chain(s, today=SUN_27_SEP, month=SEP, day=SUN_27_SEP):
    """month 'read 500 pages' <- week 'read 110 pages' <- day 'read 10 pages'."""
    m = tr.create_goal(s, MONTH, month, "read 500 pages", 500, "pages", today=today)
    w = tr.create_goal(s, WEEK, SUN_27_SEP, "read 110 pages", 110, "pages", parent_id=m.id, today=today)
    d = tr.create_goal(s, DAY, day, "read 10 pages", 10, "pages", parent_id=w.id, today=today)
    return m, w, d
