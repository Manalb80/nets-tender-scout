"""
RFPSyncEngine: Production-grade two-tier RFP acquisition with OCR fallback.

Replaces the single-tier HTTP-only downloader with:
  Tier 1: Direct HTTP with session cookies, user-agent rotation, retries
  Tier 2: Playwright headless browser for JS-rendered portals and login walls
  OCR:    Tesseract fallback for scanned/image-only PDFs

All storage is environment-configurable (no hardcoded D:\\ paths).
State updates use the Manager Agent's pipeline/ schema.

Usage:
    from backend.rfp_sync_engine import RFPSyncEngine
    engine = RFPSyncEngine()
    result = engine.acquire(tender_id, detail_url, portal="PPRA")

Environment variables (see .env.example):
    RFP_STORAGE_PATH       Local or mounted path (default: ./data/rfps)
    SHAREPOINT_UPLOAD       "true" to also push to SharePoint after download
    OCR_ENABLED            "true" to enable Tesseract OCR (default: true)
    OCR_MIN_CHARS_PER_PAGE  Threshold below which OCR triggers (default: 50)
    PLAYWRIGHT_HEADLESS    "true" (default) or "false" for debugging
"""

import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rfp_sync_engine")

# ---------------------------------------------------------------------------
# Configuration (all from environment; zero hardcoded paths)
# ---------------------------------------------------------------------------
STORAGE_PATH = os.getenv("RFP_STORAGE_PATH", "./data/rfps")
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"
OCR_MIN_CHARS_PER_PAGE = int(os.getenv("OCR_MIN_CHARS_PER_PAGE", "50"))
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
SHAREPOINT_UPLOAD = os.getenv("SHAREPOINT_UPLOAD", "false").lower() == "true"

# User-agent rotation pool (Tier 1)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# HTTP status codes that trigger Tier 2 escalation
TIER2_TRIGGER_CODES = {401, 403, 404, 407, 429, 503}

# Acquisition status values (must match Manager Agent states)
STATUS_AUTO = "AUTO_DOWNLOADED"
STATUS_HEADLESS = "AUTO_DOWNLOADED_HEADLESS"
STATUS_OCR = "OCR_PROCESSED"
STATUS_MANUAL = "MANUAL_DOWNLOAD_REQUIRED"
STATUS_FAILED = "ACQUISITION_FAILED"


# ---------------------------------------------------------------------------
# Tier 1: Direct HTTP acquisition
# ---------------------------------------------------------------------------
class Tier1HTTP:
    """Standard HTTP GET with session management, rotation, and retry."""

    def __init__(self):
        import requests
        self.session = requests.Session()
        self._rotate_ua()

    def _rotate_ua(self):
        ua = random.choice(USER_AGENTS)
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def download(self, url: str, dest: Path, max_retries: int = 2) -> dict:
        """
        Attempt direct HTTP download.
        Returns {success, status_code, bytes, error, tier}.
        """
        for attempt in range(max_retries + 1):
            try:
                self._rotate_ua()
                resp = self.session.get(url, stream=True, timeout=60, allow_redirects=True)

                if resp.status_code in TIER2_TRIGGER_CODES:
                    return {
                        "success": False,
                        "status_code": resp.status_code,
                        "bytes": 0,
                        "error": f"HTTP {resp.status_code}: escalate to Tier 2",
                        "tier": 1,
                        "escalate": True,
                    }

                if resp.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(2 * (attempt + 1))
                        continue
                    return {
                        "success": False,
                        "status_code": resp.status_code,
                        "bytes": 0,
                        "error": f"HTTP {resp.status_code} after {max_retries + 1} attempts",
                        "tier": 1,
                        "escalate": False,
                    }

                # Check content type
                ct = resp.headers.get("content-type", "")
                if "html" in ct and "pdf" not in url.lower():
                    # Might be a login page or JS-rendered content
                    body = resp.content[:2000]
                    if b"login" in body.lower() or b"sign in" in body.lower() or b"password" in body.lower():
                        return {
                            "success": False, "status_code": 200, "bytes": 0,
                            "error": "Login page detected in response body",
                            "tier": 1, "escalate": True,
                        }

                # Write file
                total = 0
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        if chunk:
                            f.write(chunk)
                            total += len(chunk)

                if total < 100:
                    dest.unlink(missing_ok=True)
                    return {
                        "success": False, "status_code": 200, "bytes": total,
                        "error": f"File too small ({total} bytes); likely blocked",
                        "tier": 1, "escalate": True,
                    }

                # Verify PDF signature
                with open(dest, "rb") as f:
                    header = f.read(5)
                if header != b"%PDF-":
                    logger.warning(f"Tier 1: not a valid PDF ({dest.name}); may be HTML redirect")
                    dest.unlink(missing_ok=True)
                    return {
                        "success": False, "status_code": 200, "bytes": total,
                        "error": "Downloaded file is not a PDF (wrong magic bytes)",
                        "tier": 1, "escalate": True,
                    }

                logger.info(f"Tier 1 OK: {total:,} bytes -> {dest.name}")
                return {"success": True, "status_code": 200, "bytes": total, "error": None, "tier": 1, "escalate": False}

            except Exception as e:
                if attempt < max_retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                return {
                    "success": False, "status_code": 0, "bytes": 0,
                    "error": f"Tier 1 exception: {str(e)[:300]}",
                    "tier": 1, "escalate": True,
                }

        return {"success": False, "status_code": 0, "bytes": 0, "error": "Exhausted retries", "tier": 1, "escalate": True}

    def head_check(self, url: str) -> dict:
        """Quick HEAD check to see if a URL is publicly accessible."""
        try:
            resp = self.session.head(url, timeout=15, allow_redirects=True)
            return {"accessible": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as e:
            return {"accessible": False, "status_code": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# Tier 2: Playwright headless browser
# ---------------------------------------------------------------------------
class Tier2Playwright:
    """Headless browser fallback for JS-rendered portals and login walls."""

    def __init__(self):
        self._browser = None
        self._pw = None

    def _ensure_browser(self):
        if self._browser:
            return
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        logger.info("Tier 2: Playwright browser launched")

    def download(self, url: str, dest: Path, timeout_ms: int = 30000) -> dict:
        """
        Navigate to the URL in a headless browser and capture the PDF download.
        Returns {success, bytes, error, tier}.
        """
        try:
            self._ensure_browser()
            context = self._browser.new_context(accept_downloads=True)
            page = context.new_page()

            # Set up download capture
            downloaded_path = None

            def on_download(download):
                nonlocal downloaded_path
                downloaded_path = download.path()

            page.on("download", on_download)

            # Navigate
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)

            # Wait briefly for any auto-triggered download
            page.wait_for_timeout(3000)

            # If no auto-download, look for PDF links and click them
            if not downloaded_path:
                pdf_links = page.query_selector_all('a[href*=".pdf"], a[href*="pdf?"], a[href*="download"]')
                for link in pdf_links[:3]:
                    try:
                        with page.expect_download(timeout=10000) as dl_info:
                            link.click()
                        download = dl_info.value
                        downloaded_path = download.path()
                        if downloaded_path:
                            break
                    except Exception:
                        continue

            context.close()

            if downloaded_path and Path(downloaded_path).exists():
                import shutil
                shutil.move(str(downloaded_path), str(dest))
                size = dest.stat().st_size
                logger.info(f"Tier 2 OK: {size:,} bytes -> {dest.name}")
                return {"success": True, "bytes": size, "error": None, "tier": 2, "escalate": False}
            else:
                # Check if the page itself was a PDF (some portals serve inline)
                content = page.content() if not context.pages else ""
                return {
                    "success": False, "bytes": 0,
                    "error": "Playwright: no downloadable PDF found on the page",
                    "tier": 2, "escalate": False,
                }

        except Exception as e:
            return {
                "success": False, "bytes": 0,
                "error": f"Tier 2 exception: {str(e)[:300]}",
                "tier": 2, "escalate": False,
            }

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._browser = None
        self._pw = None


# ---------------------------------------------------------------------------
# OCR pipeline for scanned PDFs
# ---------------------------------------------------------------------------
class OCRPipeline:
    """Extract text from scanned/image PDFs using Tesseract OCR."""

    @staticmethod
    def needs_ocr(pdf_path: Path) -> bool:
        """Check if a PDF has too little text (likely scanned)."""
        if not OCR_ENABLED:
            return False
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            total_chars = 0
            total_pages = min(doc.page_count, 10)  # sample first 10 pages
            for i in range(total_pages):
                text = doc[i].get_text()
                total_chars += len(text.strip())
            doc.close()
            chars_per_page = total_chars / max(total_pages, 1)
            needs = chars_per_page < OCR_MIN_CHARS_PER_PAGE
            if needs:
                logger.info(f"OCR needed: {pdf_path.name} has {chars_per_page:.0f} chars/page (threshold: {OCR_MIN_CHARS_PER_PAGE})")
            return needs
        except ImportError:
            logger.warning("PyMuPDF not installed; cannot check for OCR need")
            return False
        except Exception as e:
            logger.warning(f"OCR check failed for {pdf_path.name}: {e}")
            return False

    @staticmethod
    def run_ocr(pdf_path: Path) -> str:
        """Convert PDF pages to images, run Tesseract, return text."""
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError as e:
            logger.error(f"OCR dependencies missing: {e}. Install: pip install pdf2image pytesseract")
            return ""

        try:
            images = convert_from_path(str(pdf_path), dpi=300, first_page=1, last_page=30)
            all_text = []
            for i, img in enumerate(images):
                text = pytesseract.image_to_string(img, lang="eng")
                all_text.append(text)
                logger.debug(f"OCR page {i+1}: {len(text)} chars")
            full = "\n\n".join(all_text)
            logger.info(f"OCR complete: {pdf_path.name}, {len(full)} chars from {len(images)} pages")
            return full
        except Exception as e:
            logger.error(f"OCR failed for {pdf_path.name}: {e}")
            return ""


# ---------------------------------------------------------------------------
# Text extraction (multi-strategy)
# ---------------------------------------------------------------------------
def extract_text(pdf_path: Path, max_pages: int = 30) -> tuple[str, str]:
    """
    Extract text from a PDF. Returns (text, method).
    method is one of: "pymupdf", "pdfminer", "ocr", "none".
    """
    text = ""

    # Strategy 1: PyMuPDF
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        pages = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pages.append(page.get_text())
        doc.close()
        text = "\n".join(pages)
        if len(text.strip()) > 100:
            return text, "pymupdf"
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"PyMuPDF failed: {e}")

    # Strategy 2: pdfminer
    try:
        from pdfminer.high_level import extract_text as pm_extract
        text = pm_extract(str(pdf_path), maxpages=max_pages)
        if len(text.strip()) > 100:
            return text, "pdfminer"
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"pdfminer failed: {e}")

    # Strategy 3: OCR
    if OCR_ENABLED and OCRPipeline.needs_ocr(pdf_path):
        ocr_text = OCRPipeline.run_ocr(pdf_path)
        if len(ocr_text.strip()) > 100:
            return ocr_text, "ocr"

    return text, "none" if len(text.strip()) < 50 else "pymupdf"


# ---------------------------------------------------------------------------
# RFPSyncEngine: the main class
# ---------------------------------------------------------------------------
class RFPSyncEngine:
    """
    Two-tier RFP acquisition engine with OCR fallback.

    Usage:
        engine = RFPSyncEngine()
        result = engine.acquire("PPRA-TS0000017824E", "https://epms.ppra.gov.pk/...", portal="PPRA")
        engine.close()  # release Playwright resources
    """

    def __init__(self, storage_path: str | None = None):
        self.storage = Path(storage_path or STORAGE_PATH)
        self.storage.mkdir(parents=True, exist_ok=True)
        self.tier1 = Tier1HTTP()
        self.tier2: Tier2Playwright | None = None  # lazy init
        logger.info(f"RFPSyncEngine initialized. Storage: {self.storage}")

    def _ensure_tier2(self) -> Tier2Playwright:
        if not self.tier2:
            self.tier2 = Tier2Playwright()
        return self.tier2

    def acquire(self, tender_id: str, url: str, portal: str = "PPRA") -> dict:
        """
        Full acquisition pipeline for one tender.

        Returns a result dict with:
            tender_id, acq_status, tier_used, file_path, text_length,
            text_method, ocr_used, error, duration_s
        """
        t0 = time.time()
        tender_dir = self.storage / portal.upper().replace(" ", "_") / tender_id
        tender_dir.mkdir(parents=True, exist_ok=True)
        dest = tender_dir / "RFP.pdf"

        result = {
            "tender_id": tender_id,
            "portal": portal,
            "url": url,
            "acq_status": STATUS_FAILED,
            "tier_used": 0,
            "file_path": None,
            "file_bytes": 0,
            "text_length": 0,
            "text_method": "none",
            "ocr_used": False,
            "error": None,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "duration_s": 0,
        }

        # ── Tier 1: Direct HTTP ──
        logger.info(f"[{tender_id}] Tier 1: attempting direct HTTP download")
        t1 = self.tier1.download(url, dest)

        if t1["success"]:
            result["acq_status"] = STATUS_AUTO
            result["tier_used"] = 1
            result["file_path"] = str(dest)
            result["file_bytes"] = t1["bytes"]
        elif t1.get("escalate"):
            # ── Tier 2: Playwright headless ──
            logger.info(f"[{tender_id}] Tier 2: escalating to headless browser ({t1['error']})")
            pw = self._ensure_tier2()
            t2 = pw.download(url, dest)

            if t2["success"]:
                result["acq_status"] = STATUS_HEADLESS
                result["tier_used"] = 2
                result["file_path"] = str(dest)
                result["file_bytes"] = t2["bytes"]
            else:
                result["error"] = f"Tier 1: {t1['error']}; Tier 2: {t2['error']}"
                result["acq_status"] = STATUS_MANUAL
                logger.warning(f"[{tender_id}] Both tiers failed: {result['error']}")
        else:
            result["error"] = t1["error"]
            result["acq_status"] = STATUS_MANUAL

        # ── Text extraction + OCR fallback ──
        if result["file_path"] and dest.exists():
            text, method = extract_text(dest)

            if method == "none" and OCR_ENABLED:
                logger.info(f"[{tender_id}] Text extraction returned nothing; trying OCR")
                ocr_text = OCRPipeline.run_ocr(dest)
                if len(ocr_text.strip()) > 100:
                    text = ocr_text
                    method = "ocr"
                    result["ocr_used"] = True
                    result["acq_status"] = STATUS_OCR

            result["text_length"] = len(text)
            result["text_method"] = method

            # Save extracted text alongside the PDF
            if text:
                text_path = tender_dir / "rfp_text.txt"
                text_path.write_text(text, encoding="utf-8")
                result["text_file"] = str(text_path)

        # ── Write manifest ──
        result["duration_s"] = round(time.time() - t0, 2)
        manifest_path = tender_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        logger.info(
            f"[{tender_id}] Done: {result['acq_status']} "
            f"(tier {result['tier_used']}, {result['text_length']} chars via {result['text_method']}, "
            f"{result['duration_s']}s)"
        )
        return result

    def acquire_batch(self, tenders: list[dict], delay: float = 2.0) -> list[dict]:
        """
        Acquire RFPs for a list of tenders.
        Each tender dict must have: id, detail_url (or doc_url), source.
        """
        results = []
        for i, t in enumerate(tenders):
            tid = t.get("id", t.get("tender_id", ""))
            url = t.get("detail_url") or t.get("doc_url") or t.get("detailUrl", "")
            portal = t.get("source", t.get("source_portal", "PPRA"))

            if not url:
                results.append({
                    "tender_id": tid, "acq_status": STATUS_MANUAL,
                    "error": "No URL available for download",
                })
                continue

            try:
                r = self.acquire(tid, url, portal)
                results.append(r)
            except Exception as e:
                logger.error(f"[{tid}] Acquisition error: {e}")
                results.append({
                    "tender_id": tid, "acq_status": STATUS_FAILED,
                    "error": str(e)[:500],
                })

            if i < len(tenders) - 1:
                time.sleep(delay)

        return results

    def close(self):
        """Release Playwright browser resources."""
        if self.tier2:
            self.tier2.close()
            self.tier2 = None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")

    ap = argparse.ArgumentParser(description="RFPSyncEngine: Two-tier RFP acquisition")
    ap.add_argument("url", nargs="?", help="URL to download (single tender mode)")
    ap.add_argument("--tender-id", default="TEST-001", help="Tender ID for the download")
    ap.add_argument("--portal", default="PPRA", help="Portal name")
    ap.add_argument("--storage", default=STORAGE_PATH, help="Storage path")
    ap.add_argument("--no-ocr", action="store_true", help="Disable OCR")
    args = ap.parse_args()

    if args.no_ocr:
        OCR_ENABLED = False

    engine = RFPSyncEngine(storage_path=args.storage)

    if args.url:
        result = engine.acquire(args.tender_id, args.url, args.portal)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python rfp_sync_engine.py <url> --tender-id PPRA-TS001 --portal PPRA")
        print("Or import and use: from backend.rfp_sync_engine import RFPSyncEngine")

    engine.close()
