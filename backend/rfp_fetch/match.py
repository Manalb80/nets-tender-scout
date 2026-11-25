"""Match a SharePoint file name to a live tender. Deterministic: a file is matched only when exactly one
live tender's portal number appears in its name as a whole token. Anything else is left for a person.

  EPADS-P194040        matches "P194040", "p-194040", or "194040" as a separate number
  PPRA-TS0000080868E   matches "TS0000080868E", or "80868" as a separate number next to the word PPRA
  S-26110836621        matches the id, or the PDF file name from the tender's "doc" url
  any tender           matches its full dashboard id, e.g. "EPADS-P194040 RFP.pdf"
"""
import os
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from . import LIVE_SCORE


def is_live(t: Dict) -> bool:
    return t.get("open") is True and (t.get("score") or 0) >= LIVE_SCORE and t.get("qualVerdict") != "NOGO"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _has_token(name_norm: str, token: str) -> bool:
    return bool(token) and re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", name_norm) is not None


def keys_for(t: Dict) -> List[Tuple[str, bool]]:
    """(normalised token, needs a PPRA word nearby)."""
    tid = str(t.get("id") or "")
    keys = [(_norm(tid), False)]
    m = re.match(r"EPADS-P(\d+)$", tid, re.I)
    if m:
        keys += [("p" + m.group(1), False), ("p " + m.group(1), False), (m.group(1), False)]
    m = re.match(r"PPRA-((?:TS|FW)\d+[A-Z]?)$", tid, re.I)
    if m:
        keys.append((m.group(1).lower(), False))
        num = re.sub(r"\D", "", m.group(1)).lstrip("0")
        if len(num) >= 4:
            keys.append((num, True))
    if t.get("source") == "Sindh Bank" or tid.startswith(("S-", "SB-")):
        doc = t.get("doc") or ""
        if doc:
            base = os.path.splitext(os.path.basename(unquote(urlparse(doc).path)))[0]
            if len(_norm(base)) >= 6:
                keys.append((_norm(base), False))
    return [k for k in keys if k[0]]


def match_file(name: str, tenders: Dict[str, Dict]) -> Tuple[Optional[str], List[str]]:
    """Returns (tender_id or None, every candidate id). None with candidates means ambiguous."""
    stem = _norm(os.path.splitext(name)[0])
    hits = []
    for tid, t in tenders.items():
        for token, needs_ppra in keys_for(t):
            if _has_token(stem, token) and (not needs_ppra or "ppra" in stem.split()):
                hits.append(tid)
                break
    hits = sorted(set(hits))
    return (hits[0] if len(hits) == 1 else None), hits
