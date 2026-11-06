"""
NETS Tender Scout: Production API Server.
FastAPI backend that replaces Claude's Artifact DB with a real database.

Run:   uvicorn main:app --host 0.0.0.0 --port 8000
Docs:  http://localhost:8000/docs  (auto-generated Swagger)
"""
import os
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from models import init_db, get_db, Tender, ScanLog, Proposal, Config
from scorer import score_tender, get_solutions_list
from scraper import scrape_with_playwright, scrape_with_requests, parse_portal_date, days_remaining

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("tender-scout")

# ── Scheduler ──
scheduler = AsyncIOScheduler()


async def run_scan_job():
    """
    Scheduled job: scrape portal, score tenders, save qualified ones.
    This replaces Claude's Agent 1.
    """
    from models import SessionLocal
    db = SessionLocal()
    start = datetime.utcnow()
    logger.info("Starting scheduled scan...")

    try:
        # Scrape
        try:
            raw_tenders = await scrape_with_playwright()
        except Exception as e:
            logger.warning(f"Playwright failed ({e}), falling back to requests")
            raw_tenders = scrape_with_requests()

        total_on_portal = len(raw_tenders)
        new_count = 0
        qualified_count = 0
        open_qualified_count = 0

        for raw in raw_tenders:
            score, verdict, matched_solutions, matched_keywords = score_tender(raw["title"])

            # Only store qualified tenders (score >= 70)
            if score < 70:
                continue

            qualified_count += 1
            closing_date = parse_portal_date(raw.get("closing", ""))
            days_left = days_remaining(closing_date)
            is_open = days_left is not None and days_left >= 0

            if is_open:
                open_qualified_count += 1

            # Upsert: update if exists, create if new
            existing = db.query(Tender).filter(Tender.id == raw["id"]).first()
            if existing:
                existing.is_open = is_open
                existing.days_remaining = days_left
                existing.score = score
                existing.verdict = verdict
                existing.matched_keywords = matched_keywords
                existing.matched_solutions = matched_solutions
                existing.document_url = raw.get("doc_url") or existing.document_url
                existing.updated_at = datetime.utcnow()
            else:
                new_count += 1
                tender = Tender(
                    id=raw["id"],
                    title=raw["title"],
                    department=raw.get("department", ""),
                    advertised=raw.get("advertised", ""),
                    closing=raw.get("closing", ""),
                    closing_date=closing_date,
                    is_open=is_open,
                    days_remaining=days_left,
                    score=score,
                    verdict=verdict,
                    matched_keywords=matched_keywords,
                    matched_solutions=matched_solutions,
                    document_url=raw.get("doc_url"),
                    source_url="https://sindhbank.com.pk/tenders",
                )
                db.add(tender)

        # Log the scan
        duration = (datetime.utcnow() - start).total_seconds()
        scan_log = ScanLog(
            date=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            total_on_portal=total_on_portal,
            qualified_count=qualified_count,
            open_qualified_count=open_qualified_count,
            new_count=new_count,
            duration_seconds=duration,
            status="success",
        )
        db.add(scan_log)
        db.commit()

        logger.info(
            f"Scan complete: {total_on_portal} total, {qualified_count} qualified, "
            f"{new_count} new, {duration:.1f}s"
        )

    except Exception as e:
        logger.error(f"Scan failed: {e}")
        scan_log = ScanLog(
            date=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            status="error",
            error_message=str(e),
        )
        db.add(scan_log)
        db.commit()
    finally:
        db.close()


# ── App lifecycle ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, start scheduler. Shutdown: stop scheduler."""
    init_db()

    # Schedule the scraper: every day at 05:47 UK time (Mon-Sat)
    scan_hour = int(os.getenv("SCAN_HOUR", "5"))
    scan_minute = int(os.getenv("SCAN_MINUTE", "47"))
    scheduler.add_job(
        run_scan_job,
        "cron",
        hour=scan_hour,
        minute=scan_minute,
        day_of_week="mon-sat",
        id="daily_scan",
        timezone="Europe/London",
    )
    scheduler.start()
    logger.info(f"Scheduler started: daily scan at {scan_hour:02d}:{scan_minute:02d} UK (Mon-Sat)")

    yield

    scheduler.shutdown()
    logger.info("Scheduler stopped")


app = FastAPI(
    title="NETS Tender Scout",
    description="Presales tender intelligence for NETS International",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow the frontend (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════
#  API ENDPOINTS
#  These replace claude.use("db") calls
# ══════════════════════════════════════════════

@app.get("/api/tenders")
def list_tenders(
    open_only: bool = False,
    min_score: int = 0,
    db: Session = Depends(get_db),
):
    """List all qualified tenders. The frontend calls this on load."""
    q = db.query(Tender)
    if open_only:
        q = q.filter(Tender.is_open == True)
    if min_score > 0:
        q = q.filter(Tender.score >= min_score)
    tenders = q.order_by(Tender.score.desc()).all()

    return [
        {
            "id": t.id, "ti": t.title, "dept": t.department,
            "ad": t.advertised, "cl": t.closing,
            "open": t.is_open, "days": t.days_remaining,
            "score": t.score, "verdict": t.verdict,
            "matched": t.matched_keywords or [],
            "solMatch": t.matched_solutions or [],
            "doc": t.document_url,
        }
        for t in tenders
    ]


@app.get("/api/tenders/{tender_id}")
def get_tender(tender_id: str, db: Session = Depends(get_db)):
    """Get a single tender by ID."""
    t = db.query(Tender).filter(Tender.id == tender_id).first()
    if not t:
        raise HTTPException(404, "Tender not found")
    return {
        "id": t.id, "ti": t.title, "dept": t.department,
        "ad": t.advertised, "cl": t.closing,
        "open": t.is_open, "days": t.days_remaining,
        "score": t.score, "verdict": t.verdict,
        "matched": t.matched_keywords or [],
        "solMatch": t.matched_solutions or [],
        "doc": t.document_url,
    }


@app.get("/api/scans")
def list_scans(limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    """Recent scan history."""
    scans = db.query(ScanLog).order_by(ScanLog.id.desc()).limit(limit).all()
    return [
        {
            "date": s.date, "total_on_portal": s.total_on_portal,
            "qualified_count": s.qualified_count,
            "open_qualified_count": s.open_qualified_count,
            "new_count": s.new_count, "status": s.status,
        }
        for s in scans
    ]


@app.get("/api/proposals")
def list_proposals(db: Session = Depends(get_db)):
    """All generated proposals."""
    proposals = db.query(Proposal).order_by(Proposal.generated_at.desc()).all()
    return [
        {
            "_id": p.id, "rfp_title": p.rfp_title, "client": p.client,
            "solutions": p.solutions or [], "proposal_text": p.proposal_text,
            "proposal_words": p.proposal_words,
            "audit_score": p.audit_score, "audit_verdict": p.audit_verdict,
            "audit_requirements_met": p.audit_requirements_met,
            "audit_requirements_total": p.audit_requirements_total,
            "iterations": p.iterations, "status": p.status,
            "generated_at": p.generated_at.isoformat() if p.generated_at else "",
        }
        for p in proposals
    ]


@app.get("/api/solutions")
def list_solutions():
    """Return the NETS solution taxonomy (static data for the frontend)."""
    return get_solutions_list()


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """System health for the Settings tab."""
    tender_count = db.query(Tender).count()
    scan_count = db.query(ScanLog).count()
    proposal_count = db.query(Proposal).count()
    last_scan = db.query(ScanLog).order_by(ScanLog.id.desc()).first()
    pdf_count = db.query(Tender).filter(Tender.document_url.isnot(None)).count()

    return {
        "status": "healthy",
        "database": "connected",
        "tenders": tender_count,
        "scans": scan_count,
        "proposals": proposal_count,
        "pdfs": pdf_count,
        "last_scan": last_scan.date if last_scan else "never",
        "last_scan_status": last_scan.status if last_scan else "none",
        "scheduler_running": scheduler.running,
    }


@app.get("/api/scan/trigger")
@app.post("/api/scan/trigger")
async def trigger_scan():
    """Manually trigger a scan (for testing or on-demand refresh)."""
    asyncio.create_task(run_scan_job())
    return {"status": "scan_triggered", "message": "Scan started in background"}


@app.get("/api/seed")
def seed_demo_data(db: Session = Depends(get_db)):
    """Load demo tenders for testing."""
    from scorer import score_tender
    import json as _json
    demos = [
        {"id": "S-26080803636", "title": "Maintenance & Support of Dell Servers", "dept": "IT", "ad": "1-Aug-2026", "cl": "15-Dec-2026"},
        {"id": "S-26070703412", "title": "Supply of Cisco Network Switches & Routers", "dept": "IT", "ad": "15-Jul-2026", "cl": "20-Dec-2026"},
        {"id": "S-26090904001", "title": "Cybersecurity Assessment & Firewall Deployment", "dept": "IT", "ad": "5-Sep-2026", "cl": "25-Dec-2026"},
        {"id": "S-26100105523", "title": "Data Centre UPS & Power Infrastructure Upgrade", "dept": "IT", "ad": "1-Oct-2026", "cl": "30-Dec-2026"},
        {"id": "S-26101005890", "title": "Annual Maintenance Contract for Storage SAN", "dept": "IT", "ad": "10-Oct-2026", "cl": "10-Jan-2027"},
        {"id": "S-26110506401", "title": "Cloud Migration & Virtualization Services", "dept": "IT", "ad": "5-Nov-2026", "cl": "20-Jan-2027"},
        {"id": "S-26111006555", "title": "Managed IT Support Services (NOC Operations)", "dept": "IT", "ad": "10-Nov-2026", "cl": "25-Jan-2027"},
        {"id": "S-26111506700", "title": "Supply of WiFi Access Points & Wireless Network", "dept": "IT", "ad": "15-Nov-2026", "cl": "30-Jan-2027"},
        {"id": "S-26112006801", "title": "Structured Cabling for New Branch Offices", "dept": "Admin", "ad": "20-Nov-2026", "cl": "5-Feb-2027"},
        {"id": "S-26112506900", "title": "Supply & Installation of Solar Power System", "dept": "Admin", "ad": "25-Nov-2026", "cl": "10-Feb-2027"},
    ]
    added = 0
    for d in demos:
        if db.query(Tender).filter(Tender.id == d["id"]).first():
            continue
        score, verdict, solutions, keywords = score_tender(d["title"])
        if score < 70:
            continue
        tender = Tender(id=d["id"], title=d["title"], department=d["dept"], advertised=d["ad"], closing=d["cl"], is_open=True, days_remaining=60, score=score, verdict=verdict, matched_keywords=keywords, matched_solutions=solutions, source_url="https://sindhbank.com.pk/tenders")
        db.add(tender)
        added += 1
    scan = ScanLog(date=datetime.utcnow().strftime("%Y-%m-%d %H:%M"), total_on_portal=867, qualified_count=added, open_qualified_count=added, new_count=added, duration_seconds=0.1, status="success")
    db.add(scan)
    db.commit()
    return {"status": "seeded", "tenders_added": added}
# ── Serve the frontend ──

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets") if os.path.isdir(os.path.join(FRONTEND_DIR, "assets")) else None

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
