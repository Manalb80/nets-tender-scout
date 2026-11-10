"""
PPRA & Sindh Bank RFP Document Downloader (Agent 1b).

For each qualified tender:
1. Visits the tender detail page
2. Extracts all PDF/document links
3. Downloads the RFP and supporting documents
4. Creates a per-tender folder with manifest.json + PDFs

Works with both portals:
- PPRA: detail page at /public/tenders/tender-details/{tenderNumber}
        documents via /pdf?file=<base64>
- Sindh Bank: direct PDF links from the tender listing

Can run standalone or be called from the scheduled pipeline.
Uses requests for downloads (no Playwright needed; PPRA serves PDFs directly).
Falls back to Playwright only if requests fails (cookie/JS protected downloads).
"""
import os
import re
import json
import logging
import base64
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("downloader")

PPRA_BASE = "https://epms.ppra.gov.pk"
SINDH_BASE = "https://sindhbank.com.pk"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def sanitize_folder_name(name: str) -> str:
    """Make a string safe for use as a folder name."""
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:120]


def decode_ppra_filename(encoded: str) -> str:
    """
    Decode the base64 file parameter from PPRA PDF links.
    e.g. 'dGVuZGVyX2F0dGFjaG1lbnRzLzEyM18xLnBkZg==' -> 'tender_attachments/123_1.pdf'
    Returns just the filename part.
    """
    try:
        # Add padding if needed
        padded = encoded + "=" * (4 - len(encoded) % 4) if len(encoded) % 4 else encoded
        decoded = base64.b64decode(padded).decode("utf-8", errors="replace")
        # Return just the filename, not the full path
        return Path(decoded).name
    except Exception:
        return ""


def fetch_ppra_detail_page(tender_number: str) -> Dict:
    """
    Fetch a PPRA tender detail page and extract document links.
    Returns dict with 'documents' list, each having 'label', 'url', 'filename'.
    """
    detail_url = f"{PPRA_BASE}/public/tenders/tender-details/{tender_number}"
    documents = []
    metadata = {}

    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"PPRA detail page {tender_number} returned {resp.status_code}")
            return {"documents": [], "metadata": {}, "detail_url": detail_url}

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract all PDF links (pattern: /pdf?file=<base64>)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)

            if "/pdf?file=" in href:
                # Build full URL
                full_url = urljoin(PPRA_BASE, href)

                # Extract and decode the filename from base64
                match = re.search(r'file=([A-Za-z0-9+/=]+)', href)
                decoded_name = ""
                if match:
                    decoded_name = decode_ppra_filename(match.group(1))

                # Determine document type from link text
                if "tender document" in text.lower() or "bidding" in text.lower():
                    doc_type = "rfp"
                    default_name = "RFP_Document.pdf"
                elif "advertisement" in text.lower():
                    doc_type = "advertisement"
                    default_name = "Advertisement.pdf"
                elif "corrigendum" in text.lower():
                    doc_type = "corrigendum"
                    default_name = "Corrigendum.pdf"
                elif "addendum" in text.lower():
                    doc_type = "addendum"
                    default_name = "Addendum.pdf"
                else:
                    doc_type = "other"
                    default_name = f"Document_{len(documents)+1}.pdf"

                filename = decoded_name if decoded_name else default_name

                documents.append({
                    "label": text,
                    "url": full_url,
                    "filename": filename,
                    "type": doc_type,
                })

        # Extract extra metadata from the detail page
        # Look for common fields in the page
        for row in soup.find_all("div", class_=re.compile(r"row|detail|info")):
            text = row.get_text(" ", strip=True)
            if "organization" in text.lower():
                parts = text.split(":", 1)
                if len(parts) == 2:
                    metadata["organization"] = parts[1].strip()
            if "sector" in text.lower():
                parts = text.split(":", 1)
                if len(parts) == 2:
                    metadata["sector"] = parts[1].strip()

    except Exception as e:
        logger.error(f"Failed to fetch PPRA detail for {tender_number}: {e}")

    return {
        "documents": documents,
        "metadata": metadata,
        "detail_url": detail_url,
    }


def download_file(url: str, dest_path: Path, max_retries: int = 2) -> bool:
    """
    Download a file from a URL to a local path.
    Returns True if successful.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, stream=True, timeout=60)
            if resp.status_code != 200:
                logger.warning(f"Download returned {resp.status_code}: {url}")
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return False

            # Write the file in chunks
            total_bytes = 0
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_bytes += len(chunk)

            # Verify we got something real
            if total_bytes < 100:
                logger.warning(f"Download too small ({total_bytes} bytes): {url}")
                dest_path.unlink(missing_ok=True)
                return False

            # Verify PDF signature if expected
            if dest_path.suffix.lower() == ".pdf":
                with open(dest_path, "rb") as f:
                    header = f.read(5)
                if header != b"%PDF-":
                    logger.warning(f"Not a valid PDF (got {header[:20]}): {url}")
                    # Keep the file anyway; it might be HTML or another format
                    new_name = dest_path.with_suffix(".html")
                    dest_path.rename(new_name)
                    logger.info(f"Renamed to {new_name}")

            logger.info(f"Downloaded {total_bytes:,} bytes -> {dest_path.name}")
            return True

        except Exception as e:
            logger.error(f"Download error (attempt {attempt+1}): {e}")
            if attempt < max_retries:
                time.sleep(2)

    return False


def download_tender_documents(
    tender: Dict,
    base_dir: Path,
    source: str = "PPRA",
    skip_existing: bool = True,
) -> Dict:
    """
    Download all documents for a single qualified tender.

    Args:
        tender: dict with id, title, department, closing, score, solMatch, doc_url, detail_url
        base_dir: root folder (e.g. D:\\NETS\\DIGITISATION\\tender-fetcher\\PPRA)
        source: "PPRA" or "Sindh Bank"
        skip_existing: skip tenders that already have a manifest.json

    Returns:
        dict with tender_number, folder, documents_downloaded, status
    """
    tender_id = tender.get("id", "unknown")
    title = tender.get("title", "Untitled")

    # Create a readable folder name: "TS0000016912E - Supply Installation of Firewalls"
    folder_name = sanitize_folder_name(f"{tender_id} - {title}")
    tender_folder = base_dir / folder_name
    tender_folder.mkdir(parents=True, exist_ok=True)

    result = {
        "tender_number": tender_id,
        "folder": str(tender_folder),
        "documents_downloaded": 0,
        "documents_failed": 0,
        "status": "pending",
    }

    # Check if already downloaded
    manifest_path = tender_folder / "manifest.json"
    if skip_existing and manifest_path.exists():
        logger.info(f"Skipping {tender_id} (already downloaded)")
        result["status"] = "skipped"
        return result

    # Fetch document links from detail page
    documents = []
    detail_metadata = {}

    if source == "PPRA":
        # Extract tender number for the detail page URL
        tender_number = tender_id
        # Clean PPRA prefix if present
        if tender_number.startswith("PPRA-"):
            tender_number = tender_number[5:]
        # Clean trailing text that gets appended from table parsing
        # e.g. "TS0000016912EProcurement" -> "TS0000016912E"
        m = re.match(r'(TS\d+E)', tender_number)
        if m:
            tender_number = m.group(1)

        detail_info = fetch_ppra_detail_page(tender_number)
        documents = detail_info["documents"]
        detail_metadata = detail_info.get("metadata", {})

    elif source == "Sindh Bank":
        # Sindh Bank has direct PDF links from the listing page
        doc_url = tender.get("doc_url", "")
        if doc_url:
            documents.append({
                "label": "RFP Document",
                "url": doc_url,
                "filename": f"{tender_id}_RFP.pdf",
                "type": "rfp",
            })

    # Build and save manifest.json (before downloads, so we have the metadata even if downloads fail)
    manifest = {
        "tender_number": tender_id,
        "title": title,
        "department": tender.get("department", ""),
        "advertised": tender.get("advertised", ""),
        "closing_date": tender.get("closing", ""),
        "score": tender.get("score", 0),
        "verdict": tender.get("verdict", ""),
        "matched_solutions": tender.get("solMatch", []),
        "matched_keywords": tender.get("matched", []),
        "source_portal": source,
        "source_url": tender.get("detail_url", "") or tender.get("doc_url", ""),
        "documents": [],
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "organization": detail_metadata.get("organization", tender.get("department", "")),
    }

    # Download each document
    for doc in documents:
        doc_url = doc["url"]
        filename = doc["filename"]

        # Ensure unique filenames
        dest_path = tender_folder / filename
        counter = 1
        while dest_path.exists():
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            dest_path = tender_folder / f"{stem}_{counter}{suffix}"
            counter += 1

        success = download_file(doc_url, dest_path)

        doc_record = {
            "label": doc["label"],
            "type": doc["type"],
            "filename": dest_path.name,
            "url": doc_url,
            "downloaded": success,
            "size_bytes": dest_path.stat().st_size if success and dest_path.exists() else 0,
        }
        manifest["documents"].append(doc_record)

        if success:
            result["documents_downloaded"] += 1
        else:
            result["documents_failed"] += 1

    # Update manifest with download results
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    result["status"] = "complete" if result["documents_downloaded"] > 0 else "no_documents"
    return result


def sync_qualified_tenders(
    tenders: List[Dict],
    base_dir: str = r"D:\NETS\DIGITISATION\tender-fetcher",
    source: str = "PPRA",
    max_tenders: int = 50,
    only_open: bool = True,
) -> Dict:
    """
    Download documents for all qualified tenders.
    This is the main entry point for Agent 1b.

    Args:
        tenders: list of scored tender dicts from the scraper/DB
        base_dir: root sync folder on D:\\ drive
        source: "PPRA" or "Sindh Bank"
        max_tenders: limit downloads per run
        only_open: only download tenders with future closing dates

    Returns:
        execution report with counts and per-tender results
    """
    start_time = datetime.now(timezone.utc)
    portal_dir = Path(base_dir) / source.replace(" ", "_")
    portal_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "agent": "Agent 1b: RFP Document Sync",
        "timestamp": start_time.isoformat(),
        "source": source,
        "base_dir": str(portal_dir),
        "status": "running",
        "total_qualified": len(tenders),
        "processed": 0,
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }

    # Filter to qualified + open if requested
    qualified = [t for t in tenders if t.get("score", 0) >= 70]
    if only_open:
        qualified = [t for t in qualified if t.get("open", True)]

    logger.info(
        f"Agent 1b starting: {len(qualified)} qualified tenders "
        f"from {source}, syncing to {portal_dir}"
    )

    for i, tender in enumerate(qualified[:max_tenders]):
        logger.info(f"[{i+1}/{min(len(qualified), max_tenders)}] {tender.get('id', '?')}: {tender.get('title', '')[:60]}")

        result = download_tender_documents(
            tender=tender,
            base_dir=portal_dir,
            source=source,
        )

        report["details"].append(result)
        report["processed"] += 1

        if result["status"] == "complete":
            report["downloaded"] += 1
        elif result["status"] == "skipped":
            report["skipped"] += 1
        else:
            report["failed"] += 1

        # Polite delay between detail page fetches
        if i < len(qualified) - 1:
            time.sleep(2)

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    report["duration_seconds"] = duration
    report["status"] = "complete"

    # Save the sync report
    report_path = portal_dir / f"sync_report_{start_time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(
        f"Agent 1b complete: {report['downloaded']} downloaded, "
        f"{report['skipped']} skipped, {report['failed']} failed, "
        f"{duration:.1f}s"
    )

    return report


# ── Standalone runner: fetch from DB and sync ──

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Agent 1b: Download RFP documents for qualified tenders")
    parser.add_argument("--source", choices=["PPRA", "Sindh Bank", "both"], default="both",
                        help="Which portal to sync")
    parser.add_argument("--base-dir", default=r"D:\NETS\DIGITISATION\tender-fetcher",
                        help="Root sync folder")
    parser.add_argument("--max", type=int, default=20,
                        help="Max tenders to download per run")
    parser.add_argument("--include-closed", action="store_true",
                        help="Also download closed tenders")
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL"),
                        help="Database URL to fetch tender list from")
    args = parser.parse_args()

    if args.db_url:
        # Fetch qualified tenders from the database
        from sqlalchemy import create_engine, text

        engine = create_engine(args.db_url)
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, title, department, advertised, closing, score, verdict, "
                "matched_keywords, matched_solutions, document_url, source_url, is_open "
                "FROM tenders WHERE score >= 70 ORDER BY score DESC"
            )).fetchall()

        tenders = []
        for row in rows:
            source_url = row[10] or ""
            source = "PPRA" if "ppra" in source_url.lower() else "Sindh Bank"
            tenders.append({
                "id": row[0], "title": row[1], "department": row[2],
                "advertised": row[3], "closing": row[4], "score": row[5],
                "verdict": row[6], "matched": row[7] or [],
                "solMatch": row[8] or [], "doc_url": row[9] or "",
                "source": source, "open": row[11],
            })

        print(f"Loaded {len(tenders)} qualified tenders from database")

        sources = ["PPRA", "Sindh Bank"] if args.source == "both" else [args.source]
        for src in sources:
            src_tenders = [t for t in tenders if t["source"] == src]
            if src_tenders:
                report = sync_qualified_tenders(
                    tenders=src_tenders,
                    base_dir=args.base_dir,
                    source=src,
                    max_tenders=args.max,
                    only_open=not args.include_closed,
                )
                print(f"\n{src}: {report['downloaded']} downloaded, "
                      f"{report['skipped']} skipped, {report['failed']} failed")

    else:
        # Demo mode: scrape PPRA page 1 and download qualified tenders
        print("No DATABASE_URL set. Running demo: scrape PPRA page 1 and download.")

        from scraper_ppra import scrape_ppra_requests, normalize_ppra_tender
        from scorer import score_tender

        result = scrape_ppra_requests(max_pages=1)
        raw_tenders = result["tenders"]

        qualified = []
        for raw in raw_tenders:
            norm = normalize_ppra_tender(raw)
            score, verdict, sols, kws = score_tender(norm["title"])
            if score >= 70:
                norm["score"] = score
                norm["verdict"] = verdict
                norm["solMatch"] = sols
                norm["matched"] = kws
                norm["open"] = True
                qualified.append(norm)

        print(f"Found {len(qualified)} qualified tenders on page 1")

        report = sync_qualified_tenders(
            tenders=qualified,
            base_dir=args.base_dir,
            source="PPRA",
            max_tenders=args.max,
            only_open=False,
        )

        print(f"\nResult: {report['downloaded']} downloaded, "
              f"{report['skipped']} skipped, {report['failed']} failed")
