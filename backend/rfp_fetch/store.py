"""Read the dashboard snapshot and write the plan, for systems reached through another tool (the Claude
artifact database, exported with ArtifactData `list ... out_dir`). The snapshot folder holds one JSON file
per document: <state>/tenders/<id>.json, <state>/rfp_analysis/<id>.json, <state>/rfp_text/<id>.json,
<state>/sp_index/<id>.json and optionally <state>/config/sharepoint.json. Missing folders mean empty."""
import json
import os
from typing import Dict, List

MAX_WRITES, MAX_BYTES = 50, 900_000   # ArtifactData batch limits: 50 writes, 1 MiB body


def load_collection(state: str, name: str) -> Dict[str, Dict]:
    folder, out = os.path.join(state, name), {}
    if not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(folder, fn), encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(d, dict):
                out[fn[:-5]] = d.get("data", d) if isinstance(d.get("data"), dict) else d
    return out


def load_doc(state: str, collection: str, doc_id: str):
    p = os.path.join(state, collection, doc_id + ".json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("data", d) if isinstance(d.get("data"), dict) else d


def write_batches(writes: List[Dict], out_dir: str) -> List[str]:
    """Each batch: at most 50 writes and under 1 MiB. Deletes of rfp_text parts go last so the text never
    disappears before its replacement is written."""
    os.makedirs(out_dir, exist_ok=True)
    for old in os.listdir(out_dir):    # a plan from an earlier run must never be applied by mistake
        if old.startswith("batch_") and old.endswith(".json"):
            os.remove(os.path.join(out_dir, old))
    order = {"sp_index": 0, "rfp_text": 1, "rfp_analysis": 2, "tenders": 3, "config": 4}
    writes = sorted(writes, key=lambda w: (w["op"] == "delete" and w["collection"] == "rfp_text", order.get(w["collection"], 9)))
    batches, cur, size = [], [], 0
    for w in writes:
        b = len(json.dumps(w, ensure_ascii=False).encode("utf-8"))
        if cur and (len(cur) >= MAX_WRITES or size + b > MAX_BYTES):
            batches.append(cur)
            cur, size = [], 0
        cur.append(w)
        size += b
    if cur:
        batches.append(cur)
    paths = []
    for i, b in enumerate(batches, 1):
        p = os.path.join(out_dir, "batch_%03d.json" % i)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)
        paths.append(p)
    return paths


def apply_to_snapshot(paths: List[str], state: str) -> int:
    """Rehearsal only: apply batch files to the local snapshot folder the way the dashboard database would
    (set replaces, update merges, delete removes), so a second run can be tested without touching the dashboard."""
    n = 0
    for p in paths:
        with open(p, encoding="utf-8") as f:
            batch = json.load(f)
        for w in batch:
            folder = os.path.join(state, w["collection"])
            target = os.path.join(folder, w["doc_id"] + ".json")
            if w["op"] == "delete":
                if os.path.exists(target):
                    os.remove(target)
            else:
                data = dict(load_doc(state, w["collection"], w["doc_id"]) or {}) if w["op"] == "update" else {}
                data.update(w["data"])
                os.makedirs(folder, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
            n += 1
    return n
