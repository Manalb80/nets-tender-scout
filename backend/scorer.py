"""
NETS Solution Scoring & Qualification Engine (Agent 1).
Two-phase evaluation:
  Phase 1: Domain keyword matching against 15 NETS solution categories.
  Phase 2: Hard qualification gates (turnover, OEM, domain, org history, resources).

Title-only tenders get Phase 1 scoring + Phase 2 defaults.
Full RFP text (when available) enables deep Phase 2 gate evaluation.
"""
import re
from typing import List, Dict, Tuple, Optional

# ── NETS Solution Taxonomy ──
# Source: NETS Corporate Profile Sep25 + NETS Cybersecurity Portfolio 300925
# 3 domains: Infrastructure Solutions | Digital Solutions | Managed Solutions
# 24 solution categories. Each has a "weight" (1 = core, 0.7 = adjacent, 0.4 = weak signal)
# so that generic words like "power" or "maintenance" do not outrank true NETS matches.

SOLUTIONS = [
    # ═══════════ INFRASTRUCTURE SOLUTIONS ═══════════
    {"id": "fttx",        "group": "Infrastructure", "name": "FTTX / Fibre Access Network", "weight": 1.0,
     "keywords": ["ftth", "fttx", "fttp", "gpon", "xgs-pon", "fibre to the home", "fiber to the home", "fibre optic",
                   "fiber optic", "optical fibre", "optical fiber", "ofc", "splicing", "fibre cable", "fiber cable",
                   "duct", "excavation", "home install", "premises survey", "rfs", "ready for service",
                   "last mile", "access network", "broadband rollout", "fibre rollout", "fiber rollout"]},
    {"id": "wireless_access", "group": "Infrastructure", "name": "Wireless Access & Mobile Sites", "weight": 1.0,
     "keywords": ["mobile site", "cell site", "bts", "tower", "microwave", "los survey", "line of sight",
                   "ibs", "in-building solution", "das", "distributed antenna", "small cell", "rollout site",
                   "4g", "5g", "lte", "radio access", "ran", "telecom site", "site survey"]},
    {"id": "elv",         "group": "Infrastructure", "name": "ELV Systems", "weight": 1.0,
     "keywords": ["elv", "extra low voltage", "cctv", "access control", "public address", "pa system",
                   "bms", "building management system", "fire alarm", "intrusion detection", "intercom",
                   "av system", "audio visual", "smart building", "structured cabling", "scs",
                   "cat6", "cat6a", "cat7", "patch panel", "cabling"]},
    {"id": "ev",          "group": "Infrastructure", "name": "EV Charging Solutions", "weight": 1.0,
     "keywords": ["ev charger", "ev charging", "electric vehicle charging", "charging station", "evse",
                   "dc fast charger", "ac charger"]},
    {"id": "dc_power",    "group": "Infrastructure", "name": "DC Power Systems", "weight": 0.9,
     "keywords": ["dc power", "rectifier", "-48v", "48v dc", "telecom power", "battery bank", "ups system",
                   "uninterruptible power", "power plant", "site power"]},
    {"id": "dc_infra",    "group": "Infrastructure", "name": "Data Centre Infrastructure", "weight": 1.0,
     "keywords": ["data centre", "data center", "datacenter", "rack", "racking", "shelving", "cooling",
                   "precision cooling", "raised floor", "containment", "data center commissioning",
                   "dc commissioning", "tier iii", "tier 3", "tier iv", "colocation", "pdu"]},
    {"id": "servers",     "group": "Infrastructure", "name": "Servers & Compute", "weight": 1.0,
     "keywords": ["server", "servers", "dell server", "hpe server", "hp server", "blade", "compute",
                   "hyperconverged", "hci", "vmware", "virtualisation", "virtualization", "hypervisor",
                   "rack mount server", "lenovo server", "proliant", "poweredge"]},
    {"id": "storage",     "group": "Infrastructure", "name": "Storage & Backup", "weight": 1.0,
     "keywords": ["storage", "san", "nas", "backup", "data protection", "dell emc", "veeam", "commvault",
                   "tape library", "storage array", "object storage", "disaster recovery", "dr site",
                   "business continuity", "bcp", "replication"]},
    {"id": "networking",  "group": "Infrastructure", "name": "Enterprise Networking (LAN/WAN/SD-WAN/ACI)", "weight": 1.0,
     "keywords": ["network", "switch", "switches", "router", "routers", "cisco", "juniper", "aruba", "h3c", "huawei",
                   "extreme networks", "lan", "wan", "sd-wan", "sdwan", "sd-lan", "aci", "mpls", "mpls-tp",
                   "core network", "enterprise network", "campus network", "wifi", "wi-fi", "wireless lan",
                   "wlan", "access point", "wlc", "wireless controller", "cambium", "d-link", "network core",
                   "nexus", "catalyst", "meraki"]},
    {"id": "uc",          "group": "Infrastructure", "name": "Unified Communications", "weight": 0.9,
     "keywords": ["ip phone", "ip-pbx", "ip pbx", "pbx", "voip", "unified communication", "video conferencing",
                   "ip telephony", "call manager", "cucm", "collaboration", "webex", "contact centre",
                   "contact center", "telephony"]},

    # ═══════════ DIGITAL SOLUTIONS ═══════════
    {"id": "cloud",       "group": "Digital", "name": "Cloud & Hybrid IT", "weight": 1.0,
     "keywords": ["cloud", "azure", "aws", "hybrid cloud", "private cloud", "public cloud", "iaas", "paas", "saas",
                   "cloud migration", "cloud native", "kubernetes", "container", "openstack", "telco cloud"]},
    {"id": "sec_network", "group": "Digital", "name": "Network Security (NGFW, VPN, NAC)", "weight": 1.0,
     "keywords": ["firewall", "firewalls", "ngfw", "next generation firewall", "next-gen firewall", "fortinet",
                   "fortigate", "palo alto", "checkpoint", "sophos", "vpn", "nac", "network access control",
                   "cisco ise", "identity services engine", "anyconnect", "secure access", "web application firewall",
                   "waf", "ids", "ips", "intrusion prevention", "idps", "ddos", "proxy", "web security",
                   "email security", "email gateway", "mimecast", "umbrella", "dns security"]},
    {"id": "sec_soc",     "group": "Digital", "name": "SOC / SIEM / SOAR / Monitoring", "weight": 1.0,
     "keywords": ["soc", "security operations", "security operations centre", "security operations center",
                   "siem", "soar", "qradar", "splunk", "sentinel", "insightidr", "24x7 monitoring", "24/7 monitoring",
                   "security monitoring", "threat intelligence", "threat hunting", "managed soc", "soc as a service",
                   "mdr", "managed detection", "log management", "incident response", "dfir",
                   "digital forensics", "post-breach", "mitre att&ck", "mitre attack", "playbook"]},
    {"id": "sec_endpoint", "group": "Digital", "name": "Endpoint & Threat Protection (EPP/EDR/XDR)", "weight": 1.0,
     "keywords": ["endpoint", "epp", "edr", "xdr", "ndr", "antivirus", "anti-virus", "antimalware", "anti-malware",
                   "kaspersky", "crowdstrike", "trend micro", "symantec", "endpoint protection",
                   "endpoint detection", "ransomware", "phishing", "anti-phishing", "patch management",
                   "virtual patching", "ivanti", "nbad", "anomaly detection"]},
    {"id": "sec_iam",     "group": "Digital", "name": "Identity & Access Management (IAM/PAM/MFA)", "weight": 1.0,
     "keywords": ["iam", "identity and access", "identity management", "pam", "privileged access",
                   "beyondtrust", "kron", "mfa", "multi-factor", "multifactor", "two-factor", "2fa", "sso",
                   "single sign-on", "single sign on", "zero trust", "ztna", "duo", "mdm", "mobile device management",
                   "maas360", "file integrity", "fim", "remote workforce"]},
    {"id": "sec_data",    "group": "Digital", "name": "Data & Cloud Security (DLP/Encryption/DAM)", "weight": 1.0,
     "keywords": ["dlp", "data loss prevention", "data leakage", "encryption", "database security", "dam",
                   "database activity monitoring", "guardium", "forcepoint", "data classification",
                   "data discovery", "getvisibility", "cloud security", "casb", "data privacy", "gdpr",
                   "pci dss", "pci-dss"]},
    {"id": "sec_vapt",    "group": "Digital", "name": "VAPT / Vulnerability Management", "weight": 1.0,
     "keywords": ["vapt", "vulnerability assessment", "penetration test", "penetration testing", "pentest",
                   "pen test", "red team", "red teaming", "vulnerability management", "nessus", "qualys",
                   "rapid7", "insightvm", "acunetix", "burp", "metasploit", "sast", "dast",
                   "application security", "web app security", "source code review", "black box", "grey box",
                   "white box", "security assessment", "breach and attack", "attackiq", "nipper",
                   "configuration audit", "network configuration audit"]},
    {"id": "sec_grc",     "group": "Digital", "name": "GRC / vCISO / Security Consulting", "weight": 1.0,
     "keywords": ["grc", "governance risk", "risk and compliance", "vciso", "virtual ciso", "ciso on demand",
                   "posture assessment", "security posture", "security consulting", "isms", "iso 27001",
                   "iso27001", "nist", "nist 800-53", "soc 2", "soc2", "security policy", "security audit",
                   "gap analysis", "maturity assessment", "security awareness", "awareness training",
                   "security training", "devsecops", "secure sdlc"]},
    {"id": "ai_auto",     "group": "Digital", "name": "Automation, AI/ML & DevOps", "weight": 0.9,
     "keywords": ["artificial intelligence", "machine learning", "ai/ml", "ai based", "ai-based", "rpa",
                   "robotic process", "automation", "hyper-automation", "chatbot", "nlp", "natural language",
                   "devops", "ci/cd", "pipeline", "microservice", "python", "ansible", "zero touch",
                   "ztp", "orchestration", "analytics", "dashboard", "dashboarding", "observability",
                   "monetx", "predictive analytics", "anomaly detection", "root cause"]},
    {"id": "nms",         "group": "Digital", "name": "NMS / Observability / ITSM Platforms", "weight": 1.0,
     "keywords": ["nms", "network management system", "network monitoring", "infrastructure monitoring",
                   "unified observability", "observability platform", "itsm", "it service management",
                   "servicenow", "service desk tool", "ticketing", "ticketing system", "cmdb",
                   "asset management", "inventory management", "ipam", "ip address management",
                   "ncm", "configuration management", "netflow", "apm", "application performance",
                   "supportx", "greenx", "mapx", "sustainability", "carbon", "co2"]},

    # ═══════════ MANAGED SOLUTIONS ═══════════
    {"id": "managed_om",  "group": "Managed", "name": "Managed O&M / AMC / Break-Fix", "weight": 1.0,
     "keywords": ["managed service", "managed services", "o&m", "operation and maintenance",
                   "operations and maintenance", "amc", "annual maintenance", "maintenance contract",
                   "support contract", "break fix", "break-fix", "tac support", "oem support", "rma",
                   "cm/pm", "preventive maintenance", "corrective maintenance", "hardware maintenance",
                   "warranty", "smartnet", "sla", "service level"]},
    {"id": "managed_noc", "group": "Managed", "name": "NOC / Helpdesk / L1-L2 Support", "weight": 1.0,
     "keywords": ["noc", "network operations centre", "network operations center", "helpdesk", "help desk",
                   "service desk", "it support", "l1", "l2", "l1/l2", "first line", "second line",
                   "incident management", "24/7 support", "24x7 support", "8/5", "itil", "it operations",
                   "remote monitoring", "managed helpdesk"]},
    {"id": "outsourcing", "group": "Managed", "name": "Resource Outsourcing / Staff Augmentation", "weight": 1.0,
     "keywords": ["outsourcing", "outsource", "resource augmentation", "staff augmentation", "manpower",
                   "skilled resources", "resident engineer", "field engineer", "deputation", "secondment",
                   "contract staff", "hiring of engineers", "hiring of technical", "hiring of it",
                   "provision of engineers", "technical resources",
                   "certified engineers", "ccie", "ccnp", "hcip", "accelerec", "talent"]},
    {"id": "pm_consult",  "group": "Managed", "name": "Project Management & IT Consulting", "weight": 0.8,
     "keywords": ["project management", "program management", "pmo", "pmp", "prince2", "consulting",
                   "consultancy", "advisory", "it consultant", "technical consultant", "roadmap",
                   "it strategy", "digital transformation", "feasibility", "survey planning design",
                   "network design", "solution design", "architecture", "it audit", "assessment"]},
]

# ── Industry verticals NETS serves (boosts score when tender issuer matches) ──
NETS_VERTICALS = {
    "telecom": ["telecom", "telco", "ptcl", "zong", "jazz", "ufone", "telenor", "ntc", "national telecom",
                 "pta", "frequency allocation", "mobile operator", "isp", "internet service"],
    "banking": ["bank", "banking", "financial", "insurance", "takaful", "sbp", "state bank", "hbl", "ubl",
                 "nbp", "national bank", "bop", "bank of punjab", "mcb", "meezan", "credit union", "fintech"],
    "public_sector": ["ministry", "government", "govt", "federal", "provincial", "directorate", "department of",
                       "authority", "commission", "secretariat", "municipal", "nadra", "fbr", "customs"],
    "education_health": ["university", "college", "school", "hospital", "healthcare", "medical", "nust",
                          "lums", "aku", "shifa", "pims", "education"],
    "enterprise": ["corporation", "limited", "pvt", "private limited", "plc", "group", "industries", "mills"],
}

# ── Words that look like NETS keywords but are false positives in procurement context ──
NEGATIVE_KEYWORDS = [
    "security guard", "security guards", "guarding services", "watchman", "sewerage", "drainage",
    "civil works", "building construction", "road", "bitumen", "asphalt", "cement", "bricks",
    "furniture", "stationery", "printing of", "catering", "vehicle", "bus", "truck", "ambulance",
    "medicine", "pharmaceutical", "surgical", "laboratory reagent", "uniform", "janitorial",
    "cleaning services", "gardening", "lpg", "diesel", "petrol", "tyre", "tire",
    "invertor ac", "inverter ac", "split ac", "air conditioner", "hvac compressor",
    "human resource consulting", "executive search", "head hunting", "recruitment agency",
    "legal services", "law firm", "auditor", "chartered accountant", "advertising agency",
    "event management", "travel agency", "insurance services",
]

# Short keywords (3 chars or fewer) need word-boundary matching to avoid false positives.
SHORT_KEYWORD_THRESHOLD = 3

# ── NETS OEM Partnership Levels ──
NETS_OEM_LEVELS = {
    "cisco": "Gold Partner",
    "huawei": "Silver Partner",
    "dell": "Gold Partner",
    "fortinet": "Advanced Partner",
}

# Maximum annual turnover NETS can meet (PKR)
NETS_MAX_TURNOVER_PKR = 2_000_000_000  # 2 billion


def _has_negative_signal(text_lower: str) -> Optional[str]:
    """Return the first negative keyword found, or None. Negative keywords mark non-ICT tenders.
    Always word-boundary matched so 'cement' does not fire inside 'CyberSense'."""
    for neg in NEGATIVE_KEYWORDS:
        if re.search(r'\b' + re.escape(neg) + r'\b', text_lower):
            return neg
    return None


def _detect_vertical(text_lower: str) -> Optional[str]:
    """Detect which NETS industry vertical the tender issuer belongs to."""
    for vertical, words in NETS_VERTICALS.items():
        for w in words:
            if len(w) <= SHORT_KEYWORD_THRESHOLD:
                if re.search(r'\b' + re.escape(w) + r'\b', text_lower):
                    return vertical
            elif w in text_lower:
                return vertical
    return None


def _match_keywords(text_lower: str) -> Tuple[List[Dict], List[str], float]:
    """
    Phase 1: match tender text against NETS solution keywords.
    Returns (matched_solutions, matched_keywords, weighted_match_score).
    weighted_match_score = sum of solution weights (so 2 core matches = 2.0, 1 core + 1 weak = 1.4).
    """
    matched_solutions = []
    matched_keywords = []
    seen_solution_ids = set()
    weighted = 0.0

    for sol in SOLUTIONS:
        hit = False
        for kw in sol["keywords"]:
            # Word-boundary match for short tokens and for tokens that are plain words
            # (avoids "ran" inside "transport", "sla" inside "islamabad", "l1" inside "l10")
            use_boundary = len(kw) <= SHORT_KEYWORD_THRESHOLD or re.fullmatch(r'[a-z0-9]+', kw) is not None
            if use_boundary:
                pattern = r'\b' + re.escape(kw) + r'\b'
                found = re.search(pattern, text_lower) is not None
            else:
                found = kw in text_lower
            if found:
                hit = True
                if kw not in matched_keywords:
                    matched_keywords.append(kw)
        if hit and sol["id"] not in seen_solution_ids:
            matched_solutions.append({
                "id": sol["id"],
                "name": sol["name"],
                "group": sol["group"],
                "weight": sol.get("weight", 1.0),
            })
            seen_solution_ids.add(sol["id"])
            weighted += sol.get("weight", 1.0)

    return matched_solutions, matched_keywords, weighted


def _evaluate_gates(title_lower: str, rfp_text: Optional[str] = None) -> Dict:
    """
    Phase 2: Hard qualification gates.
    When rfp_text is None (title-only scan), gates default to ASSUMED_PASS
    except turnover which can sometimes be detected from the title.
    When rfp_text is provided, gates are fully evaluated.
    """
    text = rfp_text.lower() if rfp_text else title_lower

    gates = {
        "turnover_under_2b": {"pass": True, "status": "PASS", "detail": "No turnover requirement detected"},
        "oem_partnership_matched": {"pass": True, "status": "ASSUMED_PASS", "detail": "No specific OEM level requirement detected"},
        "domain_expertise_matched": {"pass": True, "status": "PASS", "detail": "Matched via keyword scoring"},
        "organizational_history_met": {"pass": True, "status": "ASSUMED_PASS", "detail": "Standard 3-5 year ICT experience assumed met"},
        "qualified_resources_met": {"pass": True, "status": "ASSUMED_PASS", "detail": "OEM certified engineers assumed available"},
    }

    # ── Gate 1: Turnover check ──
    # Look for patterns like "turnover of PKR X billion", "annual turnover Rs. X"
    turnover_patterns = [
        r'(?:turnover|revenue|annual\s+turnover)[^\d]*(\d[\d,.]+)\s*(?:billion|b\b)',
        r'(?:turnover|revenue)[^\d]*(?:pkr|rs\.?|rupees?)\s*(\d[\d,.]+)\s*(?:billion|b\b)',
        r'(?:pkr|rs\.?)\s*(\d[\d,.]+)\s*(?:billion|b)\s*(?:turnover|revenue)',
        r'(\d[\d,.]+)\s*(?:billion|b)\s*(?:pkr|rs\.?)?\s*(?:turnover|revenue)',
    ]
    for pat in turnover_patterns:
        m = re.search(pat, text)
        if m:
            try:
                val_str = m.group(1).replace(",", "")
                val = float(val_str) * 1_000_000_000  # Convert billions
                if val > NETS_MAX_TURNOVER_PKR:
                    gates["turnover_under_2b"] = {
                        "pass": False,
                        "status": "FAIL",
                        "detail": f"Requires PKR {val/1e9:.1f}B turnover; NETS limit is PKR 2B"
                    }
                else:
                    gates["turnover_under_2b"]["detail"] = f"Requires PKR {val/1e9:.1f}B; within NETS range"
            except ValueError:
                pass
            break

    # ── Gate 2: OEM partnership level ──
    oem_issues = []
    for oem, nets_level in NETS_OEM_LEVELS.items():
        if oem in text:
            # Check if specific partner level is mentioned that exceeds ours
            platinum_check = re.search(
                rf'{oem}[^.]*(?:platinum|titanium|premier)\s*(?:partner|certified|level)',
                text
            )
            if platinum_check:
                oem_issues.append(f"{oem.title()} requires Platinum/Premier (NETS has {nets_level})")

    if oem_issues:
        gates["oem_partnership_matched"] = {
            "pass": False,
            "status": "FAIL",
            "detail": "; ".join(oem_issues)
        }
    elif any(oem in text for oem in NETS_OEM_LEVELS):
        gates["oem_partnership_matched"]["status"] = "PASS"
        gates["oem_partnership_matched"]["detail"] = "OEM requirements within NETS partnership levels"

    # ── Gate 3: Domain expertise (already covered by keyword matching) ──
    # This gate passes if Phase 1 found any solution match; caller sets it.

    # ── Gate 4: Organizational history ──
    exp_patterns = [
        r'(\d+)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|track record|history)',
        r'(?:experience|track record)\s*(?:of\s+)?(\d+)\s*(?:years?|yrs?)',
        r'(?:minimum|at least|not less than)\s*(\d+)\s*(?:years?|yrs?)',
    ]
    for pat in exp_patterns:
        m = re.search(pat, text)
        if m:
            years = int(m.group(1))
            if years > 10:
                gates["organizational_history_met"] = {
                    "pass": False,
                    "status": "FAIL",
                    "detail": f"Requires {years} years experience; may exceed NETS track record"
                }
            else:
                gates["organizational_history_met"] = {
                    "pass": True,
                    "status": "PASS",
                    "detail": f"Requires {years} years; NETS has 10+ years ICT experience"
                }
            break

    # ── Gate 5: Qualified resources ──
    if rfp_text:
        cert_patterns = [
            r'(?:ccie|ccnp|ccna|hcip|hcia|nse\s*[4-8]|vcp|vcap)',
            r'(?:certified\s+engineer|oem\s+certified|manufacturer\s+certified)',
        ]
        for pat in cert_patterns:
            if re.search(pat, text):
                gates["qualified_resources_met"] = {
                    "pass": True,
                    "status": "PASS",
                    "detail": "OEM certification requirements detected; NETS has certified engineers on staff"
                }
                break

    return gates


def score_tender(title: str, rfp_text: Optional[str] = None) -> Tuple[int, str, List[Dict], List[str], Dict]:
    """
    Score and qualify a tender.

    Args:
        title: Tender title text.
        rfp_text: Optional full RFP document text for deep gate evaluation.

    Returns:
        (score, verdict, matched_solutions, matched_keywords, qualification)

    qualification dict:
        gates: {gate_name: {pass, status, detail}}
        overall_verdict: "GO" / "NOGO" / "REVIEW"
        disqualification_reason: str or None
    """
    title_lower = title.lower()
    search_text = (title + " " + (rfp_text or "")).lower()
    scan_text = search_text if rfp_text else title_lower

    # Phase 0: negative keyword gate (non-ICT tenders that happen to contain NETS words)
    negative_hit = _has_negative_signal(title_lower)

    # Phase 1: weighted keyword matching
    matched_solutions, matched_keywords, weighted = _match_keywords(scan_text)
    vertical = _detect_vertical(scan_text)

    # Phase 1 scoring (weighted):
    #   weighted >= 2.0  -> 95  (two or more core NETS domains)
    #   weighted >= 1.0  -> 80  (one core domain)
    #   weighted >= 0.7  -> 70  (one adjacent domain)
    #   weighted >  0    -> 50  (weak signal only, REVIEW)
    #   0                -> 0
    # Vertical match (bank, telco, ministry) adds +5 up to 100.
    # Negative keyword with only weak/adjacent match caps score at 40 (SKIP).
    match_count = len(matched_solutions)
    if weighted >= 2.0:
        score = 95
    elif weighted >= 1.0:
        score = 80
    elif weighted >= 0.7:
        score = 70
    elif weighted > 0:
        score = 50
    else:
        score = 0

    if vertical and score > 0:
        score = min(100, score + 5)

    if negative_hit and weighted < 2.0:
        # e.g. "Security Guarding Services" matched "security" but is not ICT
        score = min(score, 40)

    # Phase 2: qualification gates
    gates = _evaluate_gates(title_lower, rfp_text)

    # Domain gate depends on Phase 1 result
    if match_count == 0:
        gates["domain_expertise_matched"] = {
            "pass": False,
            "status": "FAIL",
            "detail": "No NETS solution domain matched in tender text"
        }

    # Overall qualification verdict
    hard_fails = [g for g, v in gates.items() if not v["pass"]]
    assumed = [g for g, v in gates.items() if v["status"] == "ASSUMED_PASS"]

    if hard_fails:
        if "turnover_under_2b" in hard_fails:
            overall = "NOGO"
            dq_reason = gates["turnover_under_2b"]["detail"]
        elif "domain_expertise_matched" in hard_fails:
            overall = "NOGO"
            dq_reason = "No NETS solution domain match"
        else:
            overall = "NOGO"
            dq_reason = "; ".join(gates[g]["detail"] for g in hard_fails)
    elif assumed:
        overall = "REVIEW"
        dq_reason = None
    else:
        overall = "GO"
        dq_reason = None

    # Final verdict combines score and qualification
    if score >= 70 and overall == "GO":
        verdict = "BID"
    elif score >= 70 and overall == "REVIEW":
        verdict = "REVIEW"
    elif score >= 70 and overall == "NOGO":
        verdict = "NOGO"
        score = max(score, 75)  # Keep score for reporting but mark NOGO
    elif score >= 40:
        verdict = "REVIEW"
    else:
        verdict = "SKIP"

    if negative_hit and score <= 40:
        overall = "NOGO"
        dq_reason = f"Non-ICT tender (matched '{negative_hit}'); outside NETS scope"
        verdict = "SKIP"

    qualification = {
        "gates": gates,
        "overall_verdict": overall,
        "disqualification_reason": dq_reason,
        "vertical": vertical,
        "weighted_match": round(weighted, 2),
        "negative_signal": negative_hit,
    }

    return score, verdict, matched_solutions, matched_keywords, qualification


def score_tender_legacy(title: str) -> Tuple[int, str, List[Dict], List[str]]:
    """
    Backward-compatible 4-return scorer for code that has not been updated yet.
    Drops the qualification dict.
    """
    score, verdict, solutions, keywords, _ = score_tender(title)
    return score, verdict, solutions, keywords


def get_solutions_list() -> List[Dict]:
    """Return the full NETS solution taxonomy for the frontend."""
    return [{"id": s["id"], "name": s["name"], "group": s["group"]} for s in SOLUTIONS]
