from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# NYSE full-day holidays. Update this list once a year — early-close days
# (day after Thanksgiving, Dec 24, Jul 3 when not itself the observed holiday)
# are not modeled; the market is treated as fully open on those days.
NYSE_HOLIDAYS_2026 = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # Martin Luther King Jr. Day
    "2026-02-16",  # Washington's Birthday
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed — Jul 4 falls on a Saturday)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving Day
    "2026-12-25",  # Christmas Day
}


def is_holiday(now_et: datetime) -> bool:
    return now_et.strftime("%Y-%m-%d") in NYSE_HOLIDAYS_2026


def is_market_open(now_et: datetime | None = None) -> bool:
    now_et = now_et or datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    if is_holiday(now_et):
        return False
    open_time  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_time = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_time <= now_et <= close_time


def hours_to_market_open(now_et: datetime | None = None) -> float:
    now_et = now_et or datetime.now(ZoneInfo("America/New_York"))
    if is_market_open(now_et):
        return 0.0
    candidate = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    if now_et >= candidate or now_et.weekday() >= 5 or is_holiday(now_et):
        candidate += timedelta(days=1)
        while candidate.weekday() >= 5 or is_holiday(candidate):
            candidate += timedelta(days=1)
    return round((candidate - now_et).total_seconds() / 3600, 2)
