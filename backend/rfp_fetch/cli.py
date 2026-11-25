"""python scripts/run_rfp_fetch.py --state <snapshot folder> --out <plan folder> [--dry-run] [--listing file.json]"""
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

from .engine import build_plan
from .graph import GraphClient, GraphError, listing_from_file, token_provider_from_env
from .store import load_collection, load_doc, write_batches

log = logging.getLogger("rfp_fetch")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent 1b: deterministic SharePoint RFP fetcher (no AI).")
    ap.add_argument("--state", required=True, help="dashboard snapshot folder (tenders/, rfp_analysis/, rfp_text/, sp_index/, config/)")
    ap.add_argument("--out", default="rfp_out", help="folder for batch_NNN.json and report.json")
    ap.add_argument("--dry-run", action="store_true", help="list, match and read files, but write no plan")
    ap.add_argument("--listing", help="offline: a JSON listing instead of calling Graph (tests)")
    ap.add_argument("--files-dir", help="offline: folder holding the files named in --listing")
    ap.add_argument("--recursive", action="store_true", default=os.environ.get("SHAREPOINT_RFP_RECURSIVE", "") == "true")
    ap.add_argument("--save-dir", default=os.environ.get("RFP_DOWNLOAD_DIR", ""),
                    help="optional: keep a copy of each downloaded file in <dir>/<tender id>/")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")

    tenders = load_collection(args.state, "tenders")
    if not tenders:
        print("No tenders in the snapshot; waiting for Agent 1. Nothing written.")
        return 0
    folder = None
    try:
        if args.listing:
            files = listing_from_file(args.listing)
            base = args.files_dir or os.path.dirname(os.path.abspath(args.listing))

            def download(f):
                with open(os.path.join(base, f["name"]), "rb") as fh:
                    return fh.read()
        else:
            g = GraphClient(token_provider_from_env())
            folder = g.resolve_folder()
            log.info("RFP folder: %s (%s)", folder["name"], folder["web_url"])
            files = list(g.list_files(folder["drive_id"], folder["item_id"], recursive=args.recursive))

            def download(f):
                return g.download(f["drive_id"], f["item_id"])
    except GraphError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    log.info("%d files in the folder, %d tenders in the snapshot", len(files), len(tenders))

    def save_copy(tid, f, data):
        if args.save_dir and not args.dry_run:
            d = os.path.join(args.save_dir, tid)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, re.sub(r'[\\/:*?"<>|]', "_", f["name"])), "wb") as fh:
                fh.write(data)

    plan = build_plan(files, tenders, load_collection(args.state, "rfp_analysis"), datetime.now(timezone.utc), download,
                      folder=folder, sp_config=load_doc(args.state, "config", "sharepoint"),
                      sp_index=load_collection(args.state, "sp_index"), text_parts=load_collection(args.state, "rfp_text"),
                      save_copy=save_copy)
    r = plan["report"]
    summary = {k: (len(v) if isinstance(v, list) else v) for k, v in r.items()}
    print(json.dumps(summary))
    for k in ("sent", "scanned", "failed", "ambiguous", "unmatched"):
        for item in r[k]:
            print("%-10s %s" % (k.upper(), json.dumps(item, ensure_ascii=False)))
    if args.dry_run:
        print("Dry run: %d writes planned, nothing written." % len(plan["writes"]))
        return 0
    paths = write_batches(plan["writes"], args.out)
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(dict(r, stamp=plan["stamp"], batches=len(paths), writes=len(plan["writes"])), f, ensure_ascii=False, indent=1)
    print("Plan: %d writes in %d batches under %s" % (len(plan["writes"]), len(paths), args.out))
    return 0
