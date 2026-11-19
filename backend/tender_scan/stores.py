"""Where a scan reads what is already stored and writes its plan.

PostgresStore  the live system (DATABASE_URL). One transaction: all of a plan is applied or none of it.
JsonStore      a snapshot of stored tenders in, a write plan out. Used where the database can only be
               reached through another tool (the Claude artifact prototype), and for dry runs and tests.
Both expose: load_previous() -> {id: tender}, last_counts() -> {sindh,ppra,epads}, apply(plan)."""
import json
import os
from typing import Dict, List, Optional

from .engine import PORTAL_KEY, SCAN_FIELDS


class JsonStore:
    """state: a folder of one-JSON-per-tender files, or one JSON file holding a list or an {id: tender} map.
    last_scan: optional JSON file with the previous scan record. out_dir: where the plan is written."""

    def __init__(self, state: Optional[str], out_dir: str, last_scan: Optional[str] = None, batch: int = 50):
        self.state, self.out_dir, self.last_scan, self.batch = state, out_dir, last_scan, batch

    def load_previous(self) -> Dict[str, Dict]:
        docs: List[Dict] = []
        if not self.state or not os.path.exists(self.state):
            return {}
        if os.path.isdir(self.state):
            for name in sorted(os.listdir(self.state)):
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(self.state, name), encoding="utf-8") as f:
                        d = json.load(f)
                except (ValueError, OSError):
                    continue
                if isinstance(d, dict):
                    d = d.get("data", d) if "data" in d and isinstance(d.get("data"), dict) else d
                    d = dict(d, _stored_id=d.get("id"), id=name[:-5])   # the file name is the document id
                    docs.append(d)
        else:
            with open(self.state, encoding="utf-8") as f:
                raw = json.load(f)
            docs = [dict(v, id=v.get("id", k)) for k, v in raw.items()] if isinstance(raw, dict) else list(raw)
        return {str(d["id"]): d for d in docs if d.get("id")}

    def last_counts(self) -> Dict[str, int]:
        if not self.last_scan or not os.path.exists(self.last_scan):
            return {}
        with open(self.last_scan, encoding="utf-8") as f:
            rec = json.load(f)
        rec = rec.get("data", rec)
        return {k: int(v) for k, v in (rec.get("per_portal") or {}).items() if isinstance(v, (int, float))}

    def apply(self, plan: Dict) -> Dict:
        os.makedirs(self.out_dir, exist_ok=True)
        writes = [{"op": "update" if u["exists"] else "set", "collection": "tenders", "doc_id": u["id"], "data": u["data"]}
                  for u in plan["upserts"]]
        writes += [{"op": "update", "collection": "tenders", "doc_id": c["id"], "data": c["data"]} for c in plan["closures"]]
        files = []
        for i in range(0, len(writes), self.batch):
            path = os.path.join(self.out_dir, "batch_%03d.json" % (i // self.batch + 1))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(writes[i:i + self.batch], f, ensure_ascii=False, indent=1)
            files.append(path)
        with open(os.path.join(self.out_dir, "scan_record.json"), "w", encoding="utf-8") as f:
            json.dump(plan["scan"], f, ensure_ascii=False, indent=1)
        with open(os.path.join(self.out_dir, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False)
        return {"batches": files, "writes": len(writes)}


_COLUMNS = [  # column, SQL type, plan field
    ("title", "VARCHAR(500)", "ti"), ("description", "TEXT", "desc"), ("department", "VARCHAR(200)", "dept"),
    ("advertised", "VARCHAR(80)", "ad"), ("closing", "VARCHAR(80)", "cl"), ("closing_date", "TIMESTAMP", "_closing_naive"),
    ("closing_at", "TIMESTAMPTZ", "closing_at"), ("date_missing", "BOOLEAN", "date_missing"),
    ("is_open", "BOOLEAN", "open"), ("days_remaining", "INTEGER", "days"), ("score", "INTEGER", "score"),
    ("verdict", "VARCHAR(20)", "verdict"), ("qual_verdict", "VARCHAR(20)", "qualVerdict"),
    ("qual_gates", "JSONB", "qualGates"), ("disqualification_reason", "TEXT", "dqReason"),
    ("matched_keywords", "JSONB", "matched"), ("matched_solutions", "JSONB", "solMatch"),
    ("document_url", "VARCHAR(1000)", "doc"), ("source_portal", "VARCHAR(50)", "source"),
    ("detail_url", "VARCHAR(1000)", "detailUrl"), ("last_scan", "VARCHAR(10)", "lastScan"),
    ("scorer_version", "VARCHAR(40)", "scorer_version"), ("not_on_portal_since", "VARCHAR(10)", "not_on_portal_since"),
]
_JSON_COLS = {"qual_gates", "matched_keywords", "matched_solutions"}


class PostgresStore:
    """Writes the same plan to the live Postgres database. Columns owned by people or other agents
    (acquisition_status, doc_accessible, local_folder, created_at) are never in an UPDATE."""

    def __init__(self, url: str):
        from sqlalchemy import create_engine
        url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):                # name the driver, so any SQLAlchemy version behaves the same
            try:
                import psycopg2  # noqa: F401
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            except ImportError:
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        # Tender titles contain non-English characters; never depend on the server or machine default.
        self.engine = create_engine(url, connect_args={"client_encoding": "utf8"})

    def ensure_schema(self, conn) -> None:
        from sqlalchemy import text
        conn.execute(text("CREATE TABLE IF NOT EXISTS tenders (id VARCHAR(100) PRIMARY KEY, "
                          "created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())"))
        for col, typ, _ in _COLUMNS:
            conn.execute(text("ALTER TABLE tenders ADD COLUMN IF NOT EXISTS %s %s" % (col, typ)))
        # Tables created by the old script have narrower text columns. Widening never loses data.
        for col, typ in (("title", "VARCHAR(500)"), ("department", "VARCHAR(200)"), ("advertised", "VARCHAR(80)"),
                         ("closing", "VARCHAR(80)")):
            conn.execute(text("ALTER TABLE tenders ALTER COLUMN %s TYPE %s" % (col, typ)))
        for col, typ in (("source_url", "VARCHAR(1000)"), ("acquisition_status", "VARCHAR(30) DEFAULT 'PENDING'"),
                         ("doc_accessible", "BOOLEAN DEFAULT TRUE"), ("local_folder", "VARCHAR(500)")):
            conn.execute(text("ALTER TABLE tenders ADD COLUMN IF NOT EXISTS %s %s" % (col, typ)))
        conn.execute(text("CREATE TABLE IF NOT EXISTS scan_runs (date VARCHAR(10) PRIMARY KEY, payload JSONB NOT NULL, "
                          "created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS scan_logs (id SERIAL PRIMARY KEY, date VARCHAR(50), "
                          "total_on_portal INTEGER DEFAULT 0, qualified_count INTEGER DEFAULT 0, "
                          "open_qualified_count INTEGER DEFAULT 0, new_count INTEGER DEFAULT 0, duration_seconds FLOAT, "
                          "status VARCHAR(20) DEFAULT 'success', error_message TEXT, created_at TIMESTAMP DEFAULT NOW())"))

    def load_previous(self) -> Dict[str, Dict]:
        from sqlalchemy import text
        with self.engine.begin() as conn:
            self.ensure_schema(conn)
            rows = conn.execute(text("SELECT id, source_portal, is_open, closing, closing_at, closing_date, document_url, score "
                                     "FROM tenders")).mappings().all()
        out = {}
        for r in rows:
            at = r["closing_at"].isoformat() if r["closing_at"] is not None else None
            cl = r["closing"] or (r["closing_date"].strftime("%Y-%m-%d") if r["closing_date"] is not None else "")
            out[r["id"]] = {"id": r["id"], "source": r["source_portal"] or "Sindh Bank", "open": bool(r["is_open"]),
                            "cl": cl, "closing_at": at, "doc": r["document_url"] or "", "score": r["score"] or 0}
        return out

    def last_counts(self) -> Dict[str, int]:
        from sqlalchemy import text
        with self.engine.begin() as conn:
            self.ensure_schema(conn)
            row = conn.execute(text("SELECT payload FROM scan_runs WHERE payload->>'status' = 'complete' "
                                    "ORDER BY date DESC LIMIT 1")).first()
        if not row:
            return {}
        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return {k: int(v) for k, v in (payload.get("per_portal") or {}).items()}

    @staticmethod
    def _params(data: Dict) -> Dict:
        from datetime import datetime
        p = {}
        for col, _, field in _COLUMNS:
            if field == "_closing_naive":
                if "closing_at" in data:
                    at = data.get("closing_at")
                    p[col] = datetime.fromisoformat(at).replace(tzinfo=None) if at else None
                continue
            if field not in data:
                continue                                   # absent means "leave what is stored"
            val = data[field]
            p[col] = json.dumps(val) if col in _JSON_COLS and val is not None else val
        return p

    def apply(self, plan: Dict) -> Dict:
        from sqlalchemy import text
        with self.engine.begin() as conn:                  # one transaction
            self.ensure_schema(conn)
            for u in plan["upserts"]:
                p = self._params(u["data"])
                cols = list(p)
                cast = lambda c: "CAST(:%s AS JSONB)" % c if c in _JSON_COLS else ":" + c
                sql = ("INSERT INTO tenders (id, %s) VALUES (:id, %s) ON CONFLICT (id) DO UPDATE SET %s, updated_at = NOW()"
                       % (", ".join(cols), ", ".join(cast(c) for c in cols),
                          ", ".join("%s = EXCLUDED.%s" % (c, c) for c in cols)))
                conn.execute(text(sql), dict(p, id=u["id"]))
            for c in plan["closures"]:
                d = c["data"]
                sets, p = ["is_open = FALSE", "updated_at = NOW()"], {"id": c["id"]}
                if "days" in d:
                    sets.append("days_remaining = :days"); p["days"] = d["days"]
                if d.get("not_on_portal_since"):
                    sets.append("not_on_portal_since = :since"); p["since"] = d["not_on_portal_since"]
                conn.execute(text("UPDATE tenders SET %s WHERE id = :id" % ", ".join(sets)), p)
            s = plan["scan"]
            conn.execute(text("INSERT INTO scan_runs (date, payload) VALUES (:d, CAST(:p AS JSONB)) "
                              "ON CONFLICT (date) DO UPDATE SET payload = EXCLUDED.payload, created_at = NOW()"),
                         {"d": s["date"], "p": json.dumps(s)})
            conn.execute(text("INSERT INTO scan_logs (date, total_on_portal, qualified_count, open_qualified_count, "
                              "new_count, status, error_message) VALUES (:d, :t, :q, :o, :n, :s, :e)"),
                         {"d": s["timestamp"], "t": s["total_on_portal"], "q": s["qualified_count"],
                          "o": s["open_qualified_count"], "n": s["new_count"], "s": s["status"],
                          "e": json.dumps(s["errors"]) if s["errors"] else None})
        return {"writes": len(plan["upserts"]) + len(plan["closures"])}
