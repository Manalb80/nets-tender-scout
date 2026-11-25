"""Text from RFP files, without AI. PDF (pypdf), Word .docx, Excel .xlsx, and plain text.
A PDF whose pages carry no text layer is reported as scanned; it is never guessed at."""
import io
import re
import zipfile
from typing import Dict
from xml.etree import ElementTree as ET

from . import MAX_PAGES, SCANNED_MIN_CHARS

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str) -> str:
    return _CTRL.sub("", text or "")


def kind_of(name: str) -> str:
    n = name.lower()
    return ("pdf" if n.endswith(".pdf") else "word" if n.endswith((".docx", ".doc")) else
            "excel" if n.endswith((".xlsx", ".xls", ".csv")) else "text" if n.endswith((".txt", ".md")) else "other")


def _pdf(data: bytes) -> Dict:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    n = len(r.pages)
    pages = []
    for i in range(min(n, MAX_PAGES)):
        try:
            pages.append("[Page %d]\n%s" % (i + 1, r.pages[i].extract_text() or ""))
        except Exception as e:  # one broken page must not lose the rest
            pages.append("[Page %d]\n(unreadable page: %s)" % (i + 1, type(e).__name__))
    return {"text": "\n".join(pages), "pages": n, "extracted": min(n, MAX_PAGES)}


def _docx(data: bytes) -> Dict:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    paras = ["".join(t.text or "" for t in p.iter(ns + "t")) for p in root.iter(ns + "p")]
    return {"text": "\n".join(p for p in paras if p.strip()), "pages": None, "extracted": None}


def _xlsx(data: bytes) -> Dict:
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(t.text or "" for t in si.iter(ns + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(ns + "si")]
        sheets = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        out = []
        for s in sheets:
            out.append("[Sheet %s]" % re.search(r"(\d+)", s.rsplit("/", 1)[1]).group(1))
            for row in ET.fromstring(z.read(s)).iter(ns + "row"):
                cells = []
                for c in row.iter(ns + "c"):
                    v = c.find(ns + "v")
                    if v is None:
                        is_ = c.find(ns + "is")
                        cells.append("".join(t.text or "" for t in is_.iter(ns + "t")) if is_ is not None else "")
                    elif c.get("t") == "s":
                        cells.append(shared[int(v.text)] if v.text and int(v.text) < len(shared) else "")
                    else:
                        cells.append(v.text or "")
                if any(x.strip() for x in cells):
                    out.append(" | ".join(cells))
    return {"text": "\n".join(out), "pages": len(sheets), "extracted": len(sheets)}


def extract(name: str, data: bytes) -> Dict:
    """-> {text, pages, extracted, chars, status}. status: read | scanned | unsupported | failed."""
    k = kind_of(name)
    try:
        if k == "pdf":
            res = _pdf(data)
        elif k == "word" and name.lower().endswith(".docx"):
            res = _docx(data)
        elif k == "excel" and name.lower().endswith(".xlsx"):
            res = _xlsx(data)
        elif k in ("text",) or name.lower().endswith(".csv"):
            res = {"text": data.decode("utf-8", "replace"), "pages": None, "extracted": None}
        else:
            return {"text": "", "pages": None, "extracted": 0, "chars": 0, "status": "unsupported",
                    "detail": "Only PDF, DOCX, XLSX, CSV and TXT are read. Save older .doc/.xls files in the new format."}
    except Exception as e:
        return {"text": "", "pages": None, "extracted": 0, "chars": 0, "status": "failed", "detail": "%s: %s" % (type(e).__name__, e)}
    text = clean(res["text"])
    chars = len(re.sub(r"\s+", "", re.sub(r"\[(?:Page|Sheet) \d+\]", "", text)))
    status = "read" if chars >= SCANNED_MIN_CHARS or k != "pdf" else "scanned"
    if k != "pdf" and chars == 0:
        status = "failed"
    out = dict(res, text=text, chars=chars, status=status)
    if status == "scanned":
        out["detail"] = "No text layer: the PDF is pictures of pages. Ask for a text PDF or OCR it and save it back."
    return out
