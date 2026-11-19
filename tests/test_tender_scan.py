"""Tests for the deterministic scan. No network: portal pages are saved fixtures (trimmed copies of the
real pages fetched on 19 Nov 2026). Run: python -m pytest tests -q
The Postgres tests run only when TEST_DATABASE_URL points at a disposable database."""
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from tender_scan import SCORE_THRESHOLD, parsers, portals  # noqa: E402
from tender_scan.dates import PKT, days_left, parse_closing  # noqa: E402
from tender_scan.engine import SCAN_FIELDS, SCAN_KEYS, ScanError, run_scan, validate  # noqa: E402
from tender_scan.normalize import canonical_id, resolve_existing_id  # noqa: E402
from tender_scan.stores import JsonStore  # noqa: E402

FX = os.path.join(os.path.dirname(__file__), "fixtures")
NOW = datetime(2026, 11, 19, 14, 0, tzinfo=timezone.utc)


def fx(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


def score_stub(text):
    """Stand-in scorer with the real signature: 'switch', 'server' or 'firewall' qualifies."""
    hit = [k for k in ("switch", "server", "firewall") if k in text.lower()]
    return (90 if hit else 10, "REVIEW" if hit else "SKIP", [{"id": "net", "name": "Networking", "group": "Infra"}] if hit else [],
            hit, {"overall_verdict": "REVIEW", "disqualification_reason": None, "gates": {}})


def row(source, raw_id, title, closing, **kw):
    r = {"source": source, "raw_id": raw_id, "title": title, "description": "", "department": "", "advertised": "",
         "closing": closing, "doc_url": "", "detail_url": ""}
    r.update(kw)
    return r


def portal(rows, complete=True, error=None, pages=1):
    return {"rows": rows, "pages": pages, "complete": complete, "error": error, "reported_total": None}


def results(sindh=None, ppra=None, epads=None):
    return {"Sindh Bank": sindh or portal([]), "PPRA": ppra or portal([]), "EPADS": epads or portal([])}


# ── dates ──
@pytest.mark.parametrize("text,expect,kind", [
    ("08-Dec-26", "2026-12-08 23:59", "date"), ("30-Sept-2024", "2024-09-30 23:59", "date"),
    ("9-Jan-27", "2027-01-09 23:59", "date"), ("Dec 22, 2026 11:00 AM", "2026-12-22 11:00", "datetime"),
    ("Dec 22, 2026\n11:00 AM", "2026-12-22 11:00", "datetime"), ("Nov 27, 2026 02:15 PM", "2026-11-27 14:15", "datetime"),
    ("Thursday, November 5, 2026 05:20 PM", "2026-11-05 17:20", "datetime"), ("November 25, 2026", "2026-11-25 23:59", "date"),
    ("2026-11-25", "2026-11-25 23:59", "date"), ("25/11/2026", "2026-11-25 23:59", "date"), ("25.11.2026", "2026-11-25 23:59", "date"),
])
def test_closing_formats(text, expect, kind):
    dt, k = parse_closing(text, NOW)
    assert dt.strftime("%Y-%m-%d %H:%M") == expect and k == kind and dt.utcoffset() == timedelta(hours=5)


def test_relative_closing_becomes_a_real_time():
    dt, kind = parse_closing("15h 37m Left", NOW)
    assert kind == "relative" and dt == (NOW + timedelta(hours=15, minutes=37)).astimezone(PKT)
    assert parse_closing("2d 5h Left", NOW)[0] == (NOW + timedelta(days=2, hours=5)).astimezone(PKT)


@pytest.mark.parametrize("text,kind", [("", "missing"), (None, "missing"), ("TBA", "unreadable"), ("41-Nov-2026", "unreadable"), ("Left", "unreadable")])
def test_bad_closing_is_never_guessed(text, kind):
    assert parse_closing(text, NOW) == (None, kind)


def test_days_left_counts_pakistan_calendar_days():
    assert days_left(datetime(2026, 11, 22, 11, 0, tzinfo=PKT), NOW) == 3


# ── ids ──
def test_ppra_id_never_carries_the_notice_type():
    for raw in ("TS0000017741E", "TS0000017741E Procurement", "TS0000017741EProcurement", "ts0000017741e\nFramework Agreement"):
        assert canonical_id("PPRA", raw) == "PPRA-TS0000017741E"
    assert canonical_id("PPRA", "FW0000017734E|Framework Agreement") == "PPRA-FW0000017734E"
    assert canonical_id("PPRA", "no number here") is None


def test_existing_suffixed_ppra_document_is_reused_not_duplicated():
    assert resolve_existing_id("PPRA-TS1E", "PPRA", {"PPRA-TS1E-Procurement"}) == "PPRA-TS1E-Procurement"
    assert resolve_existing_id("PPRA-TS1E", "PPRA", {"PPRA-TS1E", "PPRA-TS1E-Procurement"}) == "PPRA-TS1E"
    assert resolve_existing_id("PPRA-TS1E", "PPRA", set()) == "PPRA-TS1E"


def test_sindh_and_epads_ids():
    assert canonical_id("Sindh Bank", "S-26110847107", "x") == "S-26110847107"
    assert canonical_id("Sindh Bank", "EPADS-S-250161427", "x") == "S-250161427"
    assert canonical_id("Sindh Bank", "S-S-250703270", "x") == "S-250703270"
    a = canonical_id("Sindh Bank", "", "Renovation of Tando Jam Branch", "01-Jan-25")
    assert a.startswith("SB-") and a == canonical_id("Sindh Bank", " ", "renovation of  TANDO JAM branch!", "01-jan-25")
    assert canonical_id("Sindh Bank", "", "", "") is None
    assert canonical_id("EPADS", "P188832") == "EPADS-P188832"


# ── parsers on the real page structure ──
def test_parse_sindh_fixture():
    rows = parsers.parse_sindh(fx("sindh.html"))
    assert len(rows) == 20
    first = rows[0]
    assert first["raw_id"] == "S-26110847107" and first["closing"] == "08-Dec-26" and first["department"] == "Admin"
    assert first["doc_url"].startswith("https://www.sindhbank.com.pk/wp-content/uploads/") and " " not in first["doc_url"]
    assert any(not r["closing"] for r in rows), "the bank's archive rows have an empty closing cell"


def test_parse_ppra_fixture():
    html = fx("ppra_page1.html")
    rows = parsers.parse_ppra(html)
    assert len(rows) == 12 and parsers.ppra_total(html) == 2053
    r = rows[0]
    assert r["raw_id"] == "TS0000018503E" and r["notice_type"] == "Procurement"
    assert r["title"] == "Invitation to E-Bid" and "\n" not in r["closing"] and r["closing"] == "Dec 22, 2026 11:00 AM"
    assert r["detail_url"].endswith("/tender-details/TS0000018503E") and r["department"].startswith("Oil and Gas")
    assert len({x["raw_id"] for x in rows}) == 12, "titles stay attached to their own tender number"


def test_parse_epads_fixture():
    rows = parsers.parse_epads(fx("epads_page1.html"))
    assert len(rows) == 12 and rows[0]["raw_id"] == "P188832" and rows[0]["closing"].endswith("Left")
    assert "..." not in rows[1]["title"], "the full title is read, not the truncated one"


# ── paging and completeness ──
def test_paging_reads_until_the_end_and_reports_complete():
    pages = {1: fx("ppra_page1.html")}
    calls = []

    def get(url):
        calls.append(url)
        return pages.get(int(url.split("page=")[1]), "<html><body>" + "x" * 600 + "</body></html>")
    r = portals._paged("PPRA", lambda p: "u?page=%d" % p, parsers.parse_ppra, get, 50, 0)
    assert len(r["rows"]) == 12 and r["complete"] and r["pages"] == 2 and len(calls) == 2


def test_a_failed_page_marks_the_portal_incomplete():
    r = portals._paged("PPRA", lambda p: "u?page=%d" % p, parsers.parse_ppra, lambda u: fx("ppra_page1.html") if u.endswith("=1") else None, 50, 0)
    assert len(r["rows"]) == 12 and not r["complete"] and "did not respond" in r["error"]


def test_fewer_rows_than_the_portal_reports_is_incomplete():
    one = fx("ppra_page1.html")
    r = portals._paged("PPRA", lambda p: "u?page=%d" % p, parsers.parse_ppra, lambda u: one, 50, 0, total_of=parsers.ppra_total)
    assert not r["complete"] and "2053" in r["error"]


def test_page_limit_marks_incomplete():
    import itertools
    n = itertools.count()
    html = lambda u: fx("ppra_page1.html").replace("TS00000", "TS%05d" % next(n))
    r = portals._paged("PPRA", lambda p: "u?page=%d" % p, parsers.parse_ppra, html, 3, 0)
    assert not r["complete"] and "safety limit" in r["error"]


def test_sindh_portal_down():
    assert portals.fetch_sindh(lambda u: None)["complete"] is False


# ── engine ──
def plan_for(res, previous=None, last=None, now=NOW):
    return run_scan(res, previous or {}, now, score_stub, "scorer-test", last)


def test_only_qualified_tenders_are_written_with_the_fixed_fields():
    p = plan_for(results(ppra=portal([row("PPRA", "TS0000000001E", "Core switch supply", "Dec 01, 2026 11:00 AM"),
                                      row("PPRA", "TS0000000002E", "Office furniture", "Dec 01, 2026 11:00 AM")])))
    assert [u["id"] for u in p["upserts"]] == ["PPRA-TS0000000001E"]
    d = p["upserts"][0]["data"]
    assert set(d) <= set(SCAN_FIELDS) and d["open"] is True and d["days"] == 12 and d["cl_iso"] == "2026-12-01"
    assert d["closing_at"] == "2026-12-01T11:00:00+05:00" and d["score"] >= SCORE_THRESHOLD and d["lastScan"] == "2026-11-19"
    assert tuple(sorted(p["scan"])) == tuple(sorted(SCAN_KEYS))


def test_a_tender_without_a_date_is_never_open_and_never_created():
    p = plan_for(results(sindh=portal([row("Sindh Bank", "S-1234567", "Server supply", "")])))
    assert p["upserts"] == [] and p["scan"]["date_missing_count"] == 1
    p = plan_for(results(sindh=portal([row("Sindh Bank", "S-1234567", "Server supply", "")])),
                 {"S-1234567": {"source": "Sindh Bank", "open": True, "cl": ""}})
    d = p["upserts"][0]["data"]
    assert d["open"] is False and d["date_missing"] is True and d["days"] is None


def test_a_stored_date_is_not_wiped_by_an_empty_one():
    prev = {"S-1234567": {"source": "Sindh Bank", "open": True, "cl": "05-Dec-2026", "doc": "https://x/y.pdf"}}
    d = plan_for(results(sindh=portal([row("Sindh Bank", "S-1234567", "Server supply", "")])), prev)["upserts"][0]["data"]
    assert "cl" not in d and "cl_iso" not in d and "doc" not in d and d["open"] is True and d["date_missing"] is False


def test_a_date_typed_by_a_person_keeps_the_tender_open():
    prev = {"S-1234567": {"source": "Sindh Bank", "open": False, "cl": "", "cl_manual": "2026-12-05"}}
    d = plan_for(results(sindh=portal([row("Sindh Bank", "S-1234567", "Server supply", "")])), prev)["upserts"][0]["data"]
    assert d["open"] is True and "cl" not in d and "cl_manual" not in d


def test_relative_closing_is_stored_as_a_real_date():
    d = plan_for(results(epads=portal([row("EPADS", "P188832", "Firewall renewal", "15h 37m Left")])))["upserts"][0]["data"]
    assert "Left" not in d["cl"] and d["cl_iso"] == "2026-11-20" and d["open"] is True


def test_expired_tender_is_written_closed():
    d = plan_for(results(ppra=portal([row("PPRA", "TS0000000001E", "Core switch", "Nov 18, 2026 11:00 AM")])))["upserts"][0]["data"]
    assert d["open"] is False and d["days"] == -1


def test_missing_tender_is_closed_only_when_the_portal_was_read_completely():
    prev = {"PPRA-TS0000000009E": {"source": "PPRA", "open": True, "cl": "Dec 20, 2026"}}
    seen = [row("PPRA", "TS0000000001E", "Core switch", "Dec 01, 2026 11:00 AM")]
    done = plan_for(results(ppra=portal(seen)), prev)
    assert [(c["id"], c["reason"]) for c in done["closures"]] == [("PPRA-TS0000000009E", "not_on_portal")]
    part = plan_for(results(ppra=portal(seen, complete=False, error="page 6 did not respond")), prev)
    assert part["closures"] == [] and "ppra" in part["scan"]["closures_skipped"] and part["warnings"]
    assert part["scan"]["status"] == "partial"


def test_row_count_guard_stops_a_bad_scrape_from_closing_a_portal():
    """19 Nov 2026: Sindh Bank returned 258 rows instead of 872 and 415 tenders were closed."""
    prev = {"S-%07d" % i: {"source": "Sindh Bank", "open": True, "cl": "20-Dec-2026"} for i in range(100)}
    rows = [row("Sindh Bank", "S-9999999", "Server supply", "20-Dec-2026")] * 258
    p = plan_for(results(sindh=portal(rows)), prev, last={"sindh": 872})
    assert p["closures"] == [] and "258 rows against 872" in p["scan"]["closures_skipped"]["sindh"]
    assert len(plan_for(results(sindh=portal(rows)), prev, last={"sindh": 300})["closures"]) == 100


def test_a_tender_still_listed_but_below_the_threshold_is_not_closed():
    prev = {"PPRA-TS0000000002E": {"source": "PPRA", "open": True, "cl": "Dec 20, 2026"}}
    p = plan_for(results(ppra=portal([row("PPRA", "TS0000000002E", "Office furniture", "Dec 20, 2026 11:00 AM")])), prev)
    assert p["closures"] == [] and p["upserts"] == []


def test_stored_tender_that_no_longer_qualifies_is_corrected_not_left_stale():
    """Earlier scans stored wrong titles and scores under real tender numbers."""
    prev = {"PPRA-TS0000000002E": {"source": "PPRA", "open": True, "cl": "Dec 20, 2026", "score": 95, "ti": "Cisco switch renewal"}}
    p = plan_for(results(ppra=portal([row("PPRA", "TS0000000002E", "Hiring of Retainer Doctor", "Dec 20, 2026 11:00 AM")])), prev)
    d = p["upserts"][0]["data"]
    assert d["ti"] == "Hiring of Retainer Doctor" and d["score"] < SCORE_THRESHOLD
    assert p["scan"]["demoted_count"] == 1 and p["scan"]["qualified_count"] == 0 and p["scan"]["open_qualified_count"] == 0
    again = plan_for(results(ppra=portal([row("PPRA", "TS0000000002E", "Hiring of Retainer Doctor", "Dec 20, 2026 11:00 AM")])),
                     {"PPRA-TS0000000002E": dict(prev["PPRA-TS0000000002E"], score=d["score"])})
    assert again["upserts"] == [], "once corrected it is not written again"


def test_stored_tender_whose_date_passed_is_closed_even_if_the_portal_failed():
    prev = {"PPRA-TS0000000003E": {"source": "PPRA", "open": True, "cl": "Nov 10, 2026"}}
    p = plan_for(results(ppra=portal([], complete=False, error="down")), prev)
    assert [(c["id"], c["reason"]) for c in p["closures"]] == [("PPRA-TS0000000003E", "closing_passed")]


def test_suffixed_twin_is_updated_in_place_and_counted_once():
    prev = {"PPRA-TS0000000001E-Procurement": {"source": "PPRA", "open": True, "cl": "Dec 01, 2026"}}
    p = plan_for(results(ppra=portal([row("PPRA", "TS0000000001E", "Core switch", "Dec 01, 2026 11:00 AM")])), prev)
    assert [(u["id"], u["exists"]) for u in p["upserts"]] == [("PPRA-TS0000000001E-Procurement", True)] and p["scan"]["new_count"] == 0
    both = dict(prev, **{"PPRA-TS0000000001E": {"source": "PPRA", "open": True, "cl": "Dec 01, 2026"}})
    p = plan_for(results(ppra=portal([row("PPRA", "TS0000000001E", "Core switch", "Dec 01, 2026 11:00 AM")])), both)
    assert [u["id"] for u in p["upserts"]] == ["PPRA-TS0000000001E"] and p["closures"] == [], "the twin is not closed as missing"


def test_sindh_duplicate_rows_keep_the_latest_date_and_the_document():
    rows = [row("Sindh Bank", "S-1234567", "Server supply", "01-Dec-2026", doc_url="https://x/rfp.pdf"),
            row("Sindh Bank", "S-1234567", "Server supply (Corrigendum)", "10-Dec-2026")]
    d = plan_for(results(sindh=portal(rows)))["upserts"][0]["data"]
    assert d["cl_iso"] == "2026-12-10" and d["doc"] == "https://x/rfp.pdf"


def test_rows_without_an_id_are_counted_not_guessed():
    p = plan_for(results(ppra=portal([row("PPRA", "", "Core switch", "Dec 01, 2026")])))
    assert p["upserts"] == [] and p["scan"]["skipped_no_id"] == 1


def test_same_inputs_give_the_same_plan():
    res = results(sindh=portal(parsers.parse_sindh(fx("sindh.html"))), ppra=portal(parsers.parse_ppra(fx("ppra_page1.html"))),
                  epads=portal(parsers.parse_epads(fx("epads_page1.html"))))
    a, b = plan_for(copy.deepcopy(res)), plan_for(copy.deepcopy(res))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_all_portals_down_is_a_failed_scan_that_closes_nothing():
    prev = {"PPRA-TS0000000009E": {"source": "PPRA", "open": True, "cl": "Dec 20, 2026"}}
    p = plan_for({s: portal([], complete=False, error="down") for s in ("Sindh Bank", "PPRA", "EPADS")}, prev)
    assert p["scan"]["status"] == "failed" and p["closures"] == [] and p["upserts"] == []


def test_validation_refuses_a_broken_plan():
    p = plan_for(results(ppra=portal([row("PPRA", "TS0000000001E", "Core switch", "Dec 01, 2026 11:00 AM")])))
    for breaker in (lambda d: d.update(assignee="someone"), lambda d: d.update(open="yes"),
                    lambda d: d.update(date_missing=True), lambda d: d.update(ti="a\nb"), lambda d: d.update(score=10), lambda d: d.update(score="90")):
        bad = copy.deepcopy(p)
        breaker(bad["upserts"][0]["data"])
        with pytest.raises(ScanError):
            validate(bad)
    bad = copy.deepcopy(p)
    bad["scan"]["extra_field"] = 1
    with pytest.raises(ScanError):
        validate(bad)


def test_naive_clock_is_rejected():
    with pytest.raises(ScanError):
        run_scan(results(), {}, datetime(2026, 11, 19), score_stub, "v")


def test_real_scorer_runs_through_the_engine():
    from scorer import score_tender
    res = results(ppra=portal(parsers.parse_ppra(fx("ppra_page1.html"))), sindh=portal(parsers.parse_sindh(fx("sindh.html"))))
    p = run_scan(res, {}, NOW, score_tender, "scorer-real")
    assert all(u["data"]["score"] >= SCORE_THRESHOLD for u in p["upserts"]) and p["scan"]["demoted_count"] == 0


# ── stores ──
def test_json_store_round_trip(tmp_path):
    state = tmp_path / "tenders"
    state.mkdir()
    (state / "PPRA-TS0000000001E-Procurement.json").write_text(json.dumps({"source": "PPRA", "open": True, "cl": "Dec 01, 2026", "assignee": "Iqra"}))
    (state / "broken.json").write_text("{not json")
    last = tmp_path / "last.json"
    last.write_text(json.dumps({"per_portal": {"sindh": 872, "ppra": 2053, "epads": 1174}}))
    store = JsonStore(str(state), str(tmp_path / "out"), str(last))
    prev = store.load_previous()
    assert list(prev) == ["PPRA-TS0000000001E-Procurement"] and store.last_counts()["ppra"] == 2053
    rows = [row("PPRA", "TS0000000001E", "Core switch", "Dec 01, 2026 11:00 AM")] + [row("PPRA", "TS%010dE" % i, "Server %d" % i, "Dec 02, 2026") for i in range(2, 120)]
    out = store.apply(plan_for(results(ppra=portal(rows)), prev, store.last_counts()))
    assert out["writes"] == 119 and len(out["batches"]) == 3
    first = json.loads(open(out["batches"][0]).read())
    assert len(first) == 50 and {w["op"] for w in first} <= {"set", "update"}
    upd = [w for b in out["batches"] for w in json.loads(open(b).read()) if w["doc_id"].endswith("-Procurement")][0]
    assert upd["op"] == "update" and "assignee" not in upd["data"]
    assert json.loads((tmp_path / "out" / "scan_record.json").read_text())["schema"] == 1


PG = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not PG, reason="set TEST_DATABASE_URL to a disposable Postgres database")
def test_postgres_store_end_to_end():
    from sqlalchemy import create_engine, text
    from tender_scan.stores import PostgresStore
    eng = PostgresStore(PG).engine
    with eng.begin() as c:
        for t in ("tenders", "scan_runs", "scan_logs"):
            c.execute(text("DROP TABLE IF EXISTS %s" % t))
        # the table exactly as the old scripts/github_scan.py created it, with one row a person has worked on
        c.execute(text("""CREATE TABLE tenders (id VARCHAR(100) PRIMARY KEY, title VARCHAR(500), department VARCHAR(100),
            advertised VARCHAR(50), closing VARCHAR(50), closing_date TIMESTAMP, is_open BOOLEAN DEFAULT TRUE,
            days_remaining INTEGER, score INTEGER DEFAULT 0, verdict VARCHAR(20), qual_verdict VARCHAR(20), qual_gates JSONB,
            disqualification_reason TEXT, matched_keywords JSONB DEFAULT '[]', matched_solutions JSONB DEFAULT '[]',
            document_url VARCHAR(1000), source_url VARCHAR(1000), created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())"""))
        c.execute(text("INSERT INTO tenders (id, title, closing, is_open, score, document_url) VALUES "
                       "('PPRA-TS0000000001E','old title','Dec 01, 2026',TRUE,80,'https://x/kept.pdf'),"
                       "('PPRA-TS0000000009E','gone','Dec 20, 2026',TRUE,80,NULL)"))
    store = PostgresStore(PG)
    prev = store.load_previous()
    assert prev["PPRA-TS0000000001E"]["open"] is True and store.last_counts() == {}
    with eng.begin() as c:
        c.execute(text("UPDATE tenders SET acquisition_status='AUTO_DOWNLOADED', local_folder='D:/x' WHERE id='PPRA-TS0000000001E'"))
    rows = [row("PPRA", "TS0000000001E", "Core switch supply", "Dec 03, 2026 11:00 AM", department="X" * 180),
            row("PPRA", "TS0000000002E", "Firewall renewal", "Dec 05, 2026 02:00 PM", detail_url="https://d/2")]
    plan = run_scan(results(ppra=portal(rows)), prev, NOW, score_stub, "scorer-test", {})
    store.apply(plan)
    store.apply(plan)                       # running twice must not duplicate or fail
    with eng.begin() as c:
        got = {r["id"]: dict(r) for r in c.execute(text("SELECT * FROM tenders")).mappings()}
        runs = c.execute(text("SELECT COUNT(*) FROM scan_runs")).scalar()
    a = got["PPRA-TS0000000001E"]
    assert a["title"] == "Core switch supply" and a["closing"] == "Dec 03, 2026 11:00 AM" and a["is_open"] is True
    assert a["acquisition_status"] == "AUTO_DOWNLOADED" and a["local_folder"] == "D:/x", "fields owned by others survive"
    assert a["document_url"] == "https://x/kept.pdf" and a["source_portal"] == "PPRA" and a["matched_keywords"] == ["switch"]
    assert a["closing_at"].astimezone(timezone.utc) == datetime(2026, 12, 3, 6, 0, tzinfo=timezone.utc)
    assert got["PPRA-TS0000000002E"]["detail_url"] == "https://d/2" and len(got) == 3
    assert got["PPRA-TS0000000009E"]["is_open"] is False and got["PPRA-TS0000000009E"]["not_on_portal_since"] == "2026-11-19"
    assert runs == 1 and store.last_counts() == {"sindh": 0, "ppra": 2, "epads": 0}


@pytest.mark.skipif(not PG, reason="set TEST_DATABASE_URL to a disposable Postgres database")
def test_postgres_plan_is_all_or_nothing():
    from sqlalchemy import create_engine, text
    from tender_scan.stores import PostgresStore
    eng = PostgresStore(PG).engine
    with eng.begin() as c:
        for t in ("tenders", "scan_runs", "scan_logs"):
            c.execute(text("DROP TABLE IF EXISTS %s" % t))
    store = PostgresStore(PG)
    plan = run_scan(results(ppra=portal([row("PPRA", "TS0000000001E", "Core switch", "Dec 03, 2026")])), store.load_previous(), NOW, score_stub, "v", {})
    plan["upserts"].append({"id": "X" * 300, "exists": False, "data": dict(plan["upserts"][0]["data"], id="X" * 300)})   # too long for the id column
    with pytest.raises(Exception):
        store.apply(plan)
    with eng.begin() as c:
        assert c.execute(text("SELECT COUNT(*) FROM tenders")).scalar() == 0, "a failed plan leaves nothing half-written"
