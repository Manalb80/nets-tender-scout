"""The scan itself: a pure function from (portal results, what is already stored, the time) to a write plan.

Given the same three inputs it always returns the same plan. It never touches the network or a database.

Rules it enforces
  1. One tender, one id (normalize.canonical_id); an existing suffixed PPRA document is reused, not duplicated.
  2. A tender is open only when a closing date was read and has not passed. No date: never open.
  3. A tender missing from a portal is closed only when that portal was read completely AND returned at
     least GUARD_RATIO of the rows it returned last time. One bad scrape can no longer close a portal's tenders.
  4. Fields a person or another agent owns are never written (see SCAN_FIELDS).
  5. The scan record has one fixed layout (SCAN_KEYS). The plan is validated before it is returned.
"""
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from . import SCHEMA_VERSION, SCORE_THRESHOLD
from .dates import PKT, days_left, parse_closing
from .normalize import SOURCES, canonical_id, clean_closing, clean_title, ppra_base, resolve_existing_id

GUARD_RATIO = 0.7
PORTAL_KEY = {"Sindh Bank": "sindh", "PPRA": "ppra", "EPADS": "epads"}
# The only fields a scan may write on a tender. Everything else (assignee, goNogo, acquisition_status,
# acqStatus, local_folder, doc_accessible, decisions, analysis) belongs to people and other agents.
SCAN_FIELDS = ("id", "ti", "desc", "dept", "ad", "cl", "cl_iso", "closing_at", "date_missing", "open", "days",
               "source", "source_portal", "detailUrl", "doc", "score", "verdict", "matched", "solMatch",
               "qualVerdict", "dqReason", "qualGates", "lastScan", "scorer_version", "schema",
               "not_on_portal_since")
SCAN_KEYS = ("schema", "date", "timestamp", "status", "total_on_portal", "per_portal", "pages_read", "complete",
             "errors", "qualified_count", "open_qualified_count", "nogo_count", "new_count", "updated_count",
             "closed_count", "closures_skipped", "date_missing_count", "skipped_no_id", "scorer_version")


class ScanError(Exception):
    pass


def _prev_closing(prev: Dict, now: datetime):
    """Closing time of a stored record. Relative text ("4h 8m Left") has no anchor once stored, so it is ignored."""
    for key in ("closing_at", "cl_iso", "cl", "cl_manual"):   # cl_manual: a date a person typed in
        val = prev.get(key)
        if val:
            dt, kind = parse_closing(str(val).replace("T", " ") if key == "closing_at" else str(val), now)
            if dt is not None and kind != "relative":
                if key == "closing_at":                       # stored with its own offset
                    try:
                        return datetime.fromisoformat(str(val)).astimezone(PKT)
                    except ValueError:
                        pass
                return dt
    return None


def _dedupe(rows: List[Dict], now: datetime) -> Dict[str, Dict]:
    """Sindh Bank lists one tender on several rows (advertisement, corrigendum, evaluation report).
    Keep the row with the latest readable closing date, and keep a document link if any row has one."""
    best: Dict[str, Dict] = {}
    for r in rows:
        cur = best.get(r["_id"])
        if cur is None:
            best[r["_id"]] = r
            continue
        a, b = parse_closing(cur["closing"], now)[0], parse_closing(r["closing"], now)[0]
        keep, drop = (r, cur) if (b is not None and (a is None or b > a)) else (cur, r)
        if not keep.get("doc_url") and drop.get("doc_url"):
            keep = dict(keep, doc_url=drop["doc_url"])
        best[r["_id"]] = keep
    return best


def run_scan(portal_results: Dict[str, Dict], previous: Dict[str, Dict], now: datetime,
             score_fn: Callable, scorer_version: str, last_counts: Optional[Dict[str, int]] = None) -> Dict:
    """previous: {doc id: stored tender (at least source/open/cl)}. last_counts: rows per portal in the last
    good scan, keyed sindh/ppra/epads. Returns {"scan", "upserts", "closures", "warnings"}."""
    if now.tzinfo is None:
        raise ScanError("now must be timezone-aware")
    today = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    last_counts = last_counts or {}
    existing_ids = set(previous)
    upserts, closures, warnings = [], [], []
    per_portal, pages, complete, errors, skipped_closures = {}, {}, {}, {}, {}
    skipped_no_id = date_missing = nogo = 0
    seen_ids = {s: set() for s in SOURCES}

    for source in SOURCES:
        res = portal_results.get(source) or {"rows": [], "pages": 0, "complete": False, "error": "not scanned"}
        key = PORTAL_KEY[source]
        rows = []
        for r in res["rows"]:
            cid = canonical_id(source, r.get("raw_id", ""), r.get("title", ""), r.get("advertised", ""))
            if not cid:
                skipped_no_id += 1
                continue
            rows.append(dict(r, _id=resolve_existing_id(cid, source, existing_ids)))
        uniq = _dedupe(rows, now)
        per_portal[key], pages[key], complete[key] = len(res["rows"]), res.get("pages", 0), bool(res.get("complete"))
        if res.get("error"):
            errors[key] = res["error"]
        seen_ids[source] = set(uniq)

        for doc_id in sorted(uniq):
            r = uniq[doc_id]
            prev = previous.get(doc_id)
            text = clean_title(r["title"] + (" " + r["description"] if r.get("description") else ""))
            score, verdict, solutions, keywords, qual = score_fn(text)
            if score < SCORE_THRESHOLD:
                continue
            closing, kind = parse_closing(r["closing"], now)
            rec = {"id": doc_id, "ti": clean_title(r["title"]), "desc": clean_title(r.get("description", "")),
                   "dept": clean_title(r.get("department", ""))[:150], "ad": clean_closing(r.get("advertised", "")),
                   "source": source, "source_portal": source, "detailUrl": r.get("detail_url", ""),
                   "doc": r.get("doc_url", ""), "score": int(score), "verdict": verdict,
                   "matched": list(keywords), "solMatch": list(solutions),
                   "qualVerdict": qual.get("overall_verdict", "GO"),
                   "dqReason": qual.get("disqualification_reason"), "qualGates": qual.get("gates", {}),
                   "lastScan": today, "scorer_version": scorer_version, "schema": SCHEMA_VERSION,
                   "not_on_portal_since": None}
            if closing is None:
                date_missing += 1
                kept = _prev_closing(prev, now) if prev else None
                if prev is None:
                    continue                                   # never create a tender nobody can date
                if kept is not None:                           # keep the date already on record
                    rec.update(open=kept >= now, days=days_left(kept, now), date_missing=False)
                else:
                    rec.update(cl="", cl_iso=None, closing_at=None, open=False, days=None, date_missing=True)
            else:
                shown = clean_closing(r["closing"]) if kind != "relative" else closing.strftime("%b %d, %Y %I:%M %p")
                rec.update(cl=shown, cl_iso=closing.strftime("%Y-%m-%d"), closing_at=closing.isoformat(),
                           open=closing >= now, days=days_left(closing, now), date_missing=False)
            if not rec.get("doc") and prev and prev.get("doc"):
                rec.pop("doc")                                 # never blank a document link already stored
            if rec["qualVerdict"] == "NOGO":
                nogo += 1
            upserts.append({"id": doc_id, "exists": prev is not None, "data": rec})

    written = {u["id"] for u in upserts}
    # A stored PPRA twin (plain + suffixed id for one number) counts as seen when either was seen.
    seen_ppra_bases = {ppra_base(i) for i in seen_ids["PPRA"]}
    for doc_id in sorted(previous):
        prev = previous[doc_id]
        if doc_id in written or not prev.get("open"):
            continue
        source = prev.get("source_portal") or prev.get("source") or "Sindh Bank"
        if source == "sindhbank":
            source = "Sindh Bank"
        closing = _prev_closing(prev, now)
        if closing is not None and closing < now:
            closures.append({"id": doc_id, "reason": "closing_passed", "data": {"open": False, "days": days_left(closing, now)}})
            continue
        if source not in SOURCES:
            continue
        on_portal = doc_id in seen_ids[source] or (source == "PPRA" and ppra_base(doc_id) in seen_ppra_bases)
        if on_portal:
            continue                                           # still listed (it may simply score below the threshold)
        key = PORTAL_KEY[source]
        if not complete[key]:
            skipped_closures[key] = "portal was not read completely" + (": " + errors[key] if key in errors else "")
            continue
        if last_counts.get(key) and per_portal[key] < GUARD_RATIO * last_counts[key]:
            skipped_closures[key] = "only %d rows against %d last time" % (per_portal[key], last_counts[key])
            continue
        closures.append({"id": doc_id, "reason": "not_on_portal",
                         "data": {"open": False, "not_on_portal_since": today}})

    for key, why in sorted(skipped_closures.items()):
        warnings.append("%s: nothing was closed (%s)" % (key, why))
    ok = [k for k in complete if complete[k]]
    scan = {"schema": SCHEMA_VERSION, "date": today, "timestamp": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "complete" if len(ok) == len(SOURCES) else ("partial" if per_portal and sum(per_portal.values()) else "failed"),
            "total_on_portal": sum(per_portal.values()), "per_portal": per_portal, "pages_read": pages,
            "complete": complete, "errors": errors,
            "qualified_count": len(upserts),
            "open_qualified_count": sum(1 for u in upserts if u["data"]["open"]),
            "nogo_count": nogo, "new_count": sum(1 for u in upserts if not u["exists"]),
            "updated_count": sum(1 for u in upserts if u["exists"]), "closed_count": len(closures),
            "closures_skipped": skipped_closures, "date_missing_count": date_missing,
            "skipped_no_id": skipped_no_id, "scorer_version": scorer_version}
    plan = {"scan": scan, "upserts": upserts, "closures": closures, "warnings": warnings}
    validate(plan)
    return plan


def validate(plan: Dict) -> None:
    """Refuse to hand over a plan that breaks the contract. Raising here means nothing is written."""
    scan = plan["scan"]
    if tuple(sorted(scan)) != tuple(sorted(SCAN_KEYS)):
        raise ScanError("scan record fields differ from the fixed layout")
    ids = set()
    for u in plan["upserts"]:
        d = u["data"]
        if not d.get("id") or d["id"] != u["id"] or d["id"] in ids:
            raise ScanError("missing, mismatched or duplicate id: %r" % u.get("id"))
        ids.add(d["id"])
        extra = set(d) - set(SCAN_FIELDS)
        if extra:
            raise ScanError("field a scan may not write: %s" % sorted(extra))
        if d["source"] not in SOURCES or not isinstance(d["score"], int) or d["score"] < SCORE_THRESHOLD:
            raise ScanError("bad source or score on %s" % d["id"])
        if not isinstance(d["open"], bool):
            raise ScanError("open must be true or false on %s" % d["id"])
        if d["open"] and (d.get("date_missing") or d.get("days") is None or d["days"] < 0):
            raise ScanError("%s is marked open without a future closing date" % d["id"])
        if "\n" in d["ti"] or "\n" in str(d.get("cl") or ""):
            raise ScanError("line break in title or closing on %s" % d["id"])
    for c in plan["closures"]:
        if c["id"] in ids or c["data"].get("open") is not False:
            raise ScanError("bad closure for %s" % c["id"])
