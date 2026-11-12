"""
EPADS (e-Pak Acquisition and Disposal System) Scraper.
Portal: https://epads.gov.pk/
Covers Federal PPRA, KPPRA, and GBPPRA procurement tenders.

Table structure (5 columns per row):
  TD[0]: Row number
  TD[1]: Title + Department + Reference ID (P######), with link to detail page
  TD[2]: Published On + Closing On (absolute date or relative time like "16h 8m Left")
  TD[3]: Procurement Type + Procedure
  TD[4]: View button (link to detail page)

Pagination: ?page=N, 100 tenders per page.
Direct HTTPS access works from cloud (no WAF blocking).
"""
import re
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("scraper_epads")

EPADS_BASE = "https://epads.gov.pk"
EPADS_LIST_URL = f"{EPADS_BASE}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_epads_date(date_str: str) -> Optional[datetime]:
    """
    Parse EPADS date formats:
      "Monday, October 26, 2026 04:56 PM"  (absolute)
      "16h 8m Left"                        (relative, convert to approximate datetime)
      "Friday, November 13, 2026 11:00 AM" (absolute)
    """
    if not date_str:
        return None
    s = date_str.strip()

    # Relative time: "16h 8m Left", "2d 5h Left", "3h Left"
    rel = re.match(r'(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?Left', s)
    if rel:
        days = int(rel.group(1) or 0)
        hours = int(rel.group(2) or 0)
        minutes = int(rel.group(3) or 0)
        return datetime.now(timezone.utc) + timedelta(days=days, hours=hours, minutes=minutes)

    # Absolute: "Monday, October 26, 2026 04:56 PM"
    m = re.match(
        r'(?:\w+,\s*)?(\w+)\s+(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*(AM|PM)',
        s, re.IGNORECASE
    )
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            hour = int(m.group(4))
            if m.group(6).upper() == "PM" and hour < 12:
                hour += 12
            elif m.group(6).upper() == "AM" and hour == 12:
                hour = 0
            try:
                return datetime(
                    int(m.group(3)), mon, int(m.group(2)),
                    hour, int(m.group(5)),
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

    # Fallback: "November 13, 2026"
    m = re.match(r'(?:\w+,\s*)?(\w+)\s+(\d{1,2}),?\s+(\d{4})', s)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            try:
                return datetime(int(m.group(3)), mon, int(m.group(2)), tzinfo=timezone.utc)
            except ValueError:
                pass

    return None


def parse_epads_row(tr) -> Optional[Dict]:
    """Parse a single <tr> row from the EPADS table into a tender dict."""
    tds = tr.find_all("td")
    if len(tds) < 4:
        return None

    # TD[1]: Title + Department + Reference ID
    td1 = tds[1]
    link = td1.find("a", href=True)
    if not link:
        return None

    href = link["href"]  # /opportunities/federal/procurements/158997
    title = link.get_text(strip=True)

    # Extract reference ID (P######)
    td1_text = td1.get_text("|", strip=True)
    ref_match = re.search(r'(P\d{4,})', td1_text)
    ref_id = ref_match.group(1) if ref_match else ""

    # Extract department (text between title and reference)
    dept = ""
    parts = td1_text.split("|")
    if len(parts) >= 2:
        dept = parts[1].strip()
        # Clean up parenthetical duplication
        dept = re.sub(r'\s*\([^)]*\)\s*$', '', dept).strip()

    # Build unique ID
    tender_id = f"EPADS-{ref_id}" if ref_id else f"EPADS-{href.split('/')[-1]}"

    # TD[2]: Published On + Closing On
    td2_text = tds[2].get_text("|", strip=True)

    published = ""
    closing = ""
    closing_date = None

    pub_match = re.search(r'Published On:\|?(.+?)(?:\|Closing|\|$|$)', td2_text)
    if pub_match:
        published = pub_match.group(1).strip()

    close_match = re.search(r'Closing On:\|?(.+?)(?:\||$)', td2_text)
    if close_match:
        closing = close_match.group(1).strip()
        closing_date = parse_epads_date(closing)

    # TD[3]: Type + Procedure
    td3_text = tds[3].get_text("|", strip=True)
    proc_type = ""
    procedure = ""
    td3_parts = td3_text.split("|")
    if len(td3_parts) >= 1:
        proc_type = td3_parts[0].strip()
    if len(td3_parts) >= 2:
        procedure = td3_parts[1].strip()

    # Status badges (Under Corrigendum, Grievance Raised, etc.)
    status_badges = []
    for badge in td1.find_all("span", class_=re.compile(r"badge")):
        badge_text = badge.get_text(strip=True)
        if badge_text and badge_text not in (ref_id, title):
            status_badges.append(badge_text)

    # Detail URL
    detail_url = urljoin(EPADS_BASE, href)

    return {
        "id": tender_id,
        "title": title,
        "department": dept,
        "advertised": published,
        "closing": closing,
        "closing_date": closing_date,
        "doc_url": "",  # EPADS documents are on the detail page
        "source": "EPADS",
        "detail_url": detail_url,
        "reference": ref_id,
        "procurement_type": proc_type,
        "procedure": procedure,
        "status_badges": status_badges,
    }


def scrape_epads(max_pages: int = 5) -> List[Dict]:
    """
    Scrape open procurement tenders from EPADS.
    Returns list of tender dicts in the standard schema.
    """
    all_tenders = []
    seen_ids = set()

    print("=" * 50)
    print("EPADS SCRAPER")
    print("=" * 50)

    for page in range(1, max_pages + 1):
        url = f"{EPADS_LIST_URL}?page={page}"
        print(f"  Page {page}: {url}")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code}, stopping")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", class_="table-cb")
            if not table:
                print("    No table found, stopping")
                break

            tbody = table.find("tbody")
            rows = tbody.find_all("tr") if tbody else []

            page_count = 0
            for tr in rows:
                tender = parse_epads_row(tr)
                if tender and tender["id"] not in seen_ids:
                    seen_ids.add(tender["id"])
                    all_tenders.append(tender)
                    page_count += 1

            print(f"    Parsed {page_count} tenders")

            if page_count == 0:
                print("    Empty page, stopping")
                break

            # Polite delay
            if page < max_pages:
                time.sleep(1)

        except Exception as e:
            print(f"    Error: {e}")
            break

    print(f"EPADS: {len(all_tenders)} unique tenders across {min(page, max_pages)} pages")
    return all_tenders


def fetch_epads_detail(detail_url: str) -> Dict:
    """
    Fetch an EPADS tender detail page and extract document links.
    Returns dict with documents, metadata, and accessibility info.
    """
    documents = []
    metadata = {}
    accessible = True

    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return {"documents": [], "metadata": {}, "accessible": resp.status_code != 403}

        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for downloadable document links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)

            # Common download patterns on EPADS
            if any(ext in href.lower() for ext in [".pdf", ".doc", ".docx", ".xlsx", "/download", "/file"]):
                full_url = urljoin(EPADS_BASE, href)
                doc_type = "rfp"
                if "corrigendum" in text.lower():
                    doc_type = "corrigendum"
                elif "addendum" in text.lower():
                    doc_type = "addendum"
                elif "advertisement" in text.lower() or "notice" in text.lower():
                    doc_type = "advertisement"

                documents.append({
                    "label": text or "Document",
                    "url": full_url,
                    "filename": href.split("/")[-1] or "document.pdf",
                    "type": doc_type,
                })

        # Check for login wall
        login_indicators = soup.find_all(
            string=re.compile(r'(login|sign.?in|password|authenticate)', re.I)
        )
        if login_indicators and not documents:
            accessible = False

    except Exception as e:
        logger.error(f"EPADS detail fetch error: {e}")
        accessible = False

    return {
        "documents": documents,
        "metadata": metadata,
        "accessible": accessible,
    }


if __name__ == "__main__":
    tenders = scrape_epads(max_pages=3)
    print(f"\nTotal: {len(tenders)}")

    # Show first 5
    for t in tenders[:5]:
        print(f"  {t['id']}: {t['title'][:60]}")
        print(f"    Dept: {t['department'][:40]}, Closing: {t['closing']}")
        print(f"    Type: {t['procurement_type']}, Status: {t.get('status_badges', [])}")
