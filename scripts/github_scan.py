"""
Lightweight scraper for GitHub Actions.
Uses 4 fallback strategies to reach sindhbank.com.pk from cloud servers.
Writes directly to Supabase PostgreSQL. No Playwright needed.
"""
import os
import sys
import re
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from scorer import score_tender

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set.")
    sys.exit(1)

PORTAL_URL = "https://sindhbank.com.pk/tenders"


def scrape_tenders():
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    html = None

    # Strategy 1: direct request
    try:
        print(f"Strategy 1: Direct request to {PORTAL_URL}")
        resp = requests.get(PORTAL_URL, headers=headers, timeout=60)
        resp.raise_for_status()
        html = resp.text
        print(f"  Success: {len(html)} bytes")
    except Exception as e:
        print(f"  Failed: {e}")

    # Strategy 2: allorigins.win free CORS proxy (no API key needed)
    if not html:
        try:
            proxy_url = f"https://api.allorigins.win/raw?url={PORTAL_URL}"
            print(f"Strategy 2: allorigins proxy")
            resp = requests.get(proxy_url, timeout=60)
            if resp.status_code == 200 and len(resp.text) > 500:
                html = resp.text
                print(f"  Success: {len(html)} bytes")
        except Exception as e:
            print(f"  Failed: {e}")

    # Strategy 3: corsproxy.io (free, no key)
    if not html:
        try:
            proxy_url = f"https://corsproxy.io/?{PORTAL_URL}"
            print(f"Strategy 3: corsproxy.io")
            resp = requests.get(proxy_url, timeout=60)
            if resp.status_code == 200 and len(resp.text) > 500:
                html = resp.text
                print(f"  Success: {len(html)} bytes")
        except Exception as e:
            print(f"  Failed: {e}")

    # Strategy 4: Google cache
    if not html:
        try:
            cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{PORTAL_URL}"
            print(f"Strategy 4: Google cache")
            resp = requests.get(cache_url, headers=headers, timeout=30)
            if resp.status_code == 200 and len(resp.text) > 500:
                html = resp.text
                print(f"  Success: {len(html)} bytes (cached)")
        except Exception as e:
            print(f"  Failed: {e}")

    if not html:
        print("All strategies failed.")
        return []

    # Parse
    soup = BeautifulSoup(html, "html.parser")
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
                "id": texts[0] if texts else "",
                "title": texts[1] if len(texts) > 1 else "",
                "department": texts[2] if len(texts) > 2 else "",
                "advertised": texts[3] if len(texts) > 3 else "",
                "closing": texts[4] if len(texts) > 4 else "",
                "doc_url": doc_url,
            }
            if tender["title"] and len(tender["title"]) > 3:
                tenders.append(tender)

    print(f"Parsed {len(tenders)} tenders")
    return tenders


def parse_date(s):
    if not s: return None
    m = re.match(r'(\d{1,2})-([A-Za-z]{3})-(\d{2,4})', s.strip())
    if m:
        months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                   "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
        mon = months.get(m.group(2).lower()[:3])
        yr = int(m.group(3))
        if yr < 100: yr += 2000
        if mon:
            try: return datetime(yr, mon, int(m.group(1)))
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
            verdict VARCHAR(20), matched_keywords JSONB DEFAULT '[]',
            matched_solutions JSONB DEFAULT '[]',
            document_url VARCHAR(1000), source_url VARCHAR(1000),
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS scan_logs (
            id SERIAL PRIMARY KEY, date VARCHAR(50),
            total_on_portal INTEGER DEFAULT 0, qualified_count INTEGER DEFAULT 0,
            open_qualified_count INTEGER DEFAULT 0, new_count INTEGER DEFAULT 0,
            duration_seconds FLOAT, status VARCHAR(20) DEFAULT 'success',
            error_message TEXT, created_at TIMESTAMP DEFAULT NOW())"""))

        for raw in tenders:
            score, verdict, solutions, keywords = score_tender(raw["title"])
            if score < 70: continue
            qualified += 1
            cl_date = parse_date(raw.get("closing", ""))
            days = (cl_date - now).days if cl_date else None
            is_open = days is not None and days >= 0
            if is_open: open_qual += 1
            existing = conn.execute(text("SELECT id FROM tenders WHERE id=:id"), {"id": raw["id"]}).fetchone()
            if existing:
                conn.execute(text("UPDATE tenders SET is_open=:o,days_remaining=:d,score=:s,verdict=:v,matched_keywords=:kw,matched_solutions=:sol,document_url=COALESCE(:doc,document_url),updated_at=:now WHERE id=:id"),
                    {"id":raw["id"],"o":is_open,"d":days,"s":score,"v":verdict,"kw":json.dumps(keywords),"sol":json.dumps(solutions),"doc":raw.get("doc_url"),"now":now})
            else:
                new_count += 1
                conn.execute(text("INSERT INTO tenders (id,title,department,advertised,closing,closing_date,is_open,days_remaining,score,verdict,matched_keywords,matched_solutions,document_url,source_url) VALUES (:id,:ti,:dept,:ad,:cl,:cld,:o,:d,:s,:v,:kw,:sol,:doc,:src)"),
                    {"id":raw["id"],"ti":raw["title"],"dept":raw.get("department",""),"ad":raw.get("advertised",""),"cl":raw.get("closing",""),"cld":cl_date,"o":is_open,"d":days,"s":score,"v":verdict,"kw":json.dumps(keywords),"sol":json.dumps(solutions),"doc":raw.get("doc_url"),"src":PORTAL_URL})

        conn.execute(text("INSERT INTO scan_logs (date,total_on_portal,qualified_count,open_qualified_count,new_count,duration_seconds,status) VALUES (:d,:t,:q,:oq,:n,:dur,'success')"),
            {"d":now.strftime("%Y-%m-%d %H:%M"),"t":total,"q":qualified,"oq":open_qual,"n":new_count,"dur":(datetime.utcnow()-now).total_seconds()})

    print(f"DB: {qualified} qualified ({new_count} new), {open_qual} open")
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
