"""
Lightweight scraper for GitHub Actions (no Playwright needed).
Uses requests + BeautifulSoup, writes directly to Supabase PostgreSQL.

This runs as a GitHub Action on a free schedule. It replaces Agent 1
without needing a server running 24/7.
"""
import os
import sys
import re
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from scorer import score_tender

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set. Add it as a GitHub secret.")
    sys.exit(1)


def scrape_tenders():
    """Scrape Sindh Bank portal using requests (no browser needed)."""
    import requests
    from bs4 import BeautifulSoup

    url = "https://sindhbank.com.pk/tenders"
    print(f"Fetching {url}...")

    resp = requests.get(url, timeout=30, headers={"User-Agent": "NETS-TenderScout/1.0"})
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
                "id": texts[0] if texts else "",
                "title": texts[1] if len(texts) > 1 else "",
                "department": texts[2] if len(texts) > 2 else "",
                "advertised": texts[3] if len(texts) > 3 else "",
                "closing": texts[4] if len(texts) > 4 else "",
                "doc_url": doc_url,
            }
            if tender["title"] and len(tender["title"]) > 3:
                tenders.append(tender)

    print(f"Found {len(tenders)} tenders on portal")
    return tenders


def parse_date(s):
    if not s:
        return None
    m = re.match(r'(\d{1,2})-([A-Za-z]{3})-(\d{2,4})', s.strip())
    if m:
        months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                   "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
        mon = months.get(m.group(2).lower()[:3])
        yr = int(m.group(3))
        if yr < 100: yr += 2000
        if mon:
            try:
                return datetime(yr, mon, int(m.group(1)))
            except ValueError:
                pass
    return None


def save_to_db(tenders):
    """Save qualified tenders to Supabase PostgreSQL."""
    from sqlalchemy import create_engine, text

    engine = create_engine(DATABASE_URL)
    now = datetime.utcnow()

    total = len(tenders)
    qualified = 0
    new_count = 0
    open_qual = 0

    with engine.begin() as conn:
        # Ensure tables exist
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tenders (
                id VARCHAR(100) PRIMARY KEY,
                title VARCHAR(500),
                department VARCHAR(100),
                advertised VARCHAR(50),
                closing VARCHAR(50),
                closing_date TIMESTAMP,
                is_open BOOLEAN DEFAULT TRUE,
                days_remaining INTEGER,
                score INTEGER DEFAULT 0,
                verdict VARCHAR(20),
                matched_keywords JSONB DEFAULT '[]',
                matched_solutions JSONB DEFAULT '[]',
                document_url VARCHAR(1000),
                source_url VARCHAR(1000),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scan_logs (
                id SERIAL PRIMARY KEY,
                date VARCHAR(50),
                total_on_portal INTEGER DEFAULT 0,
                qualified_count INTEGER DEFAULT 0,
                open_qualified_count INTEGER DEFAULT 0,
                new_count INTEGER DEFAULT 0,
                duration_seconds FLOAT,
                status VARCHAR(20) DEFAULT 'success',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        for raw in tenders:
            score, verdict, solutions, keywords = score_tender(raw["title"])
            if score < 70:
                continue

            qualified += 1
            cl_date = parse_date(raw.get("closing", ""))
            days = (cl_date - now).days if cl_date else None
            is_open = days is not None and days >= 0
            if is_open:
                open_qual += 1

            # Check if exists
            existing = conn.execute(
                text("SELECT id FROM tenders WHERE id = :id"),
                {"id": raw["id"]}
            ).fetchone()

            import json
            if existing:
                conn.execute(text("""
                    UPDATE tenders SET is_open = :is_open, days_remaining = :days,
                    score = :score, verdict = :verdict, matched_keywords = :kw,
                    matched_solutions = :sol, document_url = COALESCE(:doc, document_url),
                    updated_at = :now WHERE id = :id
                """), {"id": raw["id"], "is_open": is_open, "days": days,
                       "score": score, "verdict": verdict,
                       "kw": json.dumps(keywords), "sol": json.dumps(solutions),
                       "doc": raw.get("doc_url"), "now": now})
            else:
                new_count += 1
                conn.execute(text("""
                    INSERT INTO tenders (id, title, department, advertised, closing,
                    closing_date, is_open, days_remaining, score, verdict,
                    matched_keywords, matched_solutions, document_url, source_url)
                    VALUES (:id, :title, :dept, :ad, :cl, :cl_date, :is_open, :days,
                    :score, :verdict, :kw, :sol, :doc, :src)
                """), {"id": raw["id"], "title": raw["title"], "dept": raw.get("department",""),
                       "ad": raw.get("advertised",""), "cl": raw.get("closing",""),
                       "cl_date": cl_date, "is_open": is_open, "days": days,
                       "score": score, "verdict": verdict,
                       "kw": json.dumps(keywords), "sol": json.dumps(solutions),
                       "doc": raw.get("doc_url"),
                       "src": "https://sindhbank.com.pk/tenders"})

        # Log the scan
        conn.execute(text("""
            INSERT INTO scan_logs (date, total_on_portal, qualified_count,
            open_qualified_count, new_count, status)
            VALUES (:date, :total, :qual, :oq, :new, 'success')
        """), {"date": now.strftime("%Y-%m-%d %H:%M"), "total": total,
               "qual": qualified, "oq": open_qual, "new": new_count})

    print(f"Saved: {qualified} qualified ({new_count} new), {open_qual} open")
    return qualified


if __name__ == "__main__":
    start = datetime.utcnow()
    tenders = scrape_tenders()
    saved = save_to_db(tenders)
    duration = (datetime.utcnow() - start).total_seconds()
    print(f"Done in {duration:.1f}s. {len(tenders)} scraped, {saved} qualified.")
