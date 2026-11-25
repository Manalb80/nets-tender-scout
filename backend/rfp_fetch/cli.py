"""Agent 1b command line.

  python scripts/run_rfp_fetch.py --state <snapshot> [--source local|graph] [--watch-dir DIR] [--dry-run]

Reads the dashboard snapshot, scans the RFP folder, and writes batch_NNN.json plus report.json to --out.
Exit codes: 0 done (or nothing to do), 2 the folder or SharePoint could not be reached.
"""
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

from .engine import build_plan
from .graph import GraphError
from .sources import GraphSource, HashCache, ListingSource, LocalFolderSource, SourceError
from .store import apply_to_snapshot, load_collection, load_doc, write_batches

log = logging.getLogger("rfp_fetch")


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return default if not v else v in ("1", "true", "yes", "on")


def main(argv=None) -> int:
    env = os.environ
    ap = argparse.ArgumentParser(description="Agent 1b: deterministic RFP intake (no AI).")
    ap.add_argument("--state", required=True, help="dashboard snapshot folder (tenders/, rfp_analysis/, rfp_text/, sp_index/, config/)")
    ap.add_argument("--out", default=env.get("RFP_OUT_DIR", "rfp_out"), help="folder for batch_NNN.json and report.json")
    ap.add_argument("--source", choices=("local", "graph"), default=env.get("RFP_SOURCE", "local"),
                    help="local: a synced or staging folder (default). graph: SharePoint through Microsoft Graph")
    ap.add_argument("--watch-dir", default=env.get("RFP_WATCH_DIR", ""), help="local: the folder to scan")
    ap.add_argument("--archive-dir", default=env.get("RFP_ARCHIVE_DIR", ""), help="local: where processed files are archived")
    ap.add_argument("--archive-mode", choices=("copy", "move", "off"), default=env.get("RFP_ARCHIVE_MODE", "copy"),
                    help="copy (default) keeps the original; move empties a staging folder. Never use move on a shared synced folder")
    ap.add_argument("--stable-seconds", type=float, default=float(env.get("RFP_STABLE_SECONDS", "30")),
                    help="local: a file must be unchanged this long before it is read")
    ap.add_argument("--cache", default=env.get("RFP_CACHE_FILE", os.path.join("rfp_state", "agent1b_hashes.json")),
                    help="local: SHA-256 memo keyed by path, size and mtime")
    ap.add_argument("--acq-status", default=env.get("RFP_ACQ_STATUS", "SHAREPOINT"), choices=("SHAREPOINT", "AUTO_DOWNLOADED"),
                    help="acquisition_status written when text arrives (scanned files get <status>_SCANNED)")
    ap.add_argument("--dry-run", action="store_true", help="scan, match and read files, but write no plan, archive or cache")
    ap.add_argument("--listing", help="offline tests: a JSON listing instead of a live folder")
    ap.add_argument("--files-dir", help="offline tests: folder holding the files named in --listing")
    ap.add_argument("--recursive", action="store_true", default=None, help="include subfolders (local default: yes)")
    ap.add_argument("--no-recursive", dest="recursive", action="store_false")
    ap.add_argument("--save-dir", default=env.get("RFP_DOWNLOAD_DIR", ""),
                    help="graph: keep a copy of each downloaded file in <dir>/<tender id>/")
    ap.add_argument("--apply-to-snapshot", action="store_true",
                    help="rehearsal: also apply the plan to the --state snapshot files (never the dashboard)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")

    tenders = load_collection(args.state, "tenders")
    if not tenders:
        print("No tenders in the snapshot; waiting for Agent 1. Nothing written.")
        return 0
    cache = None
    try:
        if args.listing:
            src = ListingSource(args.listing, args.files_dir, kind=args.source)
        elif args.source == "local":
            cache = HashCache(args.cache)
            src = LocalFolderSource(args.watch_dir, recursive=_env_bool("RFP_RECURSIVE", True) if args.recursive is None else args.recursive,
                                    stable_seconds=args.stable_seconds,
                                    recheck_seconds=float(env.get("RFP_RECHECK_SECONDS", "2")), archive_dir=args.archive_dir or None, cache=cache,
                                    hydrate=_env_bool("RFP_HYDRATE", False))
        else:
            src = GraphSource(recursive=_env_bool("SHAREPOINT_RFP_RECURSIVE", False) if args.recursive is None else args.recursive)
        files = src.list_files()
    except (SourceError, GraphError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    desc = src.describe()
    log.info("%s folder %s: %d files ready, %d waiting; %d tenders in the snapshot",
             desc["kind"], desc.get("root") or desc.get("web_url"), len(files), len(src.waiting), len(tenders))

    def save_copy(tid, f, data):
        if args.save_dir and not args.dry_run and src.kind == "graph":
            d = os.path.join(args.save_dir, tid)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, re.sub(r'[\\/:*?"<>|]', "_", f["name"])), "wb") as fh:
                fh.write(data)

    plan = build_plan(files, tenders, load_collection(args.state, "rfp_analysis"), datetime.now(timezone.utc), src.read,
                      folder=desc if src.kind == "graph" and "drive_id" in desc else None,
                      sp_config=load_doc(args.state, "config", "sharepoint"), sp_index=load_collection(args.state, "sp_index"),
                      text_parts=load_collection(args.state, "rfp_text"), save_copy=save_copy, kind=src.kind,
                      acq_status=args.acq_status)
    r = plan["report"]
    r["waiting"] = src.waiting

    # Archive only files the dashboard already holds (reported "unchanged"): a file sent in this run is
    # archived on the next run, once its batch has been applied. Nothing is lost if a batch is never applied.
    archived = []
    if not args.dry_run and args.archive_mode != "off":
        for f, tid in plan["archive"]:
            try:
                target = src.archive(f, tid, args.archive_mode)
                if target:
                    archived.append({"file": f.get("path") or f["name"], "tender": tid, "to": target})
            except OSError as e:
                r["failed"].append({"file": f.get("path") or f["name"], "tender": tid, "error": "archive: %s" % e})
    r["archived"] = archived
    if cache and not args.dry_run:
        cache.save()

    summary = {k: (len(v) if isinstance(v, list) else v) for k, v in r.items()}
    print(json.dumps(summary))
    for k in ("sent", "scanned", "failed", "duplicate", "ambiguous", "unmatched", "waiting", "archived", "kept_status"):
        for item in r.get(k, []):
            print("%-10s %s" % (k.upper(), json.dumps(item, ensure_ascii=False)))
    if args.dry_run:
        print("Dry run: %d writes planned; nothing written, archived or cached." % len(plan["writes"]))
        return 0
    paths = write_batches(plan["writes"], args.out)
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(dict(r, stamp=plan["stamp"], batches=len(paths), writes=len(plan["writes"]), source=desc),
                  f, ensure_ascii=False, indent=1)
    print("Plan: %d writes in %d batches under %s" % (len(plan["writes"]), len(paths), args.out))
    if args.apply_to_snapshot:
        print("Rehearsal: applied %d writes to the snapshot in %s" % (apply_to_snapshot(paths, args.state), args.state))
    return 0
