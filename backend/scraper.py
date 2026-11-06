"""
Sindh Bank Portal Scraper.
Uses Playwright (headless Chromium) to scrape sindhbank.com.pk/tenders.
Falls back to requests + BeautifulSoup if Playwright is not installed.

Run standalone:  python scraper.py
Run from API:    called by the scheduler in main.py
"""
import re
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger("scraper")

# ── Date parsing for portal formats: "5-Nov-26", "22-Oct-2026", "05-Nov-2026" ──

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
}


def parse_portal_date(date_str: str) -> Optional[datetime]:
    """Parse dates like '5-Nov-26', '22-Oct-2026', '05-Nov-2026'."""
    if not date_str:
        return None
    date_str = date_str.strip()

    # Pattern: D-Mon-YY or DD-Mon-YYYY
    m = re.match(r'(\d{1,2})-([A-Za-z]{3})-(\d{2,4})', date_str)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).lower())
        year = int(m.group(3))
        if year < 100:
            year += 2000
        if month:
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

    # Pattern: DD/MM/YYYY
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    return None


def days_remaining(closing_date: Optional[datetime]) -> Optional[int]:
    """Calculate days until closing. Negative means already closed."""
    if not closing_date:
        return None
    delta = closing_date - datetime.utcnow()
    return delta.days


async def scrape_with_playwright(url: str = "https://sindhbank.com.pk/tenders") -> List[Dict]:
    """
    Scrape tenders using Playwright headless browser.
    Returns list of raw tender dicts with keys: id, title, department, advertised, closing, doc_url.
    """
    from playwright.async_api import async_playwright

    tenders = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        logger.info(f"Navigating to {url}")
        await page.goto(url, wait_until="networkidle", timeout=60000)

        # Wait for the tender table to load
        await page.wait_for_selector("table", timeout=30000)

        # Extract all rows from all tables on the page
        rows = await page.query_selector_all("table tbody tr")
        logger.info(f"Found {len(rows)} table rows")

        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 4:
                continue

            texts = []
            for cell in cells:
                text = await cell.inner_text()
                texts.append(text.strip())

            # Try to extract PDF link
            doc_url = None
            links = await row.query_selector_all("a[href]")
            for link in links:
                href = await link.get_attribute("href")
                if href and (".pdf" in href.lower() or "download" in href.lower()):
                    if not href.startswith("http"):
                        href = f"https://sindhbank.com.pk{href}"
                    doc_url = href
                    break

            # Build tender record (adapt column indices to the actual portal layout)
            tender = {
                "id": texts[0] if len(texts) > 0 else "",
                "title": texts[1] if len(texts) > 1 else "",
                "department": texts[2] if len(texts) > 2 else "",
                "advertised": texts[3] if len(texts) > 3 else "",
                "closing": texts[4] if len(texts) > 4 else "",
                "doc_url": doc_url,
            }

            # Skip empty rows
            if tender["title"] and len(tender["title"]) > 3:
                tenders.append(tender)

        await browser.close()

    logger.info(f"Scraped {len(tenders)} tenders from portal")
    return tenders


def scrape_with_requests(url: str = "https://sindhbank.com.pk/tenders") -> List[Dict]:
    """
    Fallback scraper using requests + BeautifulSoup.
    Use this if Playwright is not available in the deployment environment.
    """
    import requests
    from bs4 import BeautifulSoup

    logger.info(f"Fetching {url} with requests")
    resp = requests.get(url, timeout=30, headers={
        "User-Agent": "NETS-TenderScout/1.0"
    })
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    tenders = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            texts = [cell.get_text(strip=True) for cell in cells]

            doc_url = None
            for link in row.find_all("a", href=True):
                href = link["href"]
                if ".pdf" in href.lower() or "download" in href.lower():
                    if not href.startswith("http"):
                        href = f"https://sindhbank.com.pk{href}"
                    doc_url = href
                    break

            tender = {
                "id": texts[0] if len(texts) > 0 else "",
                "title": texts[1] if len(texts) > 1 else "",
                "department": texts[2] if len(texts) > 2 else "",
                "advertised": texts[3] if len(texts) > 3 else "",
                "closing": texts[4] if len(texts) > 4 else "",
                "doc_url": doc_url,
            }

            if tender["title"] and len(tender["title"]) > 3:
                tenders.append(tender)

    logger.info(f"Scraped {len(tenders)} tenders with requests")
    return tenders


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    async def main():
        try:
            tenders = await scrape_with_playwright()
        except ImportError:
            logger.warning("Playwright not installed, falling back to requests")
            tenders = scrape_with_requests()

        print(json.dumps(tenders[:5], indent=2))
        print(f"\nTotal: {len(tenders)} tenders")

    asyncio.run(main())
