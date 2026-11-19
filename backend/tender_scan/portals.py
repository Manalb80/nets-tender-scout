"""Fetching. Every portal returns the same shape, including whether the whole listing was read:
    {"source", "rows", "pages", "complete", "error", "reported_total"}
`complete` is what allows the engine to conclude that a missing tender has left the portal."""
import time
from typing import Callable, Dict, Optional

from . import parsers

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
HttpGet = Callable[[str], Optional[str]]


def requests_get(timeout: int = 60, retries: int = 3, pause: float = 3.0) -> HttpGet:
    """Direct HTTPS only. No third-party relay or cache services: their content cannot be trusted
    and they would see every request."""
    import requests
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                            "Accept-Language": "en-US,en;q=0.5"})

    def get(url: str) -> Optional[str]:
        for attempt in range(retries):
            try:
                r = session.get(url, timeout=timeout)
                if r.status_code == 200 and len(r.text) > 500:
                    return r.text
            except Exception:
                pass
            if attempt + 1 < retries:
                time.sleep(pause * (attempt + 1))
        return None
    return get


def _result(source, rows, pages, complete, error=None, reported_total=None) -> Dict:
    return {"source": source, "rows": rows, "pages": pages, "complete": bool(complete),
            "error": error, "reported_total": reported_total}


def fetch_sindh(get: HttpGet) -> Dict:
    html = get(parsers.SINDH_URL)
    if html is None:
        return _result("Sindh Bank", [], 0, False, "portal did not respond")
    rows = parsers.parse_sindh(html)
    if not rows:
        return _result("Sindh Bank", [], 1, False, "page loaded but no tender table was found")
    return _result("Sindh Bank", rows, 1, True)


def _paged(source, url_for, parse, get: HttpGet, max_pages: int, delay: float, total_of=None) -> Dict:
    rows, seen, pages, reported, error, reached_end = [], set(), 0, None, None, False
    for page in range(1, max_pages + 1):
        html = get(url_for(page))
        if html is None:
            error = "page %d did not respond" % page
            break
        if total_of and reported is None:
            reported = total_of(html)
        got = parse(html)
        fresh = [r for r in got if r["raw_id"] not in seen]
        pages = page
        if not fresh:                      # an empty page, or a page that repeats the last one: the end
            reached_end = True
            break
        for r in fresh:
            seen.add(r["raw_id"])
        rows.extend(fresh)
        if reported is not None and len(rows) >= reported:
            reached_end = True
            break
        if delay:
            time.sleep(delay)
    else:
        error = "stopped at the %d page safety limit" % max_pages
    complete = reached_end and error is None and bool(rows)
    if complete and reported is not None and len(rows) < 0.98 * reported:
        complete, error = False, "portal reports %d tenders but only %d were read" % (reported, len(rows))
    return _result(source, rows, pages, complete, error, reported)


def fetch_ppra(get: HttpGet, max_pages: int = 120, delay: float = 1.0) -> Dict:
    return _paged("PPRA", lambda p: "%s?page=%d" % (parsers.PPRA_URL, p), parsers.parse_ppra, get, max_pages, delay,
                  total_of=parsers.ppra_total)


def fetch_epads(get: HttpGet, max_pages: int = 120, delay: float = 1.0) -> Dict:
    return _paged("EPADS", lambda p: "%s/?page=%d" % (parsers.EPADS_BASE, p), parsers.parse_epads, get, max_pages, delay)


def fetch_all(get: HttpGet, max_pages: int = 120, delay: float = 1.0) -> Dict[str, Dict]:
    return {"Sindh Bank": fetch_sindh(get), "PPRA": fetch_ppra(get, max_pages, delay),
            "EPADS": fetch_epads(get, max_pages, delay)}
