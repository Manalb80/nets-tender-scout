"""
Manager Agent (Orchestrator) for NETS Presales Engine.
Server-side twin of the in-page Manager in frontend/index.html.

This is the production backend. It polls the Firestore database (or any DB
that exposes the same pipeline/ collection), reads every tender's
pipeline_status, and dispatches the correct worker. It runs as a long-lived
process (systemd, Docker, or a scheduled task on Render).

Architecture:
    Manager (this file, one process, every 5 min)
        |
        +-- Agent 1: Scout (scraper.py + scorer.py, separate cron)
        +-- Agent 1b: Download RFP (downloader.py, separate cron)
        +-- Agent 2: Analyse (ai_engine.py: summary, grading, compliance, boq)
        +-- Agent 3: Writer (agent3_writer.py + rag_engine.py)
        +-- Agent 4/5: QA (agent4_technical.py, agent5_regulatory.py)
        +-- Agent 6: KB growth (scripts/kb/agent6_rebuild_kb.py)
        |
        +-- SharePoint Graph API (folder provisioning, file detection)
        |
        Central DB (Firestore pipeline/ collection)

Principles:
    1. State-driven, not sequential. The Manager never assumes which step comes
       after which; it reads the state and dispatches.
    2. Atomic locking. Before dispatching, the Manager writes a processing_*
       state. A concurrent poll that sees processing_* skips the tender.
    3. Fault tolerance. A worker crash increments retry_count. At 3 retries,
       the tender is escalated. The Manager itself never crashes.
    4. HITL gates. Five states require human action; the Manager waits.
    5. SharePoint first. No local D:\\ paths. All file storage routes through
       the Microsoft Graph API to the corporate SharePoint repository.

Usage:
    python -m backend.manager                    # run one cycle
    python -m backend.manager --loop             # poll every 5 min
    python -m backend.manager --loop --interval 300  # custom interval
    python -m backend.manager --migrate          # stamp pipeline_status on old tenders

Environment variables:
    FIRESTORE_PROJECT      GCP project (or set GOOGLE_APPLICATION_CREDENTIALS)
    SHAREPOINT_TENANT      e.g. netsinternational
    SHAREPOINT_SITE_ID     Microsoft Graph site ID
    SHAREPOINT_DRIVE_ID    Drive ID for the document library
    SHAREPOINT_RFP_ROOT    Folder path, e.g. "Digitisation/NETS_Discovery_Incoming/RFPs"
    GRAPH_CLIENT_ID        Azure AD app registration client ID
    GRAPH_CLIENT_SECRET    Azure AD app registration client secret
    GRAPH_TENANT_ID        Azure AD tenant ID
    ANTHROPIC_API_KEY      For the AI workers (Claude API)
"""

import argparse
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("manager")

# ---------------------------------------------------------------------------
# States (must match frontend MGR_STATES exactly)
# ---------------------------------------------------------------------------
STATES = {
    "DISCOVERED":          "discovered",
    "QUALIFIED_GO":        "qualified_go",
    "QUALIFIED_NOGO":      "qualified_nogo",
    "RFP_PENDING":         "rfp_pending",
    "RFP_READY":           "rfp_ready",
    "PROCESSING_ANALYSIS": "processing_analysis",
    "ANALYSING":           "analysing",
    "ANALYSED":            "analysed",
    "AWAITING_DECISION":   "awaiting_decision",
    "DECIDED_BID":         "decided_bid",
    "DECIDED_NOBID":       "decided_nobid",
    "DECIDED_HOLD":        "decided_hold",
    "PROCESSING_WRITER":   "processing_writer",
    "WRITING":             "writing",
    "WRITTEN":             "written",
    "PROCESSING_REVIEW":   "processing_review",
    "REVIEWING":           "reviewing",
    "REVIEWED":            "reviewed",
    "QA_FAILED":           "qa_failed",
    "APPROVED":            "approved",
    "PROCESSING_KB":       "processing_kb",
    "KB_ADDED":            "kb_added",
    "SUBMITTED":           "submitted",
    "WON":                 "won",
    "LOST":                "lost",
    "FAILED":              "failed",
    "ESCALATED":           "escalated",
}

MAX_RETRIES = 3
HITL_STATES = {"rfp_pending", "analysed", "decided_hold", "written", "reviewed", "qa_failed", "escalated"}
TERMINAL_STATES = {"qualified_nogo", "decided_nobid", "kb_added", "submitted", "won", "lost"}
LOCK_STATES = {"processing_analysis", "processing_writer", "processing_review", "processing_kb"}


# ---------------------------------------------------------------------------
# Database adapter (Firestore; swap for PostgreSQL/Supabase in production)
# ---------------------------------------------------------------------------
class FirestoreDB:
    """Thin wrapper around google-cloud-firestore."""

    def __init__(self):
        from google.cloud import firestore
        self.db = firestore.Client()

    def get_all_pipeline_docs(self) -> list[dict]:
        return [
            {**doc.to_dict(), "_id": doc.id}
            for doc in self.db.collection("pipeline").stream()
        ]

    def get_all_tenders(self) -> list[dict]:
        return [
            {**doc.to_dict(), "_id": doc.id}
            for doc in self.db.collection("tenders").stream()
        ]

    def get_analysis(self, tender_id: str) -> dict:
        doc = self.db.collection("rfp_analysis").document(tender_id).get()
        return doc.to_dict() if doc.exists else {}

    def set_pipeline(self, tender_id: str, doc: dict):
        self.db.collection("pipeline").document(tender_id).set(doc)

    def update_analysis(self, tender_id: str, patch: dict):
        ref = self.db.collection("rfp_analysis").document(tender_id)
        try:
            ref.update(patch)
        except Exception:
            ref.set(patch)

    def log(self, entry: dict):
        self.db.collection("mgr_log").add(entry)

    def set_health(self, health: dict):
        self.db.collection("config").document("mgr_health").set(health)


# ---------------------------------------------------------------------------
# SharePoint integration (Microsoft Graph API)
# ---------------------------------------------------------------------------
class SharePointClient:
    """Provision folders and detect new files via Microsoft Graph API."""

    def __init__(self):
        self.tenant_id = os.environ.get("GRAPH_TENANT_ID", "")
        self.client_id = os.environ.get("GRAPH_CLIENT_ID", "")
        self.client_secret = os.environ.get("GRAPH_CLIENT_SECRET", "")
        self.site_id = os.environ.get("SHAREPOINT_SITE_ID", "")
        self.drive_id = os.environ.get("SHAREPOINT_DRIVE_ID", "")
        self.rfp_root = os.environ.get("SHAREPOINT_RFP_ROOT", "Digitisation/NETS_Discovery_Incoming/RFPs")
        self._token = None
        self._token_expires = 0

    @property
    def configured(self) -> bool:
        return bool(self.tenant_id and self.client_id and self.client_secret and self.site_id)

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        import requests
        resp = requests.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def provision_folder(self, tender_id: str) -> str:
        """Create /RFPs/<tender_id>/ on SharePoint. Returns the folder URL."""
        import requests
        url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/root:/{self.rfp_root}/{tender_id}:/children"
        # Creating a folder item
        resp = requests.post(url, headers=self._headers(), json={
            "name": tender_id,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        })
        if resp.status_code == 409:
            log.info(f"SharePoint folder already exists for {tender_id}")
        elif resp.status_code >= 400:
            log.warning(f"SharePoint folder creation failed: {resp.status_code} {resp.text[:200]}")
        folder_url = f"https://{os.environ.get('SHAREPOINT_TENANT', 'netsinternational')}.sharepoint.com/sites/{self.site_id}/{self.rfp_root}/{tender_id}"
        return folder_url

    def check_for_uploads(self, tender_id: str) -> list[dict]:
        """List files in /RFPs/<tender_id>/. Returns [{name, size, lastModified}]."""
        import requests
        url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/root:/{self.rfp_root}/{tender_id}:/children"
        resp = requests.get(url, headers=self._headers())
        if resp.status_code != 200:
            return []
        items = resp.json().get("value", [])
        return [
            {"name": i["name"], "size": i.get("size", 0), "lastModified": i.get("lastModifiedDateTime")}
            for i in items if "file" in i
        ]


# ---------------------------------------------------------------------------
# State machine helpers
# ---------------------------------------------------------------------------
def is_locked(state: str) -> bool:
    return state in LOCK_STATES


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_state_doc(tender: dict, analysis: dict, new_state: str, prev_doc: dict | None = None, extra: dict | None = None) -> dict:
    """Build the canonical state document (matching the frontend schema)."""
    prev = prev_doc or {}
    decision = analysis.get("decision", {})
    proposal_sections = (analysis.get("proposal") or {}).get("sections", {})
    review = analysis.get("review", {})

    doc: dict[str, Any] = {
        "tender_id": tender.get("_id") or tender.get("id", ""),
        "title": tender.get("ti", prev.get("title", "")),
        "portal": tender.get("source_portal") or tender.get("source", prev.get("portal", "Sindh Bank")),
        "current_state": new_state,
        "previous_state": prev.get("current_state"),
        "last_updated": now_iso(),
        "retry_count": (extra or {}).get("pipeline_retries", prev.get("retry_count", 0)),
        "error_log": None,
        "failed_step": None,
        "escalated_at": None,
        "sharepoint_folder_url": prev.get("sharepoint_folder_url", ""),
        "metadata": {
            "score": tender.get("score", 0),
            "deadline": tender.get("cl", ""),
            "assignee": decision.get("owner") or decision.get("sales_owner") or tender.get("assignee", "Unassigned"),
            "go_nogo": decision.get("bid_decision") or tender.get("goNogo", "Pending"),
            "qualification_verdict": tender.get("qualVerdict", "GO"),
            "solution_areas": [s.get("name", s.get("id", "")) for s in (tender.get("solMatch") or [])][:8],
            "source_portal": tender.get("source_portal") or tender.get("source", "Sindh Bank"),
            "detail_url": tender.get("detail_url") or tender.get("detailUrl", ""),
        },
        "analyses": {
            "summary": {"done": bool(analysis.get("summary")), "at": analysis.get("summary_at")},
            "grading": {
                "done": bool(analysis.get("grading")), "at": analysis.get("grading_at"),
                "verdict": (analysis.get("grading") or {}).get("verdict"),
                "readiness": (analysis.get("grading") or {}).get("readiness_pct"),
            },
            "compliance": {
                "done": bool(analysis.get("compliance")), "at": analysis.get("compliance_at"),
                "have": (analysis.get("compliance") or {}).get("have_count", 0),
                "missing": (analysis.get("compliance") or {}).get("missing_count", 0),
            },
            "boq": {
                "done": bool(analysis.get("boq")), "at": analysis.get("boq_at"),
                "total_pkr": (analysis.get("boq") or {}).get("grand_total_pkr"),
            },
        },
        "proposal": {
            "sections_written": sum(1 for v in proposal_sections.values() if v.get("body_md")),
            "sections_approved": sum(1 for v in proposal_sections.values() if v.get("status") == "approved"),
            "sections_total": 13,
        },
        "review": {
            "technical_score": (review.get("technical") or {}).get("score"),
            "regulatory_score": (review.get("regulatory") or {}).get("score"),
            "rounds": review.get("rounds", 0),
            "status": review.get("status"),
        },
        "kb": {
            "added": bool(analysis.get("kb_added_at")),
            "added_at": analysis.get("kb_added_at"),
            "chunk_count": len(analysis.get("kb_chunk_ids", [])),
        },
        "state_history": (prev.get("state_history") or []) + (
            [{"from": prev.get("current_state"), "to": new_state, "at": now_iso()}]
            if prev.get("current_state") and prev.get("current_state") != new_state else []
        ),
    }

    # Overlay error fields
    if extra:
        if "pipeline_last_error" in extra:
            doc["error_log"] = {"step": extra.get("pipeline_failed_step"), "message": extra["pipeline_last_error"], "at": now_iso()}
            doc["failed_step"] = extra.get("pipeline_failed_step")
        if "pipeline_escalated_at" in extra:
            doc["escalated_at"] = extra["pipeline_escalated_at"]
        if "pipeline_retries" in extra:
            doc["retry_count"] = extra["pipeline_retries"]

    # Trim history to last 20
    doc["state_history"] = doc["state_history"][-20:]
    return doc


# ---------------------------------------------------------------------------
# Manager cycle
# ---------------------------------------------------------------------------
class Manager:
    def __init__(self, db: FirestoreDB, sp: SharePointClient | None = None):
        self.db = db
        self.sp = sp
        self.cycle = 0

    def _log(self, tender_id: str | None, msg: str, level: str = "info"):
        entry = {"at": now_iso(), "tender": tender_id or "SYSTEM", "msg": msg, "level": level, "cycle": self.cycle}
        getattr(log, level, log.info)(f"[{tender_id or 'SYS'}] {msg}")
        try:
            self.db.log(entry)
        except Exception:
            pass

    def set_status(self, tender: dict, new_state: str, extra: dict | None = None):
        tid = tender.get("_id") or tender.get("id", "")
        analysis = self.db.get_analysis(tid)
        prev_doc = None
        try:
            prev_doc = next((d for d in self._pipeline_cache if d.get("tender_id") == tid), None)
        except Exception:
            pass
        doc = build_state_doc(tender, analysis, new_state, prev_doc, extra)
        self.db.set_pipeline(tid, doc)
        self.db.update_analysis(tid, {"pipeline_status": new_state, "pipeline_updated_at": doc["last_updated"]})
        self._log(tid, f"{'State: ' + (doc.get('previous_state') or '?') + ' -> ' if doc.get('previous_state') else 'State -> '}{new_state}")
        return doc

    def record_failure(self, tender: dict, step: str, error: Exception):
        tid = tender.get("_id") or tender.get("id", "")
        analysis = self.db.get_analysis(tid)
        retries = analysis.get("pipeline_retries", 0) + 1
        msg = str(error)[:500]
        if retries >= MAX_RETRIES:
            self.set_status(tender, STATES["ESCALATED"], {
                "pipeline_retries": retries, "pipeline_last_error": msg,
                "pipeline_failed_step": step, "pipeline_escalated_at": now_iso(),
            })
            self._log(tid, f"ESCALATED after {retries} retries at '{step}': {msg}", "error")
        else:
            self.set_status(tender, STATES["FAILED"], {
                "pipeline_retries": retries, "pipeline_last_error": msg, "pipeline_failed_step": step,
            })
            self._log(tid, f"FAILED (retry {retries}/{MAX_RETRIES}) at '{step}': {msg}", "warning")

    def run_cycle(self):
        self.cycle += 1
        t0 = time.time()
        self._log(None, f"=== Cycle #{self.cycle} started ===")

        tenders = self.db.get_all_tenders()
        self._pipeline_cache = self.db.get_all_pipeline_docs()
        pipeline_map = {d["tender_id"]: d for d in self._pipeline_cache if "tender_id" in d}

        dispatched = 0
        skipped = 0
        hitl = 0
        errors = 0

        for t in tenders:
            tid = t.get("_id") or t.get("id", "")
            if not tid:
                continue

            # Read state from pipeline doc, or infer
            pdoc = pipeline_map.get(tid, {})
            state = pdoc.get("current_state") or self._infer_state(t)

            # Skip locked, terminal, or HITL tenders
            if is_locked(state):
                self._log(tid, f"Locked ({state}), skipping")
                skipped += 1
                continue
            if state in TERMINAL_STATES:
                skipped += 1
                continue
            if state in HITL_STATES:
                hitl += 1
                continue

            try:
                action = self._route(t, state, pdoc)
                if action == "dispatched":
                    dispatched += 1
                elif action == "hitl":
                    hitl += 1
                else:
                    skipped += 1
            except Exception as e:
                self._log(tid, f"Cycle error: {e}", "error")
                traceback.print_exc()
                errors += 1

        elapsed = round(time.time() - t0, 2)
        health = {
            "cycle": self.cycle, "elapsed_s": elapsed,
            "total_tenders": len(tenders), "dispatched": dispatched,
            "skipped": skipped, "awaiting_human": hitl, "errors": errors,
            "at": now_iso(),
        }
        self._log(None, f"=== Cycle #{self.cycle} done in {elapsed}s: dispatched={dispatched} hitl={hitl} errors={errors} ===")
        try:
            self.db.set_health(health)
        except Exception:
            pass
        return health

    def _route(self, tender: dict, state: str, pdoc: dict) -> str:
        """Route one tender based on its state. Returns 'dispatched', 'hitl', or 'skipped'."""
        tid = tender.get("_id") or tender.get("id", "")
        analysis = self.db.get_analysis(tid)

        if state == STATES["DISCOVERED"]:
            return "skipped"

        if state == STATES["QUALIFIED_GO"]:
            if analysis.get("rfpText"):
                self.set_status(tender, STATES["RFP_READY"])
                return "dispatched"
            # Check SharePoint for uploaded files
            if self.sp and self.sp.configured:
                files = self.sp.check_for_uploads(tid)
                if files:
                    self._log(tid, f"SharePoint has {len(files)} file(s); TODO: extract text")
                    # Future: extract text, set rfp_ready
            self.set_status(tender, STATES["RFP_PENDING"])
            return "hitl"

        if state == STATES["RFP_READY"]:
            if not analysis.get("rfpText"):
                return "skipped"
            # Atomic lock, then dispatch analyses
            self.set_status(tender, STATES["PROCESSING_ANALYSIS"])
            try:
                self._run_analyses(tid, analysis)
                self.set_status(tender, STATES["ANALYSED"])
            except Exception as e:
                self.record_failure(tender, "analysis", e)
            return "dispatched"

        if state == STATES["ANALYSING"]:
            if all(analysis.get(k) for k in ("summary", "grading", "compliance", "boq")):
                self.set_status(tender, STATES["ANALYSED"])
                return "dispatched"
            return "skipped"

        if state == STATES["DECIDED_BID"]:
            self.set_status(tender, STATES["PROCESSING_WRITER"])
            try:
                self._run_writer(tid, analysis)
                self.set_status(tender, STATES["WRITTEN"])
            except Exception as e:
                self.record_failure(tender, "writer", e)
            return "dispatched"

        if state == STATES["WRITING"]:
            return "skipped"

        if state == STATES["APPROVED"]:
            if not analysis.get("kb_added_at"):
                self.set_status(tender, STATES["PROCESSING_KB"])
                try:
                    self._run_kb_add(tid)
                    self.set_status(tender, STATES["KB_ADDED"])
                except Exception as e:
                    self.record_failure(tender, "kb_add", e)
                return "dispatched"
            self.set_status(tender, STATES["KB_ADDED"])
            return "skipped"

        if state == STATES["FAILED"]:
            retries = analysis.get("pipeline_retries", 0)
            if retries < MAX_RETRIES:
                failed_step = analysis.get("pipeline_failed_step", "")
                self._log(tid, f"Retrying failed step: {failed_step}")
                rollback = {
                    "analysis": STATES["RFP_READY"],
                    "writer": STATES["DECIDED_BID"],
                    "review": STATES["WRITTEN"],
                    "kb_add": STATES["APPROVED"],
                }
                for prefix, target in rollback.items():
                    if prefix in failed_step:
                        self.set_status(tender, target)
                        return "dispatched"
            self.set_status(tender, STATES["ESCALATED"])
            return "hitl"

        return "skipped"

    def _infer_state(self, tender: dict) -> str:
        """Backward compat: infer state from old data for unmigrated tenders."""
        a = self.db.get_analysis(tender.get("_id", ""))
        if a.get("pipeline_status"):
            return a["pipeline_status"]
        if tender.get("score", 0) >= 70:
            return STATES["QUALIFIED_GO"]
        return STATES["DISCOVERED"]

    # -- Worker stubs (call actual worker modules) --
    def _run_analyses(self, tid: str, analysis: dict):
        """Run the four analyses. In production, these call ai_engine.py."""
        self._log(tid, "Running analyses (summary, grading, compliance, boq)")
        # Import and call the actual AI workers:
        # from backend.ai_engine import run_summary, run_grading, run_compliance, run_boq
        # results = await asyncio.gather(run_summary(tid), run_grading(tid), ...)
        # For now, this is a stub; the artifact page handles analysis via sample()
        raise NotImplementedError("Wire ai_engine.py workers here for server deployment")

    def _run_writer(self, tid: str, analysis: dict):
        """Run the proposal writer. In production, calls agent3_writer.py + rag_engine.py."""
        self._log(tid, "Running proposal writer")
        raise NotImplementedError("Wire agent3_writer.py + rag_engine.py here for server deployment")

    def _run_kb_add(self, tid: str):
        """Run Agent 6 KB growth. In production, calls agent6_rebuild_kb.py."""
        self._log(tid, "Running KB growth (Agent 6)")
        raise NotImplementedError("Wire agent6_rebuild_kb.py here for server deployment")

    def migrate(self):
        """Stamp pipeline_status on all existing tenders that lack it."""
        tenders = self.db.get_all_tenders()
        count = 0
        for t in tenders:
            tid = t.get("_id", "")
            a = self.db.get_analysis(tid)
            if a.get("pipeline_status"):
                continue
            state = self._infer_state(t)
            self.set_status(t, state)
            count += 1
        self._log(None, f"Migration complete: {count} tenders stamped")
        return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="NETS Presales Manager Agent (Orchestrator)")
    ap.add_argument("--loop", action="store_true", help="Run continuously (poll every --interval seconds)")
    ap.add_argument("--interval", type=int, default=300, help="Poll interval in seconds (default 300 = 5 min)")
    ap.add_argument("--migrate", action="store_true", help="Stamp pipeline_status on all existing tenders")
    args = ap.parse_args()

    db = FirestoreDB()
    sp = SharePointClient() if SharePointClient().configured else None
    mgr = Manager(db, sp)

    if args.migrate:
        n = mgr.migrate()
        print(f"Migrated {n} tenders.")
        return

    if args.loop:
        log.info(f"Manager loop started. Polling every {args.interval}s. Ctrl+C to stop.")
        while True:
            try:
                mgr.run_cycle()
            except KeyboardInterrupt:
                log.info("Manager stopped by user.")
                break
            except Exception:
                log.exception("Manager cycle failed (will retry next interval)")
            time.sleep(args.interval)
    else:
        health = mgr.run_cycle()
        print(f"Cycle complete: {health}")


if __name__ == "__main__":
    main()
