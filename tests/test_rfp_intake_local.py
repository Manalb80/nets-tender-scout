"""Tests for Agent 1b's local / OneDrive-synced folder intake. Real files in a temp folder, no network.
Run: python -m pytest tests/test_rfp_intake_local.py -q"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))
from rfp_fetch import cli  # noqa: E402
from rfp_fetch import sources  # noqa: E402
from rfp_fetch.engine import build_plan  # noqa: E402
from rfp_fetch.sources import HashCache, LocalFolderSource  # noqa: E402
from test_rfp_fetch import LONG, NOW, TENDERS, blank_pdf, text_pdf  # noqa: E402

OLD = time.time() - 3600


def put(folder, rel, data, mtime=OLD):
    p = os.path.join(folder, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    os.utime(p, (mtime, mtime))
    return p


def src(folder, **kw):
    kw.setdefault("recheck_seconds", 0)
    return LocalFolderSource(str(folder), **kw)


def plan_for(s, analyses=None, tenders=TENDERS, **kw):
    return build_plan(s.list_files(), tenders, analyses or {}, NOW, s.read, kind="local", **kw)


def by(plan, coll):
    return {w["doc_id"]: w for w in plan["writes"] if w["collection"] == coll}


# ---------- the folder ----------
def test_partial_and_lock_files_are_ignored(tmp_path):
    for n in ("~$P103237.docx", "P103237.pdf.crdownload", "P103237.part", "desktop.ini", ".hidden.pdf"):
        put(tmp_path, n, b"x")
    put(tmp_path, "P103237.pdf", b"real")
    assert [f["name"] for f in src(tmp_path).list_files()] == ["P103237.pdf"]


def test_fresh_file_waits_until_stable(tmp_path):
    put(tmp_path, "P103237.pdf", b"data", mtime=time.time())
    s = src(tmp_path, stable_seconds=30)
    assert s.list_files() == [] and "waiting" in s.waiting[0]["reason"]


def test_file_growing_during_check_waits(tmp_path):
    p = put(tmp_path, "P103237.pdf", b"part one")

    def grow(_):
        with open(p, "ab") as f:
            f.write(b" and more")
        os.utime(p, (OLD + 5, OLD + 5))
    s = LocalFolderSource(str(tmp_path), recheck_seconds=1, sleep=grow)
    assert s.list_files() == [] and s.waiting[0]["reason"] == "still being written"


def test_empty_file_waits(tmp_path):
    put(tmp_path, "P103237.pdf", b"")
    s = src(tmp_path)
    assert s.list_files() == [] and "empty" in s.waiting[0]["reason"]


def test_hash_cache_skips_rehashing_unchanged_files(tmp_path, monkeypatch):
    put(tmp_path / "in", "P103237.pdf", b"content")
    cache = HashCache(str(tmp_path / "cache.json"))
    first = src(tmp_path / "in", cache=cache).list_files()[0]
    cache.save()
    monkeypatch.setattr(sources, "sha256_file", lambda p: pytest.fail("re-hashed an unchanged file"))
    again = src(tmp_path / "in", cache=HashCache(str(tmp_path / "cache.json"))).list_files()[0]
    assert again["sha256"] == first["sha256"] and first["item_id"] == "sha256:" + first["sha256"]


def test_archive_dir_inside_the_folder_is_not_scanned(tmp_path):
    put(tmp_path, "P103237.pdf", b"a")
    put(tmp_path, "_archive/EPADS-P103237/P103237.pdf", b"a")
    assert [f["path"] for f in src(tmp_path, archive_dir=str(tmp_path / "_archive")).list_files()] == ["P103237.pdf"]


# ---------- the plan ----------
def test_new_local_file_is_sent_without_sharepoint_writes(tmp_path):
    put(tmp_path, "P103237 Epads.pdf", text_pdf(LONG[:200], 4))
    plan = plan_for(src(tmp_path))
    a = by(plan, "rfp_analysis")["EPADS-P103237"]["data"]
    assert a["rfpSource"] == "AGENT_1B_LOCAL" and a["rfp_stamp"] and a["rfpText"].startswith("===== FILE: P103237 Epads.pdf")
    d = a["docs"][0]
    assert d["read"] == "local" and len(d["file_sha256"]) == 64 and "sp_item" not in d
    assert by(plan, "tenders")["EPADS-P103237"]["data"]["acquisition_status"] == "SHAREPOINT"
    assert not by(plan, "sp_index") and not by(plan, "config")


def test_acq_status_can_be_auto_downloaded(tmp_path):
    put(tmp_path, "P103237.pdf", text_pdf(LONG[:200], 4))
    plan = plan_for(src(tmp_path), acq_status="AUTO_DOWNLOADED")
    assert by(plan, "tenders")["EPADS-P103237"]["data"]["acqStatus"] == "AUTO_DOWNLOADED"


def test_same_content_under_two_names_is_sent_once(tmp_path):
    pdf = text_pdf(LONG[:200], 4)
    put(tmp_path, "P103237 Epads.pdf", pdf)
    put(tmp_path, "P103237 Epads (copy).pdf", pdf)
    plan = plan_for(src(tmp_path))
    assert len(plan["report"]["sent"]) == 1 and len(plan["report"]["duplicate"]) == 1


def test_known_content_is_unchanged_even_if_renamed(tmp_path):
    put(tmp_path, "P103237 renamed.pdf", b"%PDF same bytes")
    sha = src(tmp_path).list_files()[0]["sha256"]
    prev = {"EPADS-P103237": {"docs": [{"name": "P103237.pdf", "file_path": "P103237.pdf", "file_sha256": sha}], "rfpText": "x"}}
    plan = plan_for(src(tmp_path), analyses=prev)
    assert plan["writes"] == [] and plan["report"]["unchanged"][0]["tender"] == "EPADS-P103237"
    assert [t for _, t in plan["archive"]] == ["EPADS-P103237"]


def test_new_version_replaces_old_entry_and_keeps_manual_upload(tmp_path):
    put(tmp_path, "P103237.pdf", text_pdf(LONG[:200], 4))
    prev = {"EPADS-P103237": {"rfpText": "===== FILE: P103237.pdf =====\nold\n===== FILE: manual.pdf =====\nhuman upload",
                              "docs": [{"name": "P103237.pdf", "file_path": "P103237.pdf", "file_sha256": "0" * 64},
                                       {"name": "manual.pdf"}], "summary": {"keep": 1}, "rfpSource": "MANUAL_UPLOAD"}}
    a = by(plan_for(src(tmp_path), analyses=prev), "rfp_analysis")["EPADS-P103237"]
    assert a["op"] == "update" and "human upload" in a["data"]["rfpText"] and "\nold\n" not in a["data"]["rfpText"]
    assert [d["name"] for d in a["data"]["docs"]] == ["manual.pdf", "P103237.pdf"]
    assert "rfpSource" not in a["data"] and "summary" not in a["data"]     # a person's source label is kept


def test_status_set_by_a_person_is_kept(tmp_path):
    put(tmp_path, "P103237.pdf", text_pdf(LONG[:200], 4))
    tenders = dict(TENDERS, **{"EPADS-P103237": dict(TENDERS["EPADS-P103237"], acquisition_status="MANUAL_UPLOADED")})
    plan = plan_for(src(tmp_path), tenders=tenders)
    assert "EPADS-P103237" not in by(plan, "tenders") and plan["report"]["kept_status"][0]["status"] == "MANUAL_UPLOADED"


def test_subfolder_name_can_carry_the_tender_number(tmp_path):
    put(tmp_path, "EPADS-P194040/bidding document.pdf", text_pdf(LONG[:200], 4))
    plan = plan_for(src(tmp_path))
    assert plan["report"]["sent"][0] == {"file": "EPADS-P194040/bidding document.pdf", "tender": "EPADS-P194040",
                                         "chars": plan["report"]["sent"][0]["chars"]}


def test_scanned_local_pdf_is_flagged(tmp_path):
    put(tmp_path, "P194040.pdf", blank_pdf())
    plan = plan_for(src(tmp_path))
    assert by(plan, "tenders")["EPADS-P194040"]["data"]["acquisition_status"] == "SHAREPOINT_SCANNED"
    assert plan["report"]["scanned"][0]["file"] == "P194040.pdf"


# ---------- the command, end to end ----------
def snapshot(tmp_path):
    state = tmp_path / "state"
    for tid, t in TENDERS.items():
        (state / "tenders").mkdir(parents=True, exist_ok=True)
        (state / "tenders" / (tid + ".json")).write_text(json.dumps(t))
    return state


def args(tmp_path, state, *extra):
    return ["--state", str(state), "--out", str(tmp_path / "out"), "--watch-dir", str(tmp_path / "in"),
            "--archive-dir", str(tmp_path / "archive"), "--cache", str(tmp_path / "cache.json"),
            "--stable-seconds", "0"] + list(extra)


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    for k in [k for k in os.environ if k.startswith(("RFP_", "SHAREPOINT_", "GRAPH_"))]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("RFP_RECHECK_SECONDS", "0")


def test_dry_run_writes_nothing(tmp_path, capsys):
    state = snapshot(tmp_path)
    put(tmp_path / "in", "P103237.pdf", text_pdf(LONG[:200], 4))
    assert cli.main(args(tmp_path, state, "--dry-run")) == 0
    assert "Dry run" in capsys.readouterr().out
    assert not (tmp_path / "out").exists() and not (tmp_path / "archive").exists() and not (tmp_path / "cache.json").exists()


def test_send_then_archive_on_the_next_run(tmp_path):
    state = snapshot(tmp_path)
    original = put(tmp_path / "in", "P103237.pdf", text_pdf(LONG[:200], 4))
    assert cli.main(args(tmp_path, state, "--apply-to-snapshot")) == 0
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["sent"][0]["tender"] == "EPADS-P103237" and report["archived"] == []
    # second run: the snapshot now holds the file, so nothing is planned and the file is archived (copy)
    assert cli.main(args(tmp_path, state)) == 0
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["writes"] == 0 and report["archived"][0]["tender"] == "EPADS-P103237"
    assert (tmp_path / "archive" / "EPADS-P103237" / "P103237.pdf").exists() and os.path.exists(original)
    assert sorted(os.listdir(tmp_path / "out")) == ["report.json"]    # no stale batches left behind


def test_move_mode_empties_a_staging_folder(tmp_path):
    state = snapshot(tmp_path)
    original = put(tmp_path / "in", "P103237.pdf", text_pdf(LONG[:200], 4))
    cli.main(args(tmp_path, state, "--apply-to-snapshot", "--archive-mode", "move"))
    cli.main(args(tmp_path, state, "--archive-mode", "move"))
    assert not os.path.exists(original) and (tmp_path / "archive" / "EPADS-P103237" / "P103237.pdf").exists()


def test_missing_folder_is_a_clear_error(tmp_path, capsys):
    state = snapshot(tmp_path)
    assert cli.main(["--state", str(state), "--watch-dir", str(tmp_path / "nope")]) == 2
    assert "RFP_WATCH_DIR" in capsys.readouterr().err
