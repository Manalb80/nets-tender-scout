"""
Seed the local database from a JSON export of the Claude Artifact DB.

Usage:
  1. Export your tenders from the artifact: copy the JSON from ArtifactData reads
  2. Save as scripts/tenders_export.json
  3. Run: python scripts/seed_data.py

Or run with --demo to insert sample data for testing.
"""
import sys
import os
import json
from datetime import datetime

# Add parent to path so we can import backend modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models import init_db, SessionLocal, Tender, ScanLog, Proposal
from scorer import score_tender

DEMO_TENDERS = [
    {"id": "S-26080803636", "title": "Maintenance & Support of Dell Servers", "department": "IT", "advertised": "1-Aug-2026", "closing": "15-Dec-2026"},
    {"id": "S-26070703412", "title": "Supply of Cisco Network Switches & Routers", "department": "IT", "advertised": "15-Jul-2026", "closing": "20-Dec-2026"},
    {"id": "S-26090904001", "title": "Cybersecurity Assessment & Firewall Deployment", "department": "IT", "advertised": "5-Sep-2026", "closing": "25-Dec-2026"},
    {"id": "S-26100105523", "title": "Data Centre UPS & Power Infrastructure Upgrade", "department": "IT", "advertised": "1-Oct-2026", "closing": "30-Dec-2026"},
    {"id": "S-26101005890", "title": "Annual Maintenance Contract for Storage SAN", "department": "IT", "advertised": "10-Oct-2026", "closing": "10-Jan-2027"},
    {"id": "S-26110106234", "title": "Supply & Installation of CCTV Surveillance System", "department": "Admin", "advertised": "1-Nov-2026", "closing": "15-Jan-2027"},
    {"id": "S-26110506401", "title": "Cloud Migration & Virtualization Services", "department": "IT", "advertised": "5-Nov-2026", "closing": "20-Jan-2027"},
    {"id": "S-26111006555", "title": "Managed IT Support Services (NOC Operations)", "department": "IT", "advertised": "10-Nov-2026", "closing": "25-Jan-2027"},
    {"id": "S-26111506700", "title": "Supply of WiFi Access Points & Wireless Network", "department": "IT", "advertised": "15-Nov-2026", "closing": "30-Jan-2027"},
    {"id": "S-26112006801", "title": "Structured Cabling for New Branch Offices", "department": "Admin", "advertised": "20-Nov-2026", "closing": "5-Feb-2027"},
]


def seed_demo():
    """Insert demo tenders for testing."""
    db = SessionLocal()
    now = datetime.utcnow()
    count = 0

    for raw in DEMO_TENDERS:
        if db.query(Tender).filter(Tender.id == raw["id"]).first():
            print(f"  Skipping {raw['id']} (already exists)")
            continue

        score, verdict, matched_solutions, matched_keywords = score_tender(raw["title"])

        tender = Tender(
            id=raw["id"],
            title=raw["title"],
            department=raw.get("department", ""),
            advertised=raw.get("advertised", ""),
            closing=raw.get("closing", ""),
            is_open=True,
            days_remaining=60,
            score=score,
            verdict=verdict,
            matched_keywords=matched_keywords,
            matched_solutions=matched_solutions,
        )
        db.add(tender)
        count += 1
        print(f"  Added: {raw['id']} | {raw['title'][:50]} | Score: {score} | {verdict}")

    # Add a scan log entry
    scan = ScanLog(
        date=now.strftime("%Y-%m-%d %H:%M"),
        total_on_portal=867,
        qualified_count=count,
        open_qualified_count=count,
        new_count=count,
        duration_seconds=2.5,
        status="success",
    )
    db.add(scan)
    db.commit()
    db.close()
    print(f"\nSeeded {count} demo tenders + 1 scan log entry.")


def seed_from_export(filepath: str):
    """Import tenders from a JSON export file."""
    with open(filepath) as f:
        data = json.load(f)

    db = SessionLocal()
    count = 0

    items = data if isinstance(data, list) else data.get("tenders", data.get("docs", []))

    for raw in items:
        tender_id = raw.get("id") or raw.get("_id", "")
        if not tender_id:
            continue
        if db.query(Tender).filter(Tender.id == tender_id).first():
            continue

        score, verdict, matched_solutions, matched_keywords = score_tender(raw.get("ti", raw.get("title", "")))

        tender = Tender(
            id=tender_id,
            title=raw.get("ti", raw.get("title", "")),
            department=raw.get("dept", raw.get("department", "")),
            advertised=raw.get("ad", raw.get("advertised", "")),
            closing=raw.get("cl", raw.get("closing", "")),
            is_open=raw.get("open", True),
            days_remaining=raw.get("days"),
            score=score,
            verdict=verdict,
            matched_keywords=matched_keywords,
            matched_solutions=matched_solutions,
            document_url=raw.get("doc", raw.get("document_url")),
        )
        db.add(tender)
        count += 1

    db.commit()
    db.close()
    print(f"Imported {count} tenders from {filepath}")


if __name__ == "__main__":
    init_db()

    if "--demo" in sys.argv:
        print("Seeding demo data...")
        seed_demo()
    elif len(sys.argv) > 1:
        filepath = sys.argv[1]
        if os.path.isfile(filepath):
            print(f"Importing from {filepath}...")
            seed_from_export(filepath)
        else:
            print(f"File not found: {filepath}")
    else:
        print("Usage:")
        print("  python scripts/seed_data.py --demo              # Insert test data")
        print("  python scripts/seed_data.py tenders_export.json # Import from export")
