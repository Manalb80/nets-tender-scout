"""Turn a SharePoint folder listing plus the dashboard's current records into a write plan.

Pure logic: no network, no clock reads, no AI. The caller passes `download(file) -> bytes` and `now`.
The dashboard itself is the sync state: every file sent is recorded in rfp_analysis/<id>.docs[] with its
SharePoint item id and cTag, so a file is downloaded again only when SharePoint says its content changed.

Fields written (and nothing else):
  rfp_analysis/<id>  tender_id, rfpText, rfp_chars, rfp_stamp, rfp_received_at, rfpSource, docs
                     (never summary, grading, compliance, boq, decision or any other analysis field)
  rfp_text/<id>__<n> tender_id, part, parts, stamp, text   (only when the text is too big to keep inline)
  tenders/<id>       acquisition_status, acqStatus, doc_accessible
  sp_index/<item>    item_id, drive_id, uri, name, size, kind, modified, web_url, indexed_at
  config/sharepoint  indexed_at, count, indexed_by, error   (folder_uri and folder_name when missing)
"""
import json
import re
from datetime import datetime
from typing import Callable, Dict, List, Optional

from . import CHUNK_CHARS, INLINE_BYTES, SOURCE, TEXT_CAP
from .extract import extract, kind_of
from .match import is_live, match_file

ANALYSIS_FIELDS = ("tender_id", "rfpText", "rfp_chars", "rfp_stamp", "rfp_received_at", "rfpSource", "docs")
TENDER_FIELDS = ("acquisition_status", "acqStatus", "doc_accessible")
_SECTION = re.compile(r"^===== FILE: (.+?) =====$", re.M)


def _iso(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def file_uri(f: Dict) -> str:
    return "file:///%s/%s" % (f["drive_id"], f["item_id"])


def _sections(text: str) -> Dict[str, str]:
    """Split an existing rfpText into {file name: body}. Text before the first header is kept under ''."""
    out, parts = {}, _SECTION.split(text or "")
    if parts and parts[0].strip():
        out[""] = parts[0].strip("\n")
    for i in range(1, len(parts) - 1, 2):
        out[parts[i]] = parts[i + 1].strip("\n")
    return out


def _join(sections: Dict[str, str]) -> str:
    chunks = [sections[""]] if sections.get("") else []
    chunks += ["===== FILE: %s =====\n%s" % (k, v) for k, v in sections.items() if k]
    return "\n".join(chunks)[:TEXT_CAP]


def _same(doc_entry: Dict, f: Dict) -> bool:
    if f.get("ctag") and doc_entry.get("sp_ctag"):
        return doc_entry["sp_ctag"] == f["ctag"]
    if f.get("sha256") and doc_entry.get("sp_sha256"):
        return doc_entry["sp_sha256"] == f["sha256"]
    return doc_entry.get("size") == f.get("size") and doc_entry.get("sp_modified") == f.get("modified")


def _chunks(text: str) -> List[str]:
    return [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)] or [""]


def build_plan(files: List[Dict], tenders: Dict[str, Dict], analyses: Dict[str, Dict], now: datetime,
               download: Callable[[Dict], bytes], folder: Optional[Dict] = None, sp_config: Optional[Dict] = None,
               sp_index: Optional[Dict[str, Dict]] = None, text_parts: Optional[Dict[str, Dict]] = None,
               save_copy: Optional[Callable[[str, Dict, bytes], None]] = None) -> Dict:
    stamp = _iso(now)
    live = {k: v for k, v in tenders.items() if is_live(v)}
    writes: List[Dict] = []
    report = {"files": len(files), "sent": [], "unchanged": [], "unmatched": [], "ambiguous": [], "not_live": [],
              "scanned": [], "failed": [], "unsupported": []}

    # 1. sp_index mirrors the folder exactly (the workbench's file picker reads it).
    seen = set()
    for f in files:
        seen.add(f["item_id"])
        row = {"item_id": f["item_id"], "drive_id": f["drive_id"], "uri": file_uri(f), "name": f["name"],
               "size": f.get("size", 0), "kind": kind_of(f["name"]), "modified": f.get("modified"),
               "web_url": f.get("web_url"), "indexed_at": stamp}
        old = (sp_index or {}).get(f["item_id"])
        if not old or any(old.get(k) != row[k] for k in row if k != "indexed_at"):
            writes.append({"op": "update" if old else "set", "collection": "sp_index", "doc_id": f["item_id"], "data": row})
    for item_id in sorted(set(sp_index or {}) - seen):
        writes.append({"op": "delete", "collection": "sp_index", "doc_id": item_id})

    # 2. Match, then download only new or changed files.
    by_tender: Dict[str, List] = {}
    for f in files:
        tid, cands = match_file(f["name"], live)
        if not tid:
            if cands:
                report["ambiguous"].append({"file": f["name"], "candidates": cands})
            else:
                closed, _ = match_file(f["name"], {k: v for k, v in tenders.items() if k not in live})
                (report["not_live"] if closed else report["unmatched"]).append(f["name"] if not closed else {"file": f["name"], "tender": closed})
            continue
        prev_docs = (analyses.get(tid) or {}).get("docs") or []
        prev = next((d for d in prev_docs if d.get("sp_item") == f["item_id"]), None)
        if prev and _same(prev, f):
            report["unchanged"].append({"file": f["name"], "tender": tid})
            continue
        if kind_of(f["name"]) == "other":
            report["unsupported"].append({"file": f["name"], "tender": tid})
            continue
        try:
            data = download(f)
        except Exception as e:
            report["failed"].append({"file": f["name"], "tender": tid, "error": str(e)[:300]})
            continue
        if save_copy:
            save_copy(tid, f, data)
        res = extract(f["name"], data)
        by_tender.setdefault(tid, []).append((f, res))

    # 3. One analysis write per tender, merging with what it already holds.
    for tid, got in sorted(by_tender.items()):
        a = analyses.get(tid) or {}
        sections = _sections(a.get("rfpText") or "")
        if not a.get("rfpText") and text_parts:
            joined = "".join(p.get("text", "") for p in sorted((p for p in text_parts.values() if p.get("tender_id") == tid),
                                                               key=lambda p: p.get("part", 0)))
            sections = _sections(joined)
        docs = [d for d in (a.get("docs") or []) if d.get("sp_item") not in {f["item_id"] for f, _ in got}]
        readable = False
        for f, res in got:
            entry = {"name": f["name"], "size": f.get("size", 0), "pages": res.get("pages"), "extracted": res.get("extracted"),
                     "chars": res.get("chars", 0), "read": "sharepoint" if res["status"] == "read" else res["status"],
                     "sp_item": f["item_id"], "sp_drive": f["drive_id"], "sp_ctag": f.get("ctag"), "sp_sha256": f.get("sha256"),
                     "sp_modified": f.get("modified"), "at": stamp}
            if res.get("detail"):
                entry["error"] = res["detail"]
            docs.append(entry)
            sections.pop(f["name"], None)
            if res["status"] == "read":
                sections[f["name"]] = res["text"]
                readable = True
                report["sent"].append({"file": f["name"], "tender": tid, "chars": res["chars"]})
            else:
                report["scanned" if res["status"] == "scanned" else res["status"] if res["status"] in report else "failed"].append(
                    {"file": f["name"], "tender": tid, "detail": res.get("detail", "")})
        text = _join(sections)
        rec = {"tender_id": tid, "docs": docs, "rfpSource": SOURCE}
        if readable:
            rec.update(rfp_stamp=stamp, rfp_received_at=stamp, rfp_chars=len(text))
            old_parts = sorted(k for k, p in (text_parts or {}).items() if p.get("tender_id") == tid)
            if len(text.encode("utf-8")) <= INLINE_BYTES:
                rec["rfpText"] = text
                writes += [{"op": "delete", "collection": "rfp_text", "doc_id": k} for k in old_parts]
            else:
                parts = _chunks(text)
                rec["rfpText"] = ""
                for i, chunk in enumerate(parts):
                    writes.append({"op": "set", "collection": "rfp_text", "doc_id": "%s__%d" % (tid, i),
                                   "data": {"tender_id": tid, "part": i, "parts": len(parts), "stamp": stamp, "text": chunk}})
                keep = {"%s__%d" % (tid, i) for i in range(len(parts))}
                writes += [{"op": "delete", "collection": "rfp_text", "doc_id": k} for k in old_parts if k not in keep]
        writes.append({"op": "update" if a else "set", "collection": "rfp_analysis", "doc_id": tid, "data": rec})
        has_text = readable or bool(a.get("rfpText") or a.get("rfp_chars"))
        status = "SHAREPOINT" if has_text else "SHAREPOINT_SCANNED"
        t = tenders[tid]
        if t.get("acquisition_status") != status or t.get("acqStatus") != status or t.get("doc_accessible") is not True:
            writes.append({"op": "update", "collection": "tenders", "doc_id": tid,
                           "data": {"acquisition_status": status, "acqStatus": status, "doc_accessible": True}})

    # 4. Folder config: what the workbench shows as "indexed".
    cfg = {"indexed_at": stamp, "count": len(files), "indexed_by": "agent_1b", "error": None}
    if folder and not (sp_config or {}).get("folder_uri"):
        cfg.update(folder_uri="file:///%s/%s" % (folder["drive_id"], folder["item_id"]), folder_name=folder.get("name"))
    writes.append({"op": "update" if sp_config else "set", "collection": "config", "doc_id": "sharepoint", "data": cfg})

    plan = {"writes": writes, "report": report, "stamp": stamp}
    validate(plan)
    return plan


def validate(plan: Dict) -> None:
    allowed = {"rfp_analysis": set(ANALYSIS_FIELDS), "tenders": set(TENDER_FIELDS),
               "sp_index": {"item_id", "drive_id", "uri", "name", "size", "kind", "modified", "web_url", "indexed_at"},
               "rfp_text": {"tender_id", "part", "parts", "stamp", "text"},
               "config": {"indexed_at", "count", "indexed_by", "error", "folder_uri", "folder_name"}}
    seen = set()
    for w in plan["writes"]:
        key = (w["collection"], w["doc_id"])
        if key in seen:
            raise ValueError("document written twice: %s/%s" % key)
        seen.add(key)
        if w["op"] == "delete":
            continue
        extra = set(w["data"]) - allowed[w["collection"]]
        if extra:
            raise ValueError("%s/%s would write fields it does not own: %s" % (w["collection"], w["doc_id"], sorted(extra)))
    json.dumps(plan["writes"])  # must be plain JSON
