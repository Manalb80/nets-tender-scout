"""Portal HTML -> raw rows. Pure functions: no network, no clock, no database."""
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .normalize import squash

SINDH_URL = "https://www.sindhbank.com.pk/tenders/"
PPRA_BASE = "https://epms.ppra.gov.pk"
PPRA_URL = PPRA_BASE + "/public/tenders/active-tenders"
EPADS_BASE = "https://epads.gov.pk"


def _row(source, raw_id, title, **kw) -> Dict:
    r = {"source": source, "raw_id": squash(raw_id), "title": squash(title), "description": "", "department": "",
         "advertised": "", "closing": "", "doc_url": "", "detail_url": ""}
    r.update({k: (squash(v) if isinstance(v, str) else v) for k, v in kw.items()})
    return r


def parse_sindh(html: str) -> List[Dict]:
    """sindhbank.com.pk/tenders: one table, nine columns:
    id, tender name (link = tender document), advertisement, advertised, closing, opening, BER, CEF, department."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue
            title = tds[1].get_text(" ", strip=True)
            if len(squash(title)) < 4:
                continue
            link = tds[1].find("a", href=True)
            doc = urljoin(SINDH_URL, link["href"]) if link and link["href"].strip() else ""
            out.append(_row("Sindh Bank", tds[0].get_text(" ", strip=True), title,
                            department=tds[8].get_text(" ", strip=True) if len(tds) > 8 else "",
                            advertised=tds[3].get_text(" ", strip=True), closing=tds[4].get_text(" ", strip=True),
                            doc_url=doc.replace(" ", "%20")))
    return out


def ppra_total(html: str) -> Optional[int]:
    m = re.search(r"Showing\s+\d+\s+of\s+([\d,]+)\s+tenders", html)
    return int(m.group(1).replace(",", "")) if m else None


def parse_ppra(html: str) -> List[Dict]:
    """epms.ppra.gov.pk active tenders. Each tender is an 8-cell row:
    checkbox, serial, tender no (+ notice type badge), details, status, advertised, closing, actions.
    It is followed by a single-cell row holding the organisation."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) != 8:
            continue
        strong = tds[2].find("strong")
        raw_id = strong.get_text(strip=True) if strong else tds[2].get_text(" ", strip=True)
        badge = tds[2].find(class_="badge")
        t_strong = tds[3].find("strong")
        title = t_strong.get_text(" ", strip=True) if t_strong else tds[3].get_text(" ", strip=True)
        desc = " ".join(s.get_text(" ", strip=True) for s in tds[3].find_all("small")
                        if "badge" not in (s.get("class") or []))
        detail = ""
        for a in tds[7].find_all("a", href=True):
            if "tender-details" in a["href"]:
                detail = urljoin(PPRA_BASE, a["href"])
        dept = ""
        nxt = tr.find_next_sibling("tr")
        if nxt is not None and len(nxt.find_all("td", recursive=False)) == 1:
            parts = [p.strip() for p in nxt.get_text("|", strip=True).split("|")]
            if "Organization" in parts:
                i = parts.index("Organization")
                dept = parts[i + 2] if len(parts) > i + 2 and parts[i + 2] != "Tender Type" else (parts[i + 1] if len(parts) > i + 1 else "")
        out.append(_row("PPRA", raw_id, title, description=desc, department=dept,
                        notice_type=badge.get_text(" ", strip=True) if badge else "",
                        status=tds[4].get_text(" ", strip=True),
                        advertised=tds[5].get_text(" ", strip=True), closing=tds[6].get_text(" ", strip=True),
                        detail_url=detail))
    return out


def parse_epads(html: str) -> List[Dict]:
    """epads.gov.pk opportunities. Cells: #, title + department + reference, published/closing, type, details.
    The visible title is truncated; the full text is in the span's title attribute."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-cb")
    out = []
    if not table:
        return out
    for tr in table.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 4:
            continue
        a = tds[1].find("a", href=True)
        if not a:
            continue
        span = a.find("span")
        title = (span.get("title") if span and span.get("title") else a.get_text(" ", strip=True))
        text1 = tds[1].get_text("|", strip=True)
        ref = re.search(r"\bP\d{4,}\b", text1)
        dept = ""
        spans = tds[1].find_all("span", recursive=False)
        if spans:
            dept = spans[0].get("title") or spans[0].get_text(" ", strip=True)
        dept = re.sub(r"\s*\([^)]*\)\s*$", "", squash(dept))
        text2 = tds[2].get_text("|", strip=True)
        pub = re.search(r"Published On:\|?([^|]+)", text2)
        clo = re.search(r"Closing On:\|?([^|]+)", text2)
        out.append(_row("EPADS", ref.group(0) if ref else a["href"].rstrip("/").split("/")[-1], title,
                        department=dept, advertised=pub.group(1) if pub else "", closing=clo.group(1) if clo else "",
                        detail_url=urljoin(EPADS_BASE, a["href"])))
    return out
