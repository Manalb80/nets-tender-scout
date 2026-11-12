"""
Agent 1b: RFP Document Acquisition Engine.

Strict 2-step workflow:
  Step 1: Portal Discovery (handled by scraper.py / scraper_ppra.py)
  Step 2: Open-Status Filter Gate (cl >= NOW; drop expired instantly)
  Step 3: Dual-Path Document Handler:
    Path A: Auto-downloadable (public PDF) -> download to D:\
    Path B: Restricted/protected -> flag MANUAL_DOWNLOAD_REQUIRED, create folder + manifest

Works with both portals:
  PPRA: detail page at /public/tenders/tender-details/{tenderNumber}
        documents via /pdf?file=<base64>
  Sindh Bank: direct PDF links from the tender listing

Governance: UK and Pakistan AI compliance (data sovereignty, transparent source
linking, audit trail via manifest.json, human-in-the-loop for Path B).
"""
import os
import re
import json
import logging
import base64
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("downloader")

PPRA_BASE = "https://epms.ppra.gov.pk"
SINDH_BASE = "https://sindhbank.com.pk"

DEFAULT_BASE_DIR = r"D:\NETS\DIGITISATION\tender-fetcher"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Date parsing (shared across portal formats)
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ─────────────────────────────────────────────
# STEP 2: Open-Status Filter Gate
# ─────────────────────────────────────────────

def parse_closing_date(date_str: str) -> Optional[datetime]:
    """Parse closing dates from any portal format into a datetime."""
    if not date_str:
        return None
    s = date_str.strip()

    # "5-Nov-26" or "22-Oct-2026"
    m = re.match(r'(\d{1,2})-([A-Za-z]{3,})-(\d{2,4})', s)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower()[:3])
        yr = int(m.group(3))
        if yr < 100:
            yr += 2000
        if mon:
            try:
                return datetime(yr, mon, int(m.group(1)), tzinfo=timezone.utc)
            except ValueError:
                pass

    # "Nov 25, 2026" or "Nov 25, 202611:00 AM" (PPRA format with time appended)
    cleaned = re.sub(r'(\d{4})\d{1,2}:\d{2}\s*(AM|PM)', r'\1', s)
    m = re.match(r'([A-Za-z]{3,})\s+(\d{1,2}),?\s+(\d{4})', cleaned)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower()[:3])
        if mon:
            try:
                return datetime(int(m.group(3)), mon, int(m.group(2)), tzinfo=timezone.utc)
            except ValueError:
                pass

    # "2026-11-25" or "2026-11-25T..."
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass

    # "25/11/2026"
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def is_open_tender(tender: Dict) -> Tuple[bool, Optional[int]]:
    """
    STRICT OPEN-STATUS GATE.
    Returns (is_open, days_remaining).
    A tender is open ONLY if closing_date >= NOW.
    No closing date: treated as open (benefit of the doubt; flagged in manifest).
    """
    now = datetime.now(timezone.utc)

    # Try pre-parsed datetime first
    cl = tender.get("closing_date_obj")
    if not cl:
        cl = parse_closing_date(tender.get("closing", ""))

    if cl is None:
        # No closing date available; keep it but flag
        return True, None

    # Ensure timezone-aware comparison
    if cl.tzinfo is None:
        cl = cl.replace(tzinfo=timezone.utc)

    days = (cl - now).days
    return days >= 0, days


def filter_open_only(tenders: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Apply the strict open-status gate to a list of tenders.
    Returns (open_tenders, dropped_tenders).
    """
    open_tenders = []
    dropped = []

    for t in tenders:
        is_open, days = is_open_tender(t)
        t["is_open"] = is_open
        t["days_remaining"] = days

        if is_open:
            open_tenders.append(t)
        else:
            dropped.append(t)

    logger.info(
        f"Open-status gate: {len(open_tenders)} open, "
        f"{len(dropped)} dropped (expired)"
    )
    return open_tenders, dropped


# ─────────────────────────────────────────────
# STEP 3: Document Discovery & Accessibility Check
# ─────────────────────────────────────────────

def sanitize_folder_name(name: str) -> str:
    """Make a string safe for use as a folder name."""
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:120]


def decode_ppra_filename(encoded: str) -> str:
    """Decode base64 file parameter from PPRA PDF links."""
    try:
        padded = encoded + "=" * (4 - len(encoded) % 4) if len(encoded) % 4 else encoded
        decoded = base64.b64decode(padded).decode("utf-8", errors="replace")
        return Path(decoded).name
    except Exception:
        return ""


def clean_ppra_tender_id(tender_id: str) -> str:
    """Clean PPRA tender ID: remove prefix and trailing text."""
    tid = tender_id
    if tid.startswith("PPRA-"):
        tid = tid[5:]
    m = re.match(r'(TS\d+E)', tid)
    if m:
        tid = m.group(1)
    return tid


def fetch_ppra_detail_page(tender_number: str) -> Dict:
    """
    Fetch a PPRA tender detail page and extract document links.
    Returns dict with 'documents', 'metadata', 'detail_url', 'accessible'.
    """
    detail_url = f"{PPRA_BASE}/public/tenders/tender-details/{tender_number}"
    documents = []
    metadata = {}
    accessible = True  # assume public unless proven otherwise

    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=30)

        if resp.status_code == 403:
            accessible = False
            logger.warning(f"PPRA detail page {tender_number} returned 403 (restricted)")
            return {"documents": [], "metadata": {}, "detail_url": detail_url, "accessible": False}

        if resp.status_code != 200:
            logger.warning(f"PPRA detail page {tender_number} returned {resp.status_code}")
            return {"documents": [], "metadata": {}, "detail_url": detail_url, "accessible": True}

        soup = BeautifulSoup(resp.text, "html.parser")

        # Check for login/password gate indicators
        login_indicators = soup.find_all(
            string=re.compile(r'(login|sign.?in|password|authenticate|restricted access)', re.I)
        )
        if login_indicators:
            accessible = False
            logger.info(f"PPRA {tender_number}: login/password gate detected")

        # Extract all PDF links (pattern: /pdf?file=<base64>)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)

            if "/pdf?file=" in href:
                full_url = urljoin(PPRA_BASE, href)
                match = re.search(r'file=([A-Za-z0-9+/=]+)', href)
                decoded_name = decode_ppra_filename(match.group(1)) if match else ""

                if "tender document" in text.lower() or "bidding" in text.lower():
                    doc_type, default_name = "rfp", "RFP_Document.pdf"
                elif "advertisement" in text.lower():
                    doc_type, default_name = "advertisement", "Advertisement.pdf"
                elif "corrigendum" in text.lower():
                    doc_type, default_name = "corrigendum", "Corrigendum.pdf"
                elif "addendum" in text.lower():
                    doc_type, default_name = "addendum", "Addendum.pdf"
                else:
                    doc_type = "other"
                    default_name = f"Document_{len(documents)+1}.pdf"

                documents.append({
                    "label": text,
                    "url": full_url,
                    "filename": decoded_name or default_name,
                    "type": doc_type,
                })

        # Extract metadata
        for row in soup.find_all("div", class_=re.compile(r"row|detail|info")):
            text = row.get_text(" ", strip=True)
            if "organization" in text.lower():
                parts = text.split(":", 1)
                if len(parts) == 2:
                    metadata["organization"] = parts[1].strip()[:200]
            if "sector" in text.lower():
                parts = text.split(":", 1)
                if len(parts) == 2:
                    metadata["sector"] = parts[1].strip()[:100]

    except requests.exceptions.ConnectionError:
        accessible = False
        logger.error(f"Cannot reach PPRA detail page for {tender_number}")
    except Exception as e:
        logger.error(f"Failed to fetch PPRA detail for {tender_number}: {e}")

    return {
        "documents": documents,
        "metadata": metadata,
        "detail_url": detail_url,
        "accessible": accessible,
    }


def check_pdf_accessible(url: str) -> bool:
    """
    HEAD request to check if a PDF is publicly downloadable.
    Returns False if it requires login, returns 403, or times out.
    """
    try:
        resp = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            # Valid if it serves a PDF or octet-stream
            return "pdf" in content_type or "octet" in content_type or "application" in content_type
        if resp.status_code in (401, 403):
            return False
        # For other codes, try GET as some servers don't support HEAD
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=15)
        chunk = next(resp.iter_content(16), b"")
        resp.close()
        return chunk[:5] == b"%PDF-" or len(chunk) > 10
    except Exception:
        return False


def download_file(url: str, dest_path: Path, max_retries: int = 2) -> bool:
    """Download a file from a URL. Returns True if successful."""
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, stream=True, timeout=60)
            if resp.status_code in (401, 403):
                logger.warning(f"Access denied ({resp.status_code}): {url}")
                return False
            if resp.status_code != 200:
                logger.warning(f"Download returned {resp.status_code}: {url}")
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return False

            total_bytes = 0
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_bytes += len(chunk)

            if total_bytes < 100:
                logger.warning(f"Download too small ({total_bytes} bytes): {url}")
                dest_path.unlink(missing_ok=True)
                return False

            # Verify PDF signature
            if dest_path.suffix.lower() == ".pdf":
                with open(dest_path, "rb") as f:
                    header = f.read(5)
                if header != b"%PDF-":
                    logger.warning(f"Not a valid PDF: {url}")
                    new_name = dest_path.with_suffix(".html")
                    dest_path.rename(new_name)

            logger.info(f"Downloaded {total_bytes:,} bytes -> {dest_path.name}")
            return True

        except Exception as e:
            logger.error(f"Download error (attempt {attempt+1}): {e}")
            if attempt < max_retries:
                time.sleep(2)

    return False


# ─────────────────────────────────────────────
# STEP 3: Dual-Path Document Handler
# ─────────────────────────────────────────────

def process_tender_acquisition(
    tender: Dict,
    base_dir: Path,
    source: str = "PPRA",
    skip_existing: bool = True,
) -> Dict:
    """
    Process a single OPEN, QUALIFIED tender through the dual-path handler.

    Path A (AUTO_DOWNLOADED): PDF is public, download it.
    Path B (MANUAL_DOWNLOAD_REQUIRED): PDF is restricted, create folder + manifest,
           flag for human action via dashboard button.

    Returns a result dict written to the Artifact DB and used by the dashboard.
    """
    now = datetime.now(timezone.utc)
    tender_id = tender.get("id", "unknown")
    title = tender.get("title", "Untitled")

    # Build folder path: D:\NETS\DIGITISATION\tender-fetcher\<PORTAL>\<TENDER_ID>
    portal_dir_name = source.upper().replace(" ", "_")  # "PPRA" or "SINDH_BANK"
    tender_folder = base_dir / portal_dir_name / sanitize_folder_name(tender_id)
    tender_folder.mkdir(parents=True, exist_ok=True)

    result = {
        "tender_id": tender_id,
        "title": title,
        "source_portal": source,
        "folder_path": str(tender_folder),
        "acquisition_status": "PENDING",
        "documents_downloaded": 0,
        "documents_failed": 0,
        "is_auto_downloadable": False,
        "detail_url": "",
        "processed_at": now.isoformat(),
    }

    manifest_path = tender_folder / "manifest.json"

    # Skip if already processed
    if skip_existing and manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text())
            if existing.get("acquisition_status") in ("AUTO_DOWNLOADED", "MANUAL_DOWNLOAD_REQUIRED"):
                logger.info(f"Skipping {tender_id} (already processed: {existing['acquisition_status']})")
                result["acquisition_status"] = existing["acquisition_status"]
                return result
        except Exception:
            pass

    # ── Discover documents ──
    documents = []
    detail_metadata = {}
    page_accessible = True

    if source == "PPRA":
        clean_id = clean_ppra_tender_id(tender_id)
        detail_info = fetch_ppra_detail_page(clean_id)
        documents = detail_info["documents"]
        detail_metadata = detail_info.get("metadata", {})
        page_accessible = detail_info.get("accessible", True)
        result["detail_url"] = detail_info["detail_url"]

    elif source == "Sindh Bank":
        doc_url = tender.get("doc_url", "")
        result["detail_url"] = doc_url
        if doc_url:
            documents.append({
                "label": "RFP Document",
                "url": doc_url,
                "filename": f"RFP.pdf",
                "type": "rfp",
            })

    # ── Determine Path A vs Path B ──
    has_documents = len(documents) > 0
    docs_are_accessible = page_accessible

    if has_documents and docs_are_accessible:
        # Quick check: can we actually download the first document?
        first_url = documents[0]["url"]
        docs_are_accessible = check_pdf_accessible(first_url)

    is_auto = has_documents and docs_are_accessible
    result["is_auto_downloadable"] = is_auto

    # ── Build manifest (before downloads) ──
    manifest = {
        "tender_id": tender_id,
        "title": title,
        "department": tender.get("department", ""),
        "advertised": tender.get("advertised", ""),
        "closing_date": tender.get("closing", ""),
        "days_remaining": tender.get("days_remaining"),
        "score": tender.get("score", 0),
        "verdict": tender.get("verdict", ""),
        "matched_solutions": tender.get("solMatch", []),
        "matched_keywords": tender.get("matched", []),
        "source_portal": source,
        "source_url": result["detail_url"],
        "organization": detail_metadata.get("organization", tender.get("department", "")),
        "governance_jurisdiction": "Pakistan / UK Public Procurement",
        "acquisition_status": "PENDING",
        "documents": [],
        "processed_at": now.isoformat(),
        "folder_path": str(tender_folder),
    }

    if is_auto:
        # ── PATH A: Auto-download ──
        logger.info(f"[PATH A] {tender_id}: auto-downloading {len(documents)} document(s)")

        for doc in documents:
            filename = doc["filename"]
            dest_path = tender_folder / filename
            # Ensure unique filenames
            counter = 1
            while dest_path.exists():
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                dest_path = tender_folder / f"{stem}_{counter}{suffix}"
                counter += 1

            success = download_file(doc["url"], dest_path)

            doc_record = {
                "label": doc["label"],
                "type": doc["type"],
                "filename": dest_path.name,
                "url": doc["url"],
                "downloaded": success,
                "size_bytes": dest_path.stat().st_size if success and dest_path.exists() else 0,
            }
            manifest["documents"].append(doc_record)

            if success:
                result["documents_downloaded"] += 1
            else:
                result["documents_failed"] += 1

        manifest["acquisition_status"] = "AUTO_DOWNLOADED"
        result["acquisition_status"] = "AUTO_DOWNLOADED"

    else:
        # ── PATH B: Manual download required ──
        reason = "No documents found on detail page"
        if not page_accessible:
            reason = "Detail page requires login or returned 403"
        elif has_documents and not docs_are_accessible:
            reason = "Document links are restricted or password protected"

        logger.info(f"[PATH B] {tender_id}: manual download required ({reason})")

        manifest["acquisition_status"] = "MANUAL_DOWNLOAD_REQUIRED"
        manifest["manual_reason"] = reason
        manifest["manual_instructions"] = (
            f"1. Open the source URL in your browser: {result['detail_url']}\n"
            f"2. Download the RFP document manually\n"
            f"3. Save it to: {tender_folder}\\RFP.pdf"
        )

        # Record the document links we found (even if we couldn't download them)
        for doc in documents:
            manifest["documents"].append({
                "label": doc["label"],
                "type": doc["type"],
                "filename": doc["filename"],
                "url": doc["url"],
                "downloaded": False,
                "manual_download": True,
            })

        result["acquisition_status"] = "MANUAL_DOWNLOAD_REQUIRED"
        result["manual_reason"] = reason

    # ── Write manifest ──
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return result


# ─────────────────────────────────────────────
# Main entry point: Agent 1b
# ─────────────────────────────────────────────

def run_agent_1b(
    tenders: List[Dict],
    base_dir: str = DEFAULT_BASE_DIR,
    max_tenders: int = 50,
) -> Dict:
    """
    Agent 1b: Full pipeline.
    1. Apply open-status filter gate (drop expired)
    2. For each open, qualified tender: run dual-path document handler
    3. Return execution report

    Args:
        tenders: list of scored tender dicts (from scraper + scorer)
        base_dir: root sync folder on D:\ drive
        max_tenders: limit per run
    """
    start_time = datetime.now(timezone.utc)
    base_path = Path(base_dir)

    report = {
        "agent": "Agent 1b: RFP Document Acquisition",
        "timestamp": start_time.isoformat(),
        "base_dir": str(base_path),
        "status": "running",
        "input_count": len(tenders),
        "open_count": 0,
        "dropped_count": 0,
        "auto_downloaded": 0,
        "manual_required": 0,
        "skipped": 0,
        "errors": 0,
        "details": [],
    }

    # ── STEP 2: Strict open-status gate ──
    qualified = [t for t in tenders if t.get("score", 0) >= 70]
    open_tenders, dropped = filter_open_only(qualified)
    report["open_count"] = len(open_tenders)
    report["dropped_count"] = len(dropped)

    logger.info(
        f"Agent 1b: {len(qualified)} qualified, "
        f"{len(open_tenders)} open, {len(dropped)} dropped"
    )

    # ── STEP 3: Process each open tender ──
    for i, tender in enumerate(open_tenders[:max_tenders]):
        source = tender.get("source", "PPRA")
        logger.info(
            f"[{i+1}/{min(len(open_tenders), max_tenders)}] "
            f"{tender.get('id', '?')}: {tender.get('title', '')[:60]}"
        )

        try:
            result = process_tender_acquisition(
                tender=tender,
                base_dir=base_path,
                source=source,
            )
            report["details"].append(result)

            if result["acquisition_status"] == "AUTO_DOWNLOADED":
                report["auto_downloaded"] += 1
            elif result["acquisition_status"] == "MANUAL_DOWNLOAD_REQUIRED":
                report["manual_required"] += 1
            else:
                report["skipped"] += 1

        except Exception as e:
            logger.error(f"Error processing {tender.get('id', '?')}: {e}")
            report["errors"] += 1
            report["details"].append({
                "tender_id": tender.get("id", "unknown"),
                "acquisition_status": "ERROR",
                "error": str(e),
            })

        # Polite delay
        if i < len(open_tenders) - 1:
            time.sleep(2)

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    report["duration_seconds"] = duration
    report["status"] = "complete"

    # Save execution report
    report_path = base_path / f"agent1b_report_{start_time.strftime('%Y%m%d_%H%M%S')}.json"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # D:\ may not exist in cloud; that's fine

    logger.info(
        f"Agent 1b complete: {report['auto_downloaded']} auto-downloaded, "
        f"{report['manual_required']} manual required, "
        f"{report['dropped_count']} dropped, {duration:.1f}s"
    )

    return report


# ─────────────────────────────────────────────
# STEP 4: PDF Text Extraction + Deep Re-scoring
# ─────────────────────────────────────────────

def extract_pdf_text(pdf_path: Path, max_pages: int = 30) -> str:
    """
    Extract text from a downloaded PDF.
    Tries PyMuPDF (fitz) first, falls back to pdfminer, then raw read.
    Returns extracted text or empty string.
    """
    text = ""

    # Try PyMuPDF (fastest, best quality)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        pages = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pages.append(page.get_text())
        doc.close()
        text = "\n".join(pages)
        if len(text.strip()) > 100:
            return text
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"PyMuPDF failed on {pdf_path.name}: {e}")

    # Try pdfminer
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract
        text = pdfminer_extract(str(pdf_path), maxpages=max_pages)
        if len(text.strip()) > 100:
            return text
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"pdfminer failed on {pdf_path.name}: {e}")

    # Last resort: raw binary scan for readable strings
    try:
        with open(pdf_path, "rb") as f:
            raw = f.read(500000)  # First 500KB
        # Extract ASCII strings of 4+ characters
        strings = re.findall(rb'[\x20-\x7e]{4,}', raw)
        text = " ".join(s.decode("ascii", errors="ignore") for s in strings[:500])
    except Exception:
        pass

    return text


def rescore_with_rfp_text(
    tender: Dict,
    rfp_text: str,
) -> Dict:
    """
    Re-score a tender using the full RFP document text.
    This enables Phase 2 deep gate evaluation (turnover, OEM levels, etc.)
    that title-only scoring cannot detect.

    Returns updated qualification dict with gate results.
    """
    from scorer import score_tender

    title = tender.get("title", tender.get("ti", ""))
    score, verdict, solutions, keywords, qualification = score_tender(title, rfp_text=rfp_text)

    return {
        "score": score,
        "verdict": verdict,
        "matched_solutions": solutions,
        "matched_keywords": keywords,
        "qualification": qualification,
        "rfp_text_length": len(rfp_text),
        "deep_scored": True,
    }


def run_deep_scoring(base_dir: str = DEFAULT_BASE_DIR) -> Dict:
    """
    Walk all downloaded tender folders, extract PDF text, re-score with deep gates.
    Returns a report of what changed.
    """
    from scorer import score_tender

    base = Path(base_dir)
    report = {
        "processed": 0,
        "rescored": 0,
        "newly_disqualified": 0,
        "gate_changes": [],
    }

    for portal_dir in base.iterdir():
        if not portal_dir.is_dir():
            continue
        for tender_dir in portal_dir.iterdir():
            if not tender_dir.is_dir():
                continue
            manifest_path = tender_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            # Only process AUTO_DOWNLOADED tenders that have not been deep-scored yet
            if manifest.get("acquisition_status") != "AUTO_DOWNLOADED":
                continue
            if manifest.get("deep_scored"):
                continue

            # Find downloaded PDFs
            pdf_files = list(tender_dir.glob("*.pdf"))
            if not pdf_files:
                continue

            report["processed"] += 1

            # Extract text from all PDFs
            all_text = ""
            for pdf in pdf_files:
                text = extract_pdf_text(pdf)
                all_text += " " + text

            if len(all_text.strip()) < 50:
                logger.warning(f"No readable text from {tender_dir.name}")
                continue

            # Re-score with full RFP text
            title = manifest.get("title", "")
            score, verdict, solutions, keywords, qualification = score_tender(title, rfp_text=all_text)

            old_qual = manifest.get("qual_verdict", "GO")
            new_qual = qualification.get("overall_verdict", "GO")

            manifest["deep_scored"] = True
            manifest["deep_score"] = score
            manifest["deep_verdict"] = verdict
            manifest["qual_verdict"] = new_qual
            manifest["qual_gates"] = qualification.get("gates", {})
            manifest["disqualification_reason"] = qualification.get("disqualification_reason")
            manifest["rfp_text_length"] = len(all_text)

            report["rescored"] += 1

            if new_qual == "NOGO" and old_qual != "NOGO":
                report["newly_disqualified"] += 1
                report["gate_changes"].append({
                    "tender_id": manifest.get("tender_id", tender_dir.name),
                    "title": title[:80],
                    "old_verdict": old_qual,
                    "new_verdict": new_qual,
                    "reason": qualification.get("disqualification_reason", ""),
                })
                logger.info(
                    f"DISQUALIFIED: {manifest.get('tender_id', tender_dir.name)} "
                    f"({qualification.get('disqualification_reason', '')})"
                )

            # Update manifest on disk
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

    logger.info(
        f"Deep scoring: {report['processed']} processed, "
        f"{report['rescored']} rescored, "
        f"{report['newly_disqualified']} newly disqualified"
    )
    return report


# ── Standalone runner ──

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Agent 1b: RFP Document Acquisition")
    parser.add_argument("--base-dir", default=DEFAULT_BASE_DIR, help="Root sync folder")
    parser.add_argument("--max", type=int, default=20, help="Max tenders per run")
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL"), help="Database URL")
    args = parser.parse_args()

    if args.db_url:
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
        report = run_agent_1b(tenders, base_dir=args.base_dir, max_tenders=args.max)
        print(f"\nAuto: {report['auto_downloaded']}, Manual: {report['manual_required']}, "
              f"Dropped: {report['dropped_count']}")

    else:
        print("No DATABASE_URL. Running demo against PPRA page 1.")
        from scraper_ppra import scrape_ppra_requests, normalize_ppra_tender
        from scorer import score_tender

        result = scrape_ppra_requests(max_pages=1)
        qualified = []
        for raw in result["tenders"]:
            norm = normalize_ppra_tender(raw)
            score, verdict, sols, kws = score_tender(norm["title"])
            if score >= 70:
                norm.update({"score": score, "verdict": verdict, "solMatch": sols,
                             "matched": kws, "source": "PPRA"})
                qualified.append(norm)

        print(f"Qualified: {len(qualified)}")
        report = run_agent_1b(qualified, base_dir=args.base_dir, max_tenders=args.max)
        print(f"\nAuto: {report['auto_downloaded']}, Manual: {report['manual_required']}, "
              f"Dropped: {report['dropped_count']}")
