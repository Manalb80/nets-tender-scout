"""Closing date parsing. Portals publish Pakistan local time (UTC+5, no daylight saving)."""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

PKT = timezone(timedelta(hours=5))
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_TIME = re.compile(r"(\d{1,2}):(\d{2})\s*([AaPp][Mm])?")
_REL = re.compile(r"^(?:(\d+)\s*d\s*)?(?:(\d+)\s*h\s*)?(?:(\d+)\s*m\s*)?left$", re.I)


def _time_of(text: str) -> Optional[Tuple[int, int]]:
    m = _TIME.search(text)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return (h, mi) if 0 <= h < 24 and 0 <= mi < 60 else None


def _build(y: int, mo: int, d: int, rest: str) -> Optional[Tuple[datetime, bool]]:
    if y < 100:
        y += 2000
    t = _time_of(rest)
    try:
        if t:
            return datetime(y, mo, d, t[0], t[1], tzinfo=PKT), True
        # A date with no time is open until the end of that day in Pakistan.
        return datetime(y, mo, d, 23, 59, tzinfo=PKT), False
    except ValueError:
        return None


def parse_closing(text: str, now: datetime) -> Tuple[Optional[datetime], str]:
    """Returns (closing datetime in PKT or None, kind).

    kind is one of: "datetime", "date", "relative", "missing", "unreadable".
    `now` must be timezone-aware; it is only used for relative values ("4h 8m Left").
    """
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return None, "missing"
    rel = _REL.match(s)
    if rel and any(rel.groups()):
        delta = timedelta(days=int(rel.group(1) or 0), hours=int(rel.group(2) or 0), minutes=int(rel.group(3) or 0))
        return (now + delta).astimezone(PKT).replace(second=0, microsecond=0), "relative"
    s = re.sub(r"^(mon|tues|wednes|thurs|fri|satur|sun)day,?\s*", "", s, flags=re.I)
    out = None
    m = re.match(r"(\d{1,2})\s*[-/ ]\s*([A-Za-z]{3,9})\.?\s*[-/ ,]\s*(\d{2,4})(.*)$", s)   # 08-Dec-26, 30-Sept-2024
    if m and m.group(2)[:3].lower() in _MONTHS:
        out = _build(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)), m.group(4))
    if out is None:
        m = re.match(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})(.*)$", s)                  # Dec 22, 2026 11:00 AM
        if m and m.group(1)[:3].lower() in _MONTHS:
            out = _build(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)), m.group(4))
    if out is None:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})(.*)$", s)                                     # 2026-11-25[T11:00]
        if m:
            out = _build(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4))
    if out is None:
        m = re.match(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})(.*)$", s)                           # 25/11/2026 (day first)
        if m:
            out = _build(int(m.group(3)), int(m.group(2)), int(m.group(1)), m.group(4))
    if out is None:
        return None, "unreadable"
    return out[0], "datetime" if out[1] else "date"


def days_left(closing: datetime, now: datetime) -> int:
    """Whole calendar days in Pakistan between today and the closing day (0 = closes today)."""
    return (closing.astimezone(PKT).date() - now.astimezone(PKT).date()).days
