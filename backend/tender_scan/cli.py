"""Command line entry: python scripts/run_scan.py --store postgres|json [...]"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from . import portals
from .engine import run_scan
from .stores import JsonStore, PostgresStore


def scorer_fingerprint() -> str:
    """The scorer has no version number of its own, so the label is the fingerprint of its code:
    it changes exactly when the scoring rules change."""
    import scorer
    with open(scorer.__file__, "rb") as f:
        return "scorer-" + hashlib.sha1(f.read()).hexdigest()[:10]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic tender scan for Sindh Bank, PPRA EPMS and EPADS.")
    ap.add_argument("--store", choices=["postgres", "json"], default="postgres" if os.environ.get("DATABASE_URL") else "json")
    ap.add_argument("--state", help="json store: folder or file holding the tenders already stored")
    ap.add_argument("--last-scan", help="json store: file holding the previous scan record")
    ap.add_argument("--out", default="scan_out", help="json store: folder for the write plan")
    ap.add_argument("--max-pages", type=int, default=120)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between pages of one portal")
    ap.add_argument("--dry-run", action="store_true", help="scan and validate, write nothing")
    ap.add_argument("--portals", default="", help="re-scan only these portals, comma separated: sindh,ppra,epads. "
                                                  "The others are left untouched, nothing of theirs is closed.")
    args = ap.parse_args(argv)

    from scorer import score_tender
    if args.store == "postgres":
        url = os.environ.get("DATABASE_URL")
        if not url:
            print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
            return 2
        store = PostgresStore(url)
    else:
        store = JsonStore(args.state, args.out, args.last_scan)

    now = datetime.now(timezone.utc)
    previous, last = store.load_previous(), store.last_counts()
    print("Stored tenders: %d. Last complete scan rows: %s" % (len(previous), last or "none on record"))
    names = {"sindh": "Sindh Bank", "ppra": "PPRA", "epads": "EPADS"}
    want = None
    if args.portals.strip():
        keys = [k.strip().lower() for k in args.portals.split(",") if k.strip()]
        unknown = [k for k in keys if k not in names]
        if unknown:
            print("ERROR: unknown portal(s): %s. Use sindh, ppra or epads." % ", ".join(unknown), file=sys.stderr)
            return 2
        want = [names[k] for k in keys]
        print("Targeted re-scan of: %s. The other portals are left untouched." % ", ".join(want))
    results = portals.fetch_all(portals.requests_get(), args.max_pages, args.delay, want)
    for src, r in results.items():
        print("%-10s rows %-5d pages %-3d complete %-5s %s" % (src, len(r["rows"]), r["pages"], r["complete"], r["error"] or ""))
    plan = run_scan(results, previous, now, score_tender, scorer_fingerprint(), last)
    brief = {k: v for k, v in plan["scan"].items() if k != "unchecked_ids"}
    print(json.dumps(brief, indent=1))
    for key, ids in sorted(plan["scan"]["unchecked_ids"].items()):
        print("UNCHECKED %s (%d): %s%s" % (key, plan["scan"]["unchecked_count"][key], ", ".join(ids[:10]),
                                           " ..." if len(ids) > 10 else ""))
        print("   re-check with: python scripts/run_scan.py --portals %s" % key)
    for w in plan["warnings"]:
        print("WARNING:", w)
    if plan["scan"]["status"] == "failed":
        print("ERROR: no portal returned any tender. Nothing was written.", file=sys.stderr)
        return 1
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0
    print("Applied:", store.apply(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
