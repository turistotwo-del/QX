"""RF federal five-day-week working days for 2026–2027 only.

Grounding:
- Government decree 24.09.2025 No 1466 (transfers for 2026)
- Government decree 17.09.2026 No 1187 (transfers for 2027)
- RF Labour Code article 112 (federal non-working holidays).

Regional holidays, special industry work schedules, legal contract start/expiry
wording, and extraordinary amendments are NOT encoded. Never silently guess
future years; the caller must show a caution for uncovered dates.
"""
from __future__ import annotations
from datetime import date, timedelta

SUPPORTED_YEARS = frozenset((2026, 2027))
SOURCE_REFERENCES = {
    2026: 'Постановление Правительства РФ от 24.09.2025 № 1466',
    2027: 'Постановление Правительства РФ от 17.09.2026 № 1187',
}

# Actual non-working days other than usual Saturday/Sunday.
EXTRA_DAYS_OFF = {
    2026: {
        date(2026,1,9),  # Jan 3 Sat -> Jan 9 Fri
        date(2026,3,9),  # Mar 8 Sun -> Mar 9 Mon
        date(2026,5,11), # May 9 Sat -> May 11 Mon
        date(2026,12,31), # Jan 4 Sun -> Dec 31 Thu
    },
    2027: {
        date(2027,2,22), # Feb 20 Sat -> Feb 22 Mon
        date(2027,5,3),  # May 1 Sat -> May 3 Mon
        date(2027,5,10), # May 9 Sun -> May 10 Mon
        date(2027,6,14), # Jun 12 Sat -> Jun 14 Mon
        date(2027,11,5), # Jan 2 Sat -> Nov 5 Fri
        date(2027,12,31),# Jan 3 Sun -> Dec 31 Fri
    }
}
EXTRA_WORK_DAYS = {
    2026: set(),
    2027: {date(2027,2,20)},  # transferred Saturday becomes working
}


def is_working_day(day: date) -> bool:
    if day.year not in SUPPORTED_YEARS:
        raise ValueError('Производственный календарь за этот год ещё не подтверждён')
    if day in EXTRA_WORK_DAYS[day.year]:
        return True
    if day.weekday()>=5 or day in EXTRA_DAYS_OFF[day.year]:
        return False
    if ((day.month==1 and day.day<=8) or
        (day.month,day.day) in {(2,23),(3,8),(5,1),(5,9),(6,12),(11,4)}):
        return False
    return True


def add_workdays(start: date, count: int) -> date:
    """Count starting from the day AFTER start (common contract formulation)."""
    if not 0<=count<=36500:
        raise ValueError('Недопустимое число рабочих дней')
    day=start
    for _ in range(count):
        # Worst-case check dates only while traversing, no silent 2028 fallback.
        day+=timedelta(days=1)
        while not is_working_day(day):
            day+=timedelta(days=1)
    return day
