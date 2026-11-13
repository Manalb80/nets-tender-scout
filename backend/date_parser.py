"""
Robust portal date parsing for Agent 1a (Scout).

Handles every date format seen across Sindh Bank, PPRA EPMS, and EPADS portals,
plus edge cases that previously caused pipeline lockouts:
  - Standard: "5-Nov-26", "22-Oct-2026", "2026-11-25"
  - PPRA concatenated: "Nov 25, 202611:00 AM"
  - Relative: "Closing in 5 days", "16h 8m Left", "2 days remaining"
  - Localized: "25/11/2026", "25.11.2026"
  - Missing year: "5-Nov", "Nov 25"
  - ISO: "2026-11-25T14:00:00Z"

If parsing completely fails, returns a default (now + 7 days) and sets
date_parse_warning=True so the record is flagged without crashing the pipeline.

Usage:
    from backend.date_parser import parse_portal_date
    result = parse_portal_date("5-Nov-26")
    # result = {"date": datetime(2026, 11, 5), "warning": False, "source": "regex_dmy"}
"""

import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("date_parser")

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

DEFAULT_DELTA_DAYS = 7


def _fix_year(yr: int) -> int:
    """Convert 2-digit years: 0-49 -> 2000s, 50-99 -> 1900s."""
    if yr < 100:
        return yr + 2000 if yr < 50 else yr + 1900
    return yr


def _infer_year(month: int) -> int:
    """When no year is given, pick the next occurrence of that month."""
    now = datetime.now(timezone.utc)
    if month >= now.month:
        return now.year
    return now.year + 1


def _parse_relative(s: str) -> Optional[datetime]:
    """Parse relative date strings like 'Closing in 5 days', '16h 8m Left'."""
    s_lower = s.lower().strip()

    # "Closing in N days" / "N days remaining" / "N days left"
    m = re.search(r'(\d+)\s*days?\s*(remaining|left|to\s*go)?', s_lower)
    if m:
        return datetime.now(timezone.utc) + timedelta(days=int(m.group(1)))

    # "Nh Nm Left" / "16h 8m"
    m = re.search(r'(\d+)\s*h(?:ours?)?\s*(\d+)\s*m(?:in(?:utes?)?)?', s_lower)
    if m:
        hours, mins = int(m.group(1)), int(m.group(2))
        return datetime.now(timezone.utc) + timedelta(hours=hours, minutes=mins)

    # "in N hours"
    m = re.search(r'in\s+(\d+)\s*hours?', s_lower)
    if m:
        return datetime.now(timezone.utc) + timedelta(hours=int(m.group(1)))

    # "closing tomorrow"
    if "tomorrow" in s_lower:
        return datetime.now(timezone.utc) + timedelta(days=1)

    # "closing today"
    if "today" in s_lower:
        return datetime.now(timezone.utc)

    return None


def parse_portal_date(date_string: str) -> dict:
    """
    Parse a portal closing date string into a UTC datetime.

    Returns:
        {
            "date": datetime | None,
            "warning": bool,         # True if fallback was used
            "source": str,           # which parser succeeded
            "original": str,         # the input string
        }
    """
    if not date_string or not date_string.strip():
        return {"date": None, "warning": True, "source": "empty", "original": ""}

    s = date_string.strip()
    # Strip a leading weekday ("Thursday, November 19, 2026 11:00 AM" - EPADS format)
    s = re.sub(r'(?i)^(mon|tues|wednes|thurs|fri|satur|sun)day,?\s*', '', s)
    result = {"date": None, "warning": False, "source": "none", "original": s}

    # ── 1. Relative dates ("Closing in 5 days", "16h 8m Left") ──
    rel = _parse_relative(s)
    if rel:
        result["date"] = rel.replace(tzinfo=timezone.utc)
        result["source"] = "relative"
        return result

    # ── 2. ISO 8601 ("2026-11-25T14:00:00Z" or "2026-11-25") ──
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        try:
            result["date"] = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
            result["source"] = "iso"
            return result
        except ValueError:
            pass

    # ── 3. "5-Nov-26" or "22-Oct-2026" (DMY with month name) ──
    m = re.match(r'(\d{1,2})\s*[-/]\s*([A-Za-z]{3,})\s*[-/]?\s*(\d{2,4})', s)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower()[:3])
        if mon:
            yr = _fix_year(int(m.group(3)))
            try:
                result["date"] = datetime(yr, mon, int(m.group(1)), tzinfo=timezone.utc)
                result["source"] = "regex_dmy"
                return result
            except ValueError:
                pass

    # ── 4. "Nov 25, 2026" or "Nov 25, 202611:00 AM" (PPRA concatenated) ──
    cleaned = re.sub(r'(\d{4})\d{1,2}:\d{2}\s*(AM|PM)', r'\1', s)
    m = re.match(r'([A-Za-z]{3,})\s+(\d{1,2}),?\s+(\d{4})', cleaned)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower()[:3])
        if mon:
            try:
                result["date"] = datetime(int(m.group(3)), mon, int(m.group(2)), tzinfo=timezone.utc)
                result["source"] = "regex_mdy"
                return result
            except ValueError:
                pass

    # ── 5. "25/11/2026" or "25.11.2026" (European DMY numeric) ──
    m = re.match(r'(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})', s)
    if m:
        try:
            result["date"] = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc)
            result["source"] = "regex_dmy_numeric"
            return result
        except ValueError:
            pass

    # ── 6. "11/25/2026" (American MDY, month <= 12 and day > 12 heuristic) ──
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        a, b, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a <= 12 and b > 12:
            try:
                result["date"] = datetime(yr, a, b, tzinfo=timezone.utc)
                result["source"] = "regex_mdy_numeric"
                return result
            except ValueError:
                pass

    # ── 7. Missing year: "5-Nov" or "Nov 25" ──
    m = re.match(r'(\d{1,2})\s*[-/]\s*([A-Za-z]{3,})$', s)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower()[:3])
        if mon:
            yr = _infer_year(mon)
            try:
                result["date"] = datetime(yr, mon, int(m.group(1)), tzinfo=timezone.utc)
                result["source"] = "regex_dm_no_year"
                result["warning"] = True  # year was inferred
                return result
            except ValueError:
                pass

    m = re.match(r'([A-Za-z]{3,})\s+(\d{1,2})$', s)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower()[:3])
        if mon:
            yr = _infer_year(mon)
            try:
                result["date"] = datetime(yr, mon, int(m.group(2)), tzinfo=timezone.utc)
                result["source"] = "regex_md_no_year"
                result["warning"] = True
                return result
            except ValueError:
                pass

    # ── 8. dateutil fuzzy parse (catches most remaining formats) ──
    try:
        from dateutil.parser import parse as du_parse
        dt = du_parse(s, fuzzy=True, dayfirst=True)
        result["date"] = dt.replace(tzinfo=timezone.utc)
        result["source"] = "dateutil_fuzzy"
        return result
    except (ImportError, ValueError, OverflowError):
        pass

    # ── 9. Last resort: default delta ──
    logger.warning(f"Date parse failed for '{s}'; using default +{DEFAULT_DELTA_DAYS} days")
    result["date"] = datetime.now(timezone.utc) + timedelta(days=DEFAULT_DELTA_DAYS)
    result["warning"] = True
    result["source"] = "default_delta"
    return result


# ---------------------------------------------------------------------------
# Drop-in replacement for the old parse_closing_date used by downloader.py
# ---------------------------------------------------------------------------
def parse_closing_date(date_str: str) -> Optional[datetime]:
    """
    Backward-compatible wrapper: returns a datetime or None.
    This replaces the old parse_closing_date() in downloader.py.
    """
    r = parse_portal_date(date_str)
    return r["date"]


# ---------------------------------------------------------------------------
# Tests (run with: python -m backend.date_parser)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_cases = [
        ("5-Nov-26", True),
        ("22-Oct-2026", True),
        ("Nov 25, 2026", True),
        ("Nov 25, 202611:00 AM", True),  # PPRA concatenated
        ("Thursday, November 19, 2026 11:00 AM", True),  # EPADS weekday-prefixed
        ("2026-11-25", True),
        ("2026-11-25T14:00:00Z", True),
        ("25/11/2026", True),
        ("25.11.2026", True),
        ("Closing in 5 days", True),
        ("16h 8m Left", True),
        ("2 days remaining", True),
        ("5-Nov", True),
        ("Nov 25", True),
        ("closing tomorrow", True),
        ("closing today", True),
        ("", False),              # empty -> None
        ("gobbledygook", True),   # unparseable -> default delta with warning
    ]

    passed = 0
    for input_str, expect_date in test_cases:
        r = parse_portal_date(input_str)
        ok = (r["date"] is not None) == expect_date
        status = "PASS" if ok else "FAIL"
        warn = " [WARNING]" if r["warning"] else ""
        print(f"  {status}: '{input_str}' -> {r['date']} via {r['source']}{warn}")
        if ok:
            passed += 1

    print(f"\n{passed}/{len(test_cases)} tests passed")
