"""Tests for Agent 1b's SharePoint fetcher. No network and no Graph: files are built in memory.
Run: python -m pytest tests/test_rfp_fetch.py -q"""
import io
import json
import os
import sys
import zipfile
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from rfp_fetch import INLINE_BYTES  # noqa: E402
from rfp_fetch.engine import build_plan, validate  # noqa: E402
from rfp_fetch.extract import extract  # noqa: E402
from rfp_fetch.graph import share_id  # noqa: E402
from rfp_fetch.match import match_file  # noqa: E402
from rfp_fetch.store import write_batches  # noqa: E402

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
STAMP = "2026-11-25T12:00:00Z"


def text_pdf(text: str, pages: int = 1) -> bytes:
    """A minimal PDF with a real text layer, written by hand so the tests need no PDF library."""
    objs, kids = [], []
    font_id = 3 + 2 * pages
    for i in range(pages):
        stream = ("BT /F1 10 Tf 40 760 Td (%s) Tj ET" % text.replace("(", "").replace(")", "")).encode()
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        kids.append(page_id)
        objs.append((page_id, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                              b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (content_id, font_id)))
        objs.append((content_id, b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)))
    objs = [(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids), pages))] + objs
    objs.append((font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    out, offs = io.BytesIO(), {}
    out.write(b"%PDF-1.4\n")
    for n, body in sorted(objs):
        offs[n] = out.tell()
        out.write(b"%d 0 obj\n%s\nendobj\n" % (n, body))
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for n in range(1, len(objs) + 1):
        out.write(b"%010d 00000 n \n" % offs[n])
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


def blank_pdf() -> bytes:
    from pypdf import PdfWriter
    w, b = PdfWriter(), io.BytesIO()
    for _ in range(3):
        w.add_blank_page(612, 792)
    w.write(b)
    return b.getvalue()


def docx(paragraphs) -> bytes:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paragraphs)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", '<w:document %s><w:body>%s</w:body></w:document>' % (ns, body))
    return b.getvalue()


def tender(tid, **kw):
    d = {"id": tid, "open": True, "score": 80, "qualVerdict": "REVIEW", "source": tid.split("-")[0]}
    d.update(kw)
    return d


TENDERS = {
    "EPADS-P103237": tender("EPADS-P103237", source="EPADS"),
    "EPADS-P194040": tender("EPADS-P194040", source="EPADS"),
    "PPRA-TS0000080868E": tender("PPRA-TS0000080868E", source="PPRA"),
    "S-26110836621": tender("S-26110836621", source="Sindh Bank",
                            doc="https://www.sindhbank.com.pk/wp-content/uploads/2026/Super%20Capicator%202026%20BOQ.pdf"),
    "EPADS-P111111": tender("EPADS-P111111", source="EPADS", open=False),
}
LONG = "Scope of work: supply and installation of network switches and firewall. " * 20


def f(name, item, ctag="c1", size=100):
    return {"item_id": item, "drive_id": "DRIVE", "name": name, "size": size, "ctag": ctag, "modified": "2026-11-25T10:00:00Z",
            "web_url": "https://x/" + name}


# ---------- matching ----------
@pytest.mark.parametrize("name,expect", [
    ("P103237 Epads.pdf", "EPADS-P103237"),
    ("epads-p194040 bidding doc.pdf", "EPADS-P194040"),
    ("RFP 194040.pdf", "EPADS-P194040"),
    ("TS0000080868E tender.pdf", "PPRA-TS0000080868E"),
    ("PPRA 80868 RFP.pdf", "PPRA-TS0000080868E"),
    ("Super Capicator 2026 BOQ.pdf", "S-26110836621"),
    ("bidding-document (1).pdf", None),
    ("1032370 other.pdf", None),            # a longer number is not a match
    ("80868 RFP.pdf", None),               # a bare PPRA number needs the word PPRA
])
def test_match(name, expect):
    live = {k: v for k, v in TENDERS.items() if v["open"]}
    assert match_file(name, live)[0] == expect


def test_two_tenders_in_one_name_is_ambiguous():
    tid, cands = match_file("P103237 and P194040.pdf", TENDERS)
    assert tid is None and cands == ["EPADS-P103237", "EPADS-P194040"]


# ---------- extraction ----------
def test_pdf_text_and_scanned():
    r = extract("a.pdf", text_pdf(LONG[:180], pages=4))
    assert r["status"] == "read" and r["pages"] == 4 and "[Page 4]" in r["text"]
    s = extract("b.pdf", blank_pdf())
    assert s["status"] == "scanned" and s["chars"] == 0 and "OCR" in s["detail"]


def test_docx_and_unsupported():
    assert "Section 1" in extract("a.docx", docx(["Section 1", "Bill of quantities"]))["text"]
    assert extract("a.zip", b"PK")["status"] == "unsupported"
    assert extract("broken.pdf", b"not a pdf")["status"] == "failed"


# ---------- plan ----------
def run(files, blobs, analyses=None, **kw):
    return build_plan(files, TENDERS, analyses or {}, NOW, lambda fl: blobs[fl["item_id"]], **kw)


def by(plan, coll):
    return {w["doc_id"]: w for w in plan["writes"] if w["collection"] == coll}


def test_new_file_is_sent_with_stamp_and_status():
    files = [f("P103237 Epads.pdf", "I1"), f("bidding-document (1).pdf", "I2")]
    plan = run(files, {"I1": text_pdf(LONG[:200], 4), "I2": text_pdf("x")}, folder={"drive_id": "DRIVE", "item_id": "F", "name": "RFP"})
    a = by(plan, "rfp_analysis")["EPADS-P103237"]
    assert a["op"] == "set" and a["data"]["rfp_stamp"] == STAMP and a["data"]["rfpSource"] == "AGENT_1B_SHAREPOINT"
    assert a["data"]["rfpText"].startswith("===== FILE: P103237 Epads.pdf =====")
    assert a["data"]["docs"][0]["sp_item"] == "I1" and a["data"]["docs"][0]["sp_ctag"] == "c1"
    t = by(plan, "tenders")["EPADS-P103237"]["data"]
    assert t == {"acquisition_status": "SHAREPOINT", "acqStatus": "SHAREPOINT", "doc_accessible": True}
    assert plan["report"]["unmatched"] == ["bidding-document (1).pdf"]
    assert set(by(plan, "sp_index")) == {"I1", "I2"}
    assert by(plan, "config")["sharepoint"]["data"]["folder_uri"] == "file:///DRIVE/F"


def test_unchanged_file_is_not_downloaded_again():
    prev = {"EPADS-P103237": {"tender_id": "EPADS-P103237", "rfpText": "===== FILE: P103237 Epads.pdf =====\nold",
                              "docs": [{"name": "P103237 Epads.pdf", "sp_item": "I1", "sp_ctag": "c1"}], "summary": {"keep": 1}}}
    calls = []
    plan = build_plan([f("P103237 Epads.pdf", "I1")], TENDERS, prev, NOW, lambda fl: calls.append(fl) or b"")
    assert calls == [] and "rfp_analysis" not in {w["collection"] for w in plan["writes"]}
    assert plan["report"]["unchanged"][0]["tender"] == "EPADS-P103237"


def test_changed_file_replaces_its_own_section_and_keeps_analysis():
    prev = {"EPADS-P103237": {"tender_id": "EPADS-P103237",
                              "rfpText": "===== FILE: P103237 Epads.pdf =====\nold\n===== FILE: manual.pdf =====\nhuman upload",
                              "docs": [{"name": "P103237 Epads.pdf", "sp_item": "I1", "sp_ctag": "c1"}, {"name": "manual.pdf"}],
                              "summary": {"keep": 1}, "grading": {"keep": 1}}}
    plan = run([f("P103237 Epads.pdf", "I1", ctag="c2")], {"I1": text_pdf(LONG[:200], 4)}, analyses=prev)
    a = by(plan, "rfp_analysis")["EPADS-P103237"]
    assert a["op"] == "update"
    assert "human upload" in a["data"]["rfpText"] and "\nold\n" not in a["data"]["rfpText"]
    assert [d["name"] for d in a["data"]["docs"]] == ["manual.pdf", "P103237 Epads.pdf"]
    assert not {"summary", "grading", "compliance", "boq", "decision"} & set(a["data"])


def test_scanned_file_is_flagged_not_sent():
    plan = run([f("P194040.pdf", "I3")], {"I3": blank_pdf()})
    a = by(plan, "rfp_analysis")["EPADS-P194040"]["data"]
    assert "rfpText" not in a and "rfp_stamp" not in a and a["docs"][0]["read"] == "scanned"
    assert by(plan, "tenders")["EPADS-P194040"]["data"]["acquisition_status"] == "SHAREPOINT_SCANNED"
    assert plan["report"]["scanned"][0]["file"] == "P194040.pdf"


def test_closed_tender_is_never_written():
    plan = run([f("P111111.pdf", "I4")], {"I4": text_pdf(LONG)})
    assert "rfp_analysis" not in {w["collection"] for w in plan["writes"]}
    assert plan["report"]["not_live"][0]["tender"] == "EPADS-P111111"


def test_big_text_is_split_into_parts_like_the_workbench():
    big = text_pdf("A" * 3000, pages=40)
    files = [f("P103237 %d.pdf" % i, "B%d" % i) for i in range(4)]
    plan = run(files, {fl["item_id"]: big for fl in files})
    a = by(plan, "rfp_analysis")["EPADS-P103237"]["data"]
    parts = by(plan, "rfp_text")
    assert a["rfpText"] == "" and a["rfp_chars"] > INLINE_BYTES
    assert len(parts) >= 3 and all(p["data"]["stamp"] == STAMP for p in parts.values())
    assert "".join(parts["EPADS-P103237__%d" % i]["data"]["text"] for i in range(len(parts))).startswith("===== FILE:")


def test_index_removes_files_gone_from_the_folder():
    plan = run([], {}, sp_index={"OLD": {"item_id": "OLD"}})
    assert by(plan, "sp_index")["OLD"]["op"] == "delete"


def test_validate_refuses_foreign_fields():
    with pytest.raises(ValueError):
        validate({"writes": [{"op": "update", "collection": "rfp_analysis", "doc_id": "x", "data": {"summary": "no"}}]})


def test_batches_respect_limits(tmp_path):
    writes = [{"op": "set", "collection": "rfp_text", "doc_id": "t__%d" % i, "data": {"text": "x" * 50000}} for i in range(30)]
    paths = write_batches(writes, str(tmp_path))
    for p in paths:
        body = open(p, encoding="utf-8").read()
        assert len(json.loads(body)) <= 50 and len(body.encode()) < 1_000_000


def test_share_id_encoding():
    assert share_id("https://a.b/c?d=1") == "u!aHR0cHM6Ly9hLmIvYz9kPTE"
