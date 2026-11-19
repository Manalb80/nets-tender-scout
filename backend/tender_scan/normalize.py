"""One canonical id, title and closing string per tender, whatever the portal page looks like."""
import hashlib
import re
from typing import Dict, Iterable, Optional

SOURCES = ("Sindh Bank", "PPRA", "EPADS")
_PPRA_NO = re.compile(r"[A-Z]{2}\d{6,}[A-Z]?")
_PPRA_SUFFIX = re.compile(r"-(Procurement|Framework-Agreement|Disposal)$")
_EPADS_NO = re.compile(r"\bP(\d{4,})\b")
_SINDH_NO = re.compile(r"^(S-\d{6,}|T\d{4,5}-\d{2}-\d{3,5}|\d{5}-\d{2}-\d{4})$")


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()


def canonical_id(source: str, raw_id: str, title: str = "", advertised: str = "") -> Optional[str]:
    """The id a tender must be stored under. None means the row cannot be identified."""
    rid = squash(raw_id)
    if source == "PPRA":
        m = _PPRA_NO.search(rid.upper())
        return "PPRA-" + m.group(0) if m else None
    if source == "EPADS":
        m = _EPADS_NO.search(rid.upper()) or re.search(r"(\d{4,})$", rid)
        return "EPADS-P" + m.group(1) if m else None
    if source == "Sindh Bank":
        rid = re.sub(r"^(EPADS-|-)+", "", rid)          # the bank's own page prefixes some ids inconsistently
        rid = re.sub(r"^S-S-", "S-", rid)
        if _SINDH_NO.match(rid):
            return rid
        if not title_key(title):
            return None
        # Archive rows carry no number. The id is derived from the title and advertised date,
        # so the same row always gets the same id.
        digest = hashlib.sha1((title_key(title) + "|" + squash(advertised).lower()).encode("utf-8")).hexdigest()[:12]
        return "SB-" + digest
    return None


def ppra_base(doc_id: str) -> str:
    """PPRA-TS0000017741E-Procurement -> PPRA-TS0000017741E"""
    return _PPRA_SUFFIX.sub("", doc_id)


def resolve_existing_id(canon: str, source: str, existing_ids: Iterable[str]) -> str:
    """Earlier scans stored some PPRA tenders under a suffixed id. Keep writing to the document
    that already exists so nothing is orphaned; never create a second one for the same number."""
    ids = existing_ids if isinstance(existing_ids, (set, frozenset, dict)) else set(existing_ids)
    if canon in ids or source != "PPRA":
        return canon
    for suffix in ("-Procurement", "-Framework-Agreement", "-Disposal"):
        if canon + suffix in ids:
            return canon + suffix
    return canon


def clean_closing(text: str) -> str:
    return squash(text)[:60]


def clean_title(text: str) -> str:
    return squash(text)[:300]
