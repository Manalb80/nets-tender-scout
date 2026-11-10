"""
PPRA EPMS Portal Scraper (epms.ppra.gov.pk).
Scrapes active tenders from Pakistan's Public Procurement Regulatory Authority.
Uses Playwright for dynamic page rendering, with requests + BeautifulSoup fallback.

The EPMS active tenders page is paginated (50 per page) and may use dynamic rendering.
Detail pages follow: /public/tenders/tender-details/{tenderNumber}
Document links follow: https://epms.ppra.gov.pk/pdf?file=<base64>

Run standalone:  python scraper_ppra.py
"""
import re
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlencode, quote

logger = logging.getLogger("scraper-ppra")

PPRA_BASE = "https://epms.ppra.gov.pk"
PPRA_ACTIVE_URL = f"{PPRA_BASE}/public/tenders/active-tenders"
PPRA_HISTORY_URL = f"{PPRA_BASE}/public/tenders/tenders-history"

# Date formats seen on PPRA: "25-Nov-2026", "2026-11-25", "Nov 25, 2026"
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
}


def parse_ppra_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats from the PPRA portal."""
    if not date_str:
        return None
    date_str = date_str.strip()

    # "25-Nov-2026" or "5-Nov-26"
    m = re.match(r'(\d{1,2})-([A-Za-z]{3,})-(\d{2,4})', date_str)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower()[:3])
        yr = int(m.group(3))
        if yr < 100:
            yr += 2000
        if mon:
            try:
                return datetime(yr, mon, int(m.group(1)))
            except ValueError:
                pass

    # "2026-11-25" or "2026-11-25T..."
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # "Nov 25, 2026"
    m = re.match(r'([A-Za-z]{3,})\s+(\d{1,2}),?\s+(\d{4})', date_str)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower()[:3])
        if mon:
            try:
                return datetime(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                pass

    # "25/11/2026"
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    return None


async def scrape_ppra_playwright(
    max_pages: int = 20,
    include_history: bool = False,
    keyword_filter: Optional[str] = None,
) -> Dict:
    """
    Scrape active (and optionally historical) tenders from PPRA EPMS using Playwright.

    Returns a dict with:
        tenders: List of tender dicts
        execution_report: status, counts, errors
    """
    from playwright.async_api import async_playwright

    scan_start = datetime.utcnow()
    all_tenders = []
    report = {
        "agent": "Agent 1: PPRA Scraper",
        "timestamp": scan_start.isoformat() + "Z",
        "portal": "PPRA EPMS",
        "target_urls": [],
        "status": "PENDING",
        "pages_scraped": 0,
        "total_scraped": 0,
        "error_message": None,
    }

    urls_to_scrape = [PPRA_ACTIVE_URL]
    if include_history:
        urls_to_scrape.append(PPRA_HISTORY_URL)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )

        try:
            for base_url in urls_to_scrape:
                page_num = 1
                consecutive_empty = 0

                while page_num <= max_pages:
                    url = f"{base_url}?page={page_num}"
                    if keyword_filter:
                        url += f"&keyword={quote(keyword_filter)}"

                    report["target_urls"].append(url)
                    logger.info(f"Scraping PPRA page {page_num}: {url}")

                    page = await context.new_page()
                    try:
                        response = await page.goto(url, timeout=45000, wait_until="networkidle")

                        if not response or response.status != 200:
                            status_code = response.status if response else "no response"
                            logger.warning(f"PPRA returned {status_code} on page {page_num}")
                            await page.close()
                            break

                        # Wait for tender content to render
                        try:
                            await page.wait_for_selector(
                                "table, .tender-card, .card, .list-group-item, [class*='tender']",
                                timeout=15000
                            )
                        except Exception:
                            logger.info(f"No tender elements found on page {page_num}, may be end of results")
                            await page.close()
                            break

                        # Extract tenders from the PPRA EPMS page
                        # Table columns: [checkbox, Sr, Tender No, Tender Details, Status, Advertised, Closing, Actions]
                        page_tenders = await page.evaluate("""() => {
                            const results = [];
                            const rows = document.querySelectorAll('table tbody tr, table tr');

                            rows.forEach(row => {
                                const cells = row.querySelectorAll('td');
                                if (cells.length < 6) return;

                                const texts = Array.from(cells).map(c => c.innerText.trim());

                                // Tender number and detail link from column 2
                                let tenderNumber = '';
                                let detailLink = '';
                                const tenderNoCell = cells[2];
                                if (tenderNoCell) {
                                    const link = tenderNoCell.querySelector('a[href]');
                                    if (link) {
                                        detailLink = link.href || '';
                                        const match = detailLink.match(/tender-details\\/([^/?]+)/);
                                        if (match) tenderNumber = match[1];
                                    }
                                    if (!tenderNumber) tenderNumber = tenderNoCell.innerText.trim();
                                }

                                // Doc/PDF links from Actions column (last cell)
                                let docLink = '';
                                const actionsCell = cells[cells.length - 1];
                                if (actionsCell) {
                                    actionsCell.querySelectorAll('a[href]').forEach(a => {
                                        const href = a.href || '';
                                        if (href.includes('/pdf?') || href.includes('.pdf')) {
                                            docLink = href;
                                        }
                                    });
                                }

                                // Map columns: [0:checkbox, 1:Sr, 2:TenderNo, 3:Details, 4:Status, 5:Advertised, 6:Closing, 7:Actions]
                                const title = texts[3] || '';
                                const status = texts[4] || '';
                                let advertised = texts[5] || '';
                                let closing = texts[6] || '';

                                // Clean closing date: "Dec 22, 202611:00 AM" -> "Dec 22, 2026"
                                closing = closing.replace(/(\\d{4})\\d{1,2}:\\d{2}\\s*(AM|PM)/i, '$1');

                                if (title && title.length > 3) {
                                    results.push({
                                        tender_number: tenderNumber,
                                        title: title,
                                        organization: '',
                                        department: '',
                                        sector: '',
                                        status: status,
                                        advertised: advertised,
                                        closing: closing,
                                        doc_url: docLink,
                                        detail_url: detailLink,
                                        raw_texts: texts
                                    });
                                }
                            });

                            return results;
                        }""")

                        if not page_tenders:
                            consecutive_empty += 1
                            if consecutive_empty >= 2:
                                logger.info(f"Two consecutive empty pages at page {page_num}, stopping.")
                                await page.close()
                                break
                        else:
                            consecutive_empty = 0
                            all_tenders.extend(page_tenders)
                            report["pages_scraped"] += 1

                        logger.info(f"  Page {page_num}: {len(page_tenders)} tenders")

                    except Exception as e:
                        logger.error(f"Error on PPRA page {page_num}: {e}")
                        report["error_message"] = str(e)
                    finally:
                        await page.close()

                    page_num += 1
                    # Polite delay: 2 seconds between requests
                    await asyncio.sleep(2)

        except Exception as e:
            report["status"] = "FAILED"
            report["error_message"] = str(e)
            logger.error(f"PPRA scraping failed: {e}")
        finally:
            await browser.close()

    # Deduplicate by tender_number or title
    seen = set()
    unique_tenders = []
    for t in all_tenders:
        key = t.get("tender_number") or t.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique_tenders.append(t)

    report["total_scraped"] = len(unique_tenders)
    if report["status"] == "PENDING":
        report["status"] = "SUCCESS" if unique_tenders else "NO_DATA"
    report["duration_seconds"] = (datetime.utcnow() - scan_start).total_seconds()

    return {"tenders": unique_tenders, "execution_report": report}


def scrape_ppra_requests(max_pages: int = 5) -> Dict:
    """
    Fallback PPRA scraper using requests + BeautifulSoup.
    For environments without Playwright (e.g. GitHub Actions).
    Uses the same multi-strategy approach as the Sindh Bank scraper.
    """
    import requests
    from bs4 import BeautifulSoup

    scan_start = datetime.utcnow()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    report = {
        "agent": "Agent 1: PPRA Scraper (requests)",
        "timestamp": scan_start.isoformat() + "Z",
        "portal": "PPRA EPMS",
        "status": "PENDING",
        "pages_scraped": 0,
        "total_scraped": 0,
        "error_message": None,
    }

    all_tenders = []
    strategies = [
        ("direct", lambda url: url),
        ("allorigins", lambda url: f"https://api.allorigins.win/raw?url={quote(url)}"),
        ("corsproxy", lambda url: f"https://corsproxy.io/?{quote(url)}"),
    ]

    for page_num in range(1, max_pages + 1):
        page_url = f"{PPRA_ACTIVE_URL}?page={page_num}"
        html = None

        for strat_name, make_url in strategies:
            try:
                fetch_url = make_url(page_url)
                logger.info(f"PPRA page {page_num}, strategy: {strat_name}")
                resp = requests.get(fetch_url, headers=headers, timeout=60)
                if resp.status_code == 200 and len(resp.text) > 500:
                    html = resp.text
                    logger.info(f"  Success: {len(html)} bytes")
                    break
            except Exception as e:
                logger.warning(f"  {strat_name} failed: {e}")
                continue

        if not html:
            logger.warning(f"All strategies failed for PPRA page {page_num}")
            break

        soup = BeautifulSoup(html, "html.parser")
        page_tenders = []

        # Parse table rows
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                texts = [c.get_text(strip=True) for c in cells]

                doc_url = ""
                detail_url = ""
                for link in row.find_all("a", href=True):
                    href = link["href"]
                    if not href.startswith("http"):
                        href = urljoin(PPRA_BASE, href)
                    if "/pdf?" in href or ".pdf" in href.lower():
                        doc_url = href
                    if "tender-details" in href:
                        detail_url = href

                tender_number = ""
                if detail_url:
                    m = re.search(r'tender-details/([^/?]+)', detail_url)
                    if m:
                        tender_number = m.group(1)

                page_tenders.append({
                    "tender_number": tender_number or texts[0],
                    "title": texts[1] if len(texts) > 1 else texts[0],
                    "organization": texts[2] if len(texts) > 2 else "",
                    "department": texts[3] if len(texts) > 3 else "",
                    "sector": "",
                    "advertised": texts[4] if len(texts) > 4 else "",
                    "closing": texts[5] if len(texts) > 5 else "",
                    "doc_url": doc_url,
                    "detail_url": detail_url,
                })

        # Parse card-based layout
        if not page_tenders:
            for card in soup.find_all(class_=re.compile(r'tender|card|list-group-item')):
                title_el = card.find(re.compile(r'h[3-5]|a'))
                if title_el:
                    page_tenders.append({
                        "tender_number": "",
                        "title": title_el.get_text(strip=True),
                        "organization": "",
                        "department": "",
                        "sector": "",
                        "advertised": "",
                        "closing": "",
                        "doc_url": "",
                        "detail_url": "",
                    })

        if not page_tenders:
            break

        all_tenders.extend(page_tenders)
        report["pages_scraped"] += 1
        logger.info(f"PPRA page {page_num}: {len(page_tenders)} tenders")
        time.sleep(2)  # polite delay

    # Deduplicate
    seen = set()
    unique = []
    for t in all_tenders:
        key = t.get("tender_number") or t.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(t)

    report["total_scraped"] = len(unique)
    report["status"] = "SUCCESS" if unique else "NO_DATA"
    report["duration_seconds"] = (datetime.utcnow() - scan_start).total_seconds()

    return {"tenders": unique, "execution_report": report}


def normalize_ppra_tender(raw: Dict) -> Dict:
    """
    Normalize a PPRA tender into the same schema used by the Sindh Bank scraper,
    so the scorer and database can handle both sources identically.
    """
    tender_id = raw.get("tender_number", "") or ""
    title = raw.get("title", "") or ""

    # Clean up the tender ID: remove whitespace, truncate
    tender_id = re.sub(r'\s+', '-', tender_id.strip())[:100]
    if not tender_id:
        # Generate an ID from the title
        tender_id = "PPRA-" + re.sub(r'[^A-Za-z0-9]+', '-', title)[:80]

    return {
        "id": tender_id,
        "title": title,
        "department": raw.get("organization") or raw.get("department", ""),
        "advertised": raw.get("advertised", ""),
        "closing": raw.get("closing", ""),
        "doc_url": raw.get("doc_url", ""),
        "source": "PPRA",
        "detail_url": raw.get("detail_url", ""),
    }


# ── Async helper for import ──
import asyncio


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def main():
        try:
            result = await scrape_ppra_playwright(max_pages=3)
        except ImportError:
            logger.warning("Playwright not installed, falling back to requests")
            result = scrape_ppra_requests(max_pages=3)

        report = result["execution_report"]
        tenders = result["tenders"]

        print(f"\n{'='*60}")
        print(f"PPRA Scraper Report")
        print(f"{'='*60}")
        print(f"Status:   {report['status']}")
        print(f"Pages:    {report['pages_scraped']}")
        print(f"Tenders:  {report['total_scraped']}")
        if report.get("error_message"):
            print(f"Error:    {report['error_message']}")
        print(f"Duration: {report.get('duration_seconds', 0):.1f}s")
        print()

        for t in tenders[:5]:
            norm = normalize_ppra_tender(t)
            print(f"  [{norm['id']}] {norm['title'][:80]}")
            if norm.get("closing"):
                print(f"    Closing: {norm['closing']}")

        if len(tenders) > 5:
            print(f"  ... and {len(tenders) - 5} more")

    asyncio.run(main())
