"""
Lightweight scraper for GitHub Actions.
Scrapes BOTH Sindh Bank and PPRA EPMS portals.
Uses fallback strategies for cloud servers that get blocked.
Writes directly to Supabase PostgreSQL. No Playwright needed.
"""
import os
import sys
import re
import json
import time
from datetime import datetime
from urllib.parse import quote, urljoin

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from scorer import score_tender

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set.")
    sys.exit(1)

SINDH_PORTAL_URL = "https://sindhbank.com.pk/tenders"
PPRA_BASE = "https://epms.ppra.gov.pk"
PPRA_ACTIVE_URL = f"{PPRA_BASE}/public/tenders/active-tenders"


def fetch_with_strategies(url, headers):
    """Try multiple strategies to fetch a URL from cloud servers."""
    import requests

    strategies = [
        ("Direct", url),
        ("allorigins", f"https://api.allorigins.win/raw?url={quote(url)}"),
        ("corsproxy", f"https://corsproxy.io/?{quote(url)}"),
        ("Google cache", f"https://webcache.googleusercontent.com/search?q=cache:{url}"),
    ]

    for name, fetch_url in strategies:
        try:
            print(f"  {name}: {fetch_url[:80]}...")
            resp = requests.get(fetch_url, headers=headers, timeout=60)
            if resp.status_code == 200 and len(resp.text) > 500:
                print(f"    Success: {len(resp.text)} bytes")
                return resp.text
        except Exception as e:
            print(f"    Failed: {e}")

    return None


def parse_html_table(html, base_url, source_name):
    """Parse tender rows from an HTML page with tables."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            texts = [cell.get_text(strip=True) for cell in cells]

            doc_url = None
            detail_url = None
            for link in row.find_all("a", href=True):
                href = link["href"]
                if not href.startswith("http"):
                    href = urljoin(base_url, href)
                if ".pdf" in href.lower() or "download" in href.lower() or "/pdf?" in href:
                    doc_url = href
                if "tender-details" in href or "tender_details" in href:
                    detail_url = href

            tender = {
                "id": texts[0] if texts else "",
                "title": texts[1] if len(texts) > 1 else texts[0],
                "department": texts[2] if len(texts) > 2 else "",
                "advertised": texts[3] if len(texts) > 3 else "",
                "closing": texts[4] if len(texts) > 4 else "",
                "doc_url": doc_url,
                "source": source_name,
            }
            if tender["title"] and len(tender["title"]) > 3:
                tenders.append(tender)

    # PPRA specific: table has columns [checkbox, Sr, Tender No, Tender Details, Status, Advertised, Closing, Actions]
    # The tender number and detail link live in column 2 (index 2)
    if not tenders and "ppra" in base_url.lower():
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue
                texts = [c.get_text(strip=True) for c in cells]

                # Extract tender number and detail URL from column 2
                tender_no_cell = cells[2] if len(cells) > 2 else None
                detail_url = ""
                tender_number = ""
                if tender_no_cell:
                    link = tender_no_cell.find("a", href=True)
                    if link:
                        href = link["href"]
                        if not href.startswith("http"):
                            href = urljoin(base_url, href)
                        detail_url = href
                        m_tn = re.search(r'tender-details/([^/?]+)', href)
                        if m_tn:
                            tender_number = m_tn.group(1)
                    if not tender_number:
                        # Get ID from the <strong> tag, not the full cell text
                        strong = tender_no_cell.find("strong")
                        tender_number = strong.get_text(strip=True) if strong else tender_no_cell.get_text(strip=True)
                    # Clean trailing text: "TS0000016912EProcurement" -> "TS0000016912E"
                    m_clean = re.match(r'(TS\d+E)', tender_number)
                    if m_clean:
                        tender_number = m_clean.group(1)

                # Extract doc/invoice links from Actions column
                doc_url_val = ""
                actions_cell = cells[-1] if cells else None
                if actions_cell:
                    for link in actions_cell.find_all("a", href=True):
                        href = link["href"]
                        if not href.startswith("http"):
                            href = urljoin(base_url, href)
                        if "/pdf?" in href or ".pdf" in href.lower():
                            doc_url_val = href
                            break

                # Column mapping: [checkbox, Sr, TenderNo, Details, Status, Advertised, Closing, Actions]
                title = texts[3] if len(texts) > 3 else ""
                status = texts[4] if len(texts) > 4 else ""
                advertised = texts[5] if len(texts) > 5 else ""
                closing = texts[6] if len(texts) > 6 else ""

                # Clean closing date (may have time appended like "Dec 22, 202611:00 AM")
                closing = re.sub(r'(\d{4})\d{1,2}:\d{2}\s*(AM|PM)', r'\1', closing)

                if title and len(title) > 3:
                    tenders.append({
                        "id": tender_number or f"PPRA-{re.sub(r'[^A-Za-z0-9]+', '-', title)[:80]}",
                        "title": title,
                        "department": "",
                        "advertised": advertised,
                        "closing": closing,
                        "doc_url": doc_url_val,
                        "source": source_name,
                        "detail_url": detail_url,
                        "status": status,
                    })

    return tenders


def scrape_sindh_bank():
    """Scrape Sindh Bank tenders."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    print(f"\n{'='*50}")
    print(f"SINDH BANK SCRAPER")
    print(f"{'='*50}")

    html = fetch_with_strategies(SINDH_PORTAL_URL, headers)
    if not html:
        print("Sindh Bank: all strategies failed.")
        return []

    tenders = parse_html_table(html, "https://sindhbank.com.pk", "Sindh Bank")
    print(f"Sindh Bank: parsed {len(tenders)} tenders")
    return tenders


def scrape_ppra(max_pages=10):
    """Scrape PPRA EPMS active tenders, paginated."""
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    print(f"\n{'='*50}")
    print(f"PPRA EPMS SCRAPER")
    print(f"{'='*50}")

    all_tenders = []

    for page_num in range(1, max_pages + 1):
        page_url = f"{PPRA_ACTIVE_URL}?page={page_num}"
        print(f"\nPage {page_num}: {page_url}")

        html = fetch_with_strategies(page_url, headers)
        if not html:
            print(f"  Page {page_num}: all strategies failed, stopping.")
            break

        page_tenders = parse_html_table(html, PPRA_BASE, "PPRA")

        if not page_tenders:
            print(f"  Page {page_num}: no tenders found, may be end of results.")
            break

        # Generate proper IDs for PPRA tenders
        for t in page_tenders:
            if not t["id"] or t["id"].startswith("PPRA-"):
                pass  # already has an ID
            else:
                # Prefix PPRA IDs to avoid collision with Sindh Bank
                if not t["id"].startswith("PPRA"):
                    t["id"] = f"PPRA-{t['id']}"

        all_tenders.extend(page_tenders)
        print(f"  Page {page_num}: {len(page_tenders)} tenders")

        # Polite delay between pages
        time.sleep(2)

    # Deduplicate
    seen = set()
    unique = []
    for t in all_tenders:
        key = t["id"] or t["title"]
        if key and key not in seen:
            seen.add(key)
            unique.append(t)

    print(f"\nPPRA: {len(unique)} unique tenders across {min(page_num, max_pages)} pages")
    return unique


def scrape_tenders():
    """Scrape BOTH Sindh Bank and PPRA, return combined list."""
    sindh = scrape_sindh_bank()
    ppra = scrape_ppra()
    combined = sindh + ppra
    print(f"\nCombined: {len(sindh)} Sindh Bank + {len(ppra)} PPRA = {len(combined)} total")
    return combined


def parse_date(s):
    """Parse dates from multiple portal formats."""
    if not s:
        return None
    s = s.strip()

    months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
               "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}

    # "5-Nov-26" or "22-Oct-2026"
    m = re.match(r'(\d{1,2})-([A-Za-z]{3,})-(\d{2,4})', s)
    if m:
        mon = months.get(m.group(2).lower()[:3])
        yr = int(m.group(3))
        if yr < 100: yr += 2000
        if mon:
            try: return datetime(yr, mon, int(m.group(1)))
            except ValueError: pass

    # "2026-11-25" or "2026-11-25T..."
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        try: return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: pass

    # "Nov 25, 2026"
    m = re.match(r'([A-Za-z]{3,})\s+(\d{1,2}),?\s+(\d{4})', s)
    if m:
        mon = months.get(m.group(1).lower()[:3])
        if mon:
            try: return datetime(int(m.group(3)), mon, int(m.group(2)))
            except ValueError: pass

    # "25/11/2026"
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        try: return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError: pass

    return None


def save_to_db(tenders):
    from sqlalchemy import create_engine, text
    engine = create_engine(DATABASE_URL)
    now = datetime.utcnow()
    total = len(tenders)
    qualified = new_count = open_qual = 0

    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS tenders (
            id VARCHAR(100) PRIMARY KEY, title VARCHAR(500),
            department VARCHAR(100), advertised VARCHAR(50), closing VARCHAR(50),
            closing_date TIMESTAMP, is_open BOOLEAN DEFAULT TRUE,
            days_remaining INTEGER, score INTEGER DEFAULT 0,
            verdict VARCHAR(20), qual_verdict VARCHAR(20),
            qual_gates JSONB, disqualification_reason TEXT,
            matched_keywords JSONB DEFAULT '[]',
            matched_solutions JSONB DEFAULT '[]',
            document_url VARCHAR(1000), source_url VARCHAR(1000),
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS scan_logs (
            id SERIAL PRIMARY KEY, date VARCHAR(50),
            total_on_portal INTEGER DEFAULT 0, qualified_count INTEGER DEFAULT 0,
            open_qualified_count INTEGER DEFAULT 0, new_count INTEGER DEFAULT 0,
            duration_seconds FLOAT, status VARCHAR(20) DEFAULT 'success',
            error_message TEXT, created_at TIMESTAMP DEFAULT NOW())"""))

        dropped = 0
        nogo_count = 0
        for raw in tenders:
            score, verdict, solutions, keywords, qualification = score_tender(raw["title"])
            if score < 70: continue
            qualified += 1
            qual_verdict = qualification.get("overall_verdict", "GO")
            dq_reason = qualification.get("disqualification_reason")
            cl_date = parse_date(raw.get("closing", ""))
            days = (cl_date - now).days if cl_date else None
            is_open = days is not None and days >= 0

            # ── STRICT OPEN-STATUS GATE: drop expired tenders ──
            if not is_open:
                dropped += 1
                continue

            open_qual += 1
            existing = conn.execute(text("SELECT id FROM tenders WHERE id=:id"), {"id": raw["id"]}).fetchone()
            source = raw.get("source", "Sindh Bank")
            if qual_verdict == "NOGO":
                nogo_count += 1

            if existing:
                conn.execute(text("UPDATE tenders SET is_open=:o,days_remaining=:d,score=:s,verdict=:v,qual_verdict=:qv,qual_gates=:qg,disqualification_reason=:dq,matched_keywords=:kw,matched_solutions=:sol,document_url=COALESCE(:doc,document_url),updated_at=:now WHERE id=:id"),
                    {"id":raw["id"],"o":is_open,"d":days,"s":score,"v":verdict,"qv":qual_verdict,"qg":json.dumps(qualification.get("gates",{})),"dq":dq_reason,"kw":json.dumps(keywords),"sol":json.dumps(solutions),"doc":raw.get("doc_url"),"now":now})
            else:
                new_count += 1
                src_url = (
                    "https://epms.ppra.gov.pk/public/tenders/active-tenders"
                    if source == "PPRA"
                    else SINDH_PORTAL_URL
                )
                conn.execute(text("INSERT INTO tenders (id,title,department,advertised,closing,closing_date,is_open,days_remaining,score,verdict,qual_verdict,qual_gates,disqualification_reason,matched_keywords,matched_solutions,document_url,source_url) VALUES (:id,:ti,:dept,:ad,:cl,:cld,:o,:d,:s,:v,:qv,:qg,:dq,:kw,:sol,:doc,:src)"),
                    {"id":raw["id"],"ti":raw["title"],"dept":raw.get("department",""),"ad":raw.get("advertised",""),"cl":raw.get("closing",""),"cld":cl_date,"o":is_open,"d":days,"s":score,"v":verdict,"qv":qual_verdict,"qg":json.dumps(qualification.get("gates",{})),"dq":dq_reason,"kw":json.dumps(keywords),"sol":json.dumps(solutions),"doc":raw.get("doc_url"),"src":src_url})

        conn.execute(text("INSERT INTO scan_logs (date,total_on_portal,qualified_count,open_qualified_count,new_count,duration_seconds,status) VALUES (:d,:t,:q,:oq,:n,:dur,'success')"),
            {"d":now.strftime("%Y-%m-%d %H:%M"),"t":total,"q":qualified,"oq":open_qual,"n":new_count,"dur":(datetime.utcnow()-now).total_seconds()})

    print(f"DB: {qualified} qualified, {open_qual} open ({new_count} new), {nogo_count} NOGO, {dropped} dropped (expired)")
    return qualified


if __name__ == "__main__":
    tenders = scrape_tenders()
    if tenders:
        save_to_db(tenders)
    else:
        from sqlalchemy import create_engine, text
        engine = create_engine(DATABASE_URL)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS scan_logs (id SERIAL PRIMARY KEY,date VARCHAR(50),total_on_portal INTEGER DEFAULT 0,qualified_count INTEGER DEFAULT 0,open_qualified_count INTEGER DEFAULT 0,new_count INTEGER DEFAULT 0,duration_seconds FLOAT,status VARCHAR(20) DEFAULT 'success',error_message TEXT,created_at TIMESTAMP DEFAULT NOW())"))
            conn.execute(text("INSERT INTO scan_logs (date,total_on_portal,status,error_message) VALUES (:d,0,'no_data','All scraping strategies failed')"),
                {"d": datetime.utcnow().strftime("%Y-%m-%d %H:%M")})
        print("Logged: no data retrieved. Will retry next scheduled run.")
