"""
NETS Solution Scoring Engine.
Scores tenders against 15 NETS solution categories using word-boundary matching.
This is the same logic the Claude artifact uses, extracted as a standalone module.
"""
import re
from typing import List, Dict, Tuple

# ── NETS Solution Taxonomy (15 solutions across 3 groups) ──
SOLUTIONS = [
    {"id": "dc_infra",    "group": "Infrastructure", "name": "Data Centre Infrastructure",
     "keywords": ["data centre", "data center", "rack", "cooling", "ups", "precision cooling", "raised floor", "containment"]},
    {"id": "servers",     "group": "Infrastructure", "name": "Servers & Compute",
     "keywords": ["server", "dell server", "hpe server", "blade", "compute", "hyperconverged", "hci", "vmware", "virtualisation", "virtualization"]},
    {"id": "storage",     "group": "Infrastructure", "name": "Storage & Backup",
     "keywords": ["storage", "san", "nas", "backup", "data protection", "dell emc", "veeam", "commvault", "tape library"]},
    {"id": "networking",  "group": "Infrastructure", "name": "Networking",
     "keywords": ["network", "switch", "router", "cisco", "juniper", "aruba", "lan", "wan", "sd-wan", "sdwan", "wifi", "wireless", "access point"]},
    {"id": "security",    "group": "Infrastructure", "name": "Cybersecurity",
     "keywords": ["firewall", "security", "cybersecurity", "siem", "soar", "endpoint", "antivirus", "fortinet", "palo alto",
                   "checkpoint", "waf", "ids", "ips", "vulnerability", "penetration test", "soc", "noc"]},
    {"id": "cabling",     "group": "Infrastructure", "name": "Structured Cabling",
     "keywords": ["cabling", "structured cabling", "fibre", "fiber optic", "cat6", "cat7", "patch panel", "cable management"]},
    {"id": "power",       "group": "Infrastructure", "name": "Power & Electrical",
     "keywords": ["ups", "power", "generator", "pdu", "electrical", "battery", "power distribution"]},
    {"id": "cloud",       "group": "Digital", "name": "Cloud & Hybrid IT",
     "keywords": ["cloud", "azure", "aws", "hybrid cloud", "iaas", "paas", "saas", "migration", "cloud migration"]},
    {"id": "ai_auto",     "group": "Digital", "name": "AI & Automation",
     "keywords": ["artificial intelligence", "machine learning", "rpa", "automation", "chatbot", "nlp", "document processing", "ocr"]},
    {"id": "iot",         "group": "Digital", "name": "IoT & Smart Solutions",
     "keywords": ["iot", "internet of things", "smart building", "sensor", "scada", "building management", "bms"]},
    {"id": "solar",       "group": "Digital", "name": "Solar & Green IT",
     "keywords": ["solar", "renewable", "green energy", "solar panel", "photovoltaic", "pv system", "net metering"]},
    {"id": "dig_mail",    "group": "Digital", "name": "Digital Mailroom",
     "keywords": ["digital mailroom", "document management", "scanning", "digitisation", "digitization", "ecm"]},
    {"id": "managed_it",  "group": "Managed IT", "name": "Managed IT Services",
     "keywords": ["managed service", "outsourcing", "it support", "helpdesk", "service desk", "itil", "it management"]},
    {"id": "maintenance", "group": "Managed IT", "name": "Maintenance & Support",
     "keywords": ["maintenance", "annual maintenance", "amc", "support contract", "warranty", "sla", "break fix",
                   "hardware maintenance", "preventive maintenance", "corrective maintenance"]},
    {"id": "consult",     "group": "Managed IT", "name": "IT Consulting",
     "keywords": ["consulting", "consultancy", "advisory", "assessment", "audit", "roadmap", "strategy", "digital transformation"]},
]

# Short keywords (3 chars or fewer) need word-boundary matching to avoid false positives.
# Example: "ev" would match inside "Revised" without boundaries.
SHORT_KEYWORD_THRESHOLD = 3


def score_tender(title: str) -> Tuple[int, str, List[Dict], List[str]]:
    """
    Score a tender title against NETS solutions.

    Returns:
        (score, verdict, matched_solutions, matched_keywords)

    Scoring rules:
        2+ solution matches = 95
        1 match = 75
        0 matches = 0 (SKIP)
        Verdict: BID if score >= 70, REVIEW if 40-69, SKIP otherwise
    """
    title_lower = title.lower()
    matched_solutions = []
    matched_keywords = []
    seen_solution_ids = set()

    for sol in SOLUTIONS:
        for kw in sol["keywords"]:
            # Word-boundary regex for short keywords to prevent false positives
            if len(kw) <= SHORT_KEYWORD_THRESHOLD:
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, title_lower):
                    if sol["id"] not in seen_solution_ids:
                        matched_solutions.append({
                            "id": sol["id"],
                            "name": sol["name"],
                            "group": sol["group"]
                        })
                        seen_solution_ids.add(sol["id"])
                    if kw not in matched_keywords:
                        matched_keywords.append(kw)
            else:
                if kw in title_lower:
                    if sol["id"] not in seen_solution_ids:
                        matched_solutions.append({
                            "id": sol["id"],
                            "name": sol["name"],
                            "group": sol["group"]
                        })
                        seen_solution_ids.add(sol["id"])
                    if kw not in matched_keywords:
                        matched_keywords.append(kw)

    # Scoring
    match_count = len(matched_solutions)
    if match_count >= 2:
        score = 95
    elif match_count == 1:
        score = 75
    else:
        score = 0

    # Verdict
    if score >= 70:
        verdict = "BID"
    elif score >= 40:
        verdict = "REVIEW"
    else:
        verdict = "SKIP"

    return score, verdict, matched_solutions, matched_keywords


def get_solutions_list() -> List[Dict]:
    """Return the full NETS solution taxonomy for the frontend."""
    return [{"id": s["id"], "name": s["name"], "group": s["group"]} for s in SOLUTIONS]
