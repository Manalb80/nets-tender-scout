# NETS RFP Discovery Criteria Checklist

Source documents: NETS Corporate Profile (Sep 2025) and NETS Cybersecurity Services Portfolio (30 Sep 2025).
This checklist is the single reference Agent 1 uses to decide whether a public tender is relevant to NETS International. It is also the human review sheet a presales architect can tick through when a tender is borderline.

How the scorer uses it: every solution category has a weight. Two or more core categories matched = score 95. One core category = 80. One adjacent category = 70. A weak signal only = 50 (sent to REVIEW). Matching a NETS industry vertical adds 5. A negative keyword with fewer than two core matches caps the score at 40 (SKIP).

---

## Part A: NETS Company Facts (used by qualification gates)

| Fact | Value | Where it matters |
|---|---|---|
| Established | 1983 (National Engineers), 42+ years | Organisational experience gate |
| Certified resources | 1,000+ | Qualified technical resources gate |
| Projects delivered | 3,000 to 4,000+ | Past performance references |
| Countries | 25 to 26+ | Geographic eligibility |
| Global offices | 9 (PAK, UAE, KSA, UK, USA, Canada, Germany, Greece, Azerbaijan) | Local presence requirement |
| Customers | 250+ | Reference letters |
| Pakistan presence | Since 1983 (HQ Karachi) | National bidder eligibility |
| SOC/NOC centres | UAE, KSA, PAK (24/7) | Managed services bids |
| Standards | ISO 9001, ISO 14001, ISO 20000-1, ISO 27001, ISO 45001, SOC 2 (AICPA), ISO 27701 (MonetX), GDPR | Compliance gate |
| Awards | Cisco Emerging Partner of the Year 2024, Cisco Impact Partner of the Year 2024, Great Place to Work 2025, SCTE Sustainability (runner up) 2025 | Differentiator section |

## Part B: OEM Partnerships (used by OEM partnership gate)

Tier 1 partners (NETS can meet Gold or equivalent requirements):
Cisco (Gold), Dell (Gold), Huawei (Silver or above), Fortinet (Advanced), HPE, H3C, Sangfor, AWS, Microsoft, IBM

Tier 2 partners (NETS resells and implements; check tier if RFP demands a specific level):
Juniper, Extreme Networks, Cambium Networks, D-Link, Lenovo, 3M, Vivanco, Hikvision, Kaspersky, CrowdStrike, Trend Micro, Symantec, Mimecast, Forcepoint, Sophos, Pligence, Cyber Silo, Extravis

Cybersecurity specialist tooling (NETS has deployed or certified on):
IBM QRadar, Rapid7 InsightIDR / InsightVM / Metasploit / InsightAppSec, Splunk, Microsoft Sentinel, BeyondTrust, Kron, Cisco ISE / Duo / Umbrella / AnyConnect / Secure Network Analytics, IBM Guardium, IBM MaaS360, GetVisibility, Ivanti, bitTruster, PhishRod, Nessus, Qualys, Acunetix, Burp Suite, SonarQube, Titania Nipper, AttackIQ, Ridge Security, Netwrix, Skurio

Rule: if the RFP demands Cisco Platinum / Premier, Dell Platinum, Huawei Gold, or Fortinet Expert, flag OEM gap. Anything at or below the Tier 1 levels above passes.

---

## Part C: Solution Keyword Checklist

Tick every row where the tender title, scope, or BOQ contains at least one keyword. Two or more ticks in core rows means the tender is NETS relevant.

### C1. Infrastructure Solutions

| # | Category | Weight | Keywords to look for |
|---|---|---|---|
| 1 | FTTX / Fibre Access Network | Core | ftth, fttx, fttp, gpon, xgs-pon, fibre optic, fiber optic, optical fibre, OFC, splicing, duct, excavation, home install, premises survey, RFS, last mile, access network, broadband rollout |
| 2 | Wireless Access and Mobile Sites | Core | mobile site, cell site, BTS, tower, microwave, LOS survey, IBS, in-building solution, DAS, small cell, rollout site, 4G, 5G, LTE, RAN, telecom site, site survey |
| 3 | ELV Systems | Core | ELV, extra low voltage, CCTV, access control, public address, PA system, BMS, fire alarm, intrusion detection, intercom, AV system, smart building, structured cabling, SCS, cat6, cat6a, cat7, patch panel |
| 4 | EV Charging | Core | EV charger, EV charging, electric vehicle charging, charging station, EVSE, DC fast charger |
| 5 | DC Power Systems | Core (0.9) | DC power, rectifier, -48V, telecom power, battery bank, UPS system, uninterruptible power, site power |
| 6 | Data Centre Infrastructure | Core | data centre, data center, rack, racking, shelving, cooling, precision cooling, raised floor, containment, DC commissioning, Tier III, Tier IV, colocation, PDU |
| 7 | Servers and Compute | Core | server, blade, compute, hyperconverged, HCI, VMware, virtualisation, hypervisor, rack mount server, PowerEdge, ProLiant |
| 8 | Storage and Backup | Core | storage, SAN, NAS, backup, data protection, Dell EMC, Veeam, Commvault, tape library, object storage, disaster recovery, DR site, business continuity, BCP, replication |
| 9 | Enterprise Networking (LAN / WAN / SD-WAN / ACI) | Core | network, switch, router, Cisco, Juniper, Aruba, H3C, Huawei, Extreme, LAN, WAN, SD-WAN, SD-LAN, ACI, MPLS, MPLS-TP, core network, campus network, WiFi, WLAN, access point, WLC, Cambium, Nexus, Catalyst, Meraki |
| 10 | Unified Communications | Core (0.9) | IP phone, IP-PBX, VoIP, unified communication, video conferencing, IP telephony, CUCM, Webex, contact centre, telephony |

### C2. Digital Solutions

| # | Category | Weight | Keywords to look for |
|---|---|---|---|
| 11 | Cloud and Hybrid IT | Core | cloud, Azure, AWS, hybrid cloud, private cloud, IaaS, PaaS, SaaS, cloud migration, Kubernetes, container, OpenStack, telco cloud |
| 12 | Network Security (NGFW / VPN / NAC) | Core | firewall, NGFW, Fortinet, FortiGate, Palo Alto, Checkpoint, Sophos, VPN, NAC, Cisco ISE, AnyConnect, WAF, IDS, IPS, IDPS, DDoS, proxy, web security, email security, Mimecast, Umbrella, DNS security |
| 13 | SOC / SIEM / SOAR / Monitoring | Core | SOC, security operations centre, SIEM, SOAR, QRadar, Splunk, Sentinel, InsightIDR, 24x7 monitoring, threat intelligence, threat hunting, managed SOC, SOC as a service, MDR, log management, incident response, DFIR, digital forensics, MITRE ATT&CK, playbook |
| 14 | Endpoint and Threat Protection (EPP / EDR / XDR) | Core | endpoint, EPP, EDR, XDR, NDR, antivirus, antimalware, Kaspersky, CrowdStrike, Trend Micro, Symantec, ransomware, phishing, patch management, virtual patching, Ivanti, NBAD |
| 15 | Identity and Access (IAM / PAM / MFA) | Core | IAM, identity management, PAM, privileged access, BeyondTrust, Kron, MFA, multi-factor, 2FA, SSO, single sign-on, zero trust, ZTNA, Duo, MDM, MaaS360, file integrity, FIM, remote workforce |
| 16 | Data and Cloud Security (DLP / Encryption / DAM) | Core | DLP, data loss prevention, encryption, database security, DAM, Guardium, Forcepoint, data classification, data discovery, GetVisibility, cloud security, CASB, data privacy, GDPR, PCI DSS |
| 17 | VAPT / Vulnerability Management | Core | VAPT, vulnerability assessment, penetration testing, pentest, red team, Nessus, Qualys, Rapid7, InsightVM, Acunetix, Burp, Metasploit, SAST, DAST, application security, source code review, black box, grey box, white box, security assessment, breach and attack, AttackIQ, Nipper, configuration audit |
| 18 | GRC / vCISO / Security Consulting | Core | GRC, governance risk compliance, vCISO, CISO on demand, posture assessment, security consulting, ISMS, ISO 27001, NIST, NIST 800-53, SOC 2, security policy, security audit, gap analysis, maturity assessment, security awareness, awareness training, DevSecOps, secure SDLC |
| 19 | Automation, AI/ML and DevOps | Core (0.9) | artificial intelligence, machine learning, AI/ML, RPA, automation, hyper-automation, chatbot, NLP, DevOps, CI/CD, microservice, Python, Ansible, zero touch, ZTP, orchestration, analytics, dashboard, observability, MonetX, predictive analytics, anomaly detection, root cause |
| 20 | NMS / Observability / ITSM | Core | NMS, network management system, network monitoring, infrastructure monitoring, unified observability, ITSM, ServiceNow, ticketing, CMDB, asset management, inventory management, IPAM, NCM, configuration management, NetFlow, APM, SupportX, GreenX, MapX, sustainability, carbon, CO2 |

### C3. Managed Solutions

| # | Category | Weight | Keywords to look for |
|---|---|---|---|
| 21 | Managed O&M / AMC / Break-Fix | Core | managed service, O&M, operation and maintenance, AMC, annual maintenance, maintenance contract, support contract, break-fix, TAC support, OEM support, RMA, CM/PM, preventive maintenance, corrective maintenance, warranty, SmartNet, SLA |
| 22 | NOC / Helpdesk / L1-L2 Support | Core | NOC, network operations centre, helpdesk, service desk, IT support, L1, L2, L1/L2, incident management, 24/7 support, 8/5, ITIL, IT operations, remote monitoring |
| 23 | Resource Outsourcing / Staff Augmentation | Core | outsourcing, resource augmentation, staff augmentation, manpower, skilled resources, resident engineer, field engineer, deputation, secondment, contract staff, hiring of engineers, hiring of technical, provision of engineers, certified engineers, CCIE, CCNP, HCIP, Accelerec |
| 24 | Project Management and IT Consulting | Adjacent (0.8) | project management, program management, PMO, PMP, PRINCE2, consulting, consultancy, advisory, IT consultant, roadmap, IT strategy, digital transformation, feasibility, survey planning design, network design, solution design, architecture, IT audit |

---

## Part D: Industry Vertical Boost (+5 to score)

| Vertical | Issuer keywords | NETS track record |
|---|---|---|
| Telecom and Technology | telecom, telco, PTCL, Zong, Jazz, Ufone, Telenor, NTC, PTA, mobile operator, ISP | 40+ years serving telcos, 25+ years FTTX and mobile deployments (du, e&, PTCL, STC, BT, Zong, Hyperoptic, brsk, FullFibre, GO Telecom) |
| Banking and Finance | bank, banking, financial, insurance, takaful, SBP, HBL, UBL, NBP, BOP, MCB, Meezan, fintech | 20+ leading banks, 11 insurance and credit unions (Riyad Bank, ANB, BOP, HBL, UBL, DIB, Salama, Takaful Emarat, NASCO, Oman Insurance) |
| Public Sector | ministry, government, federal, provincial, directorate, authority, commission, secretariat, municipal, NADRA, FBR, customs | 32 public sector entities, 17 ministries, 6 governments (Dubai Municipality, Dubai Taxi, DEWA, Ministry of Interior, Crawley Borough Council) |
| Education and Healthcare | university, college, school, hospital, healthcare, medical, NUST, LUMS, AKU, Shifa, PIMS | 20+ schools and colleges, 15 universities, 7 hospitals (University of Dubai, UAE University, CUCA, Shifa, Adam Vital, RAK Hospital, Beaconhouse) |
| Enterprise and Corporate | corporation, limited, pvt, plc, group, industries, mills | 250+ organisations, blue chip and Fortune 500 (Cisco, Deloitte, Emaar, Coca-Cola, Nestle, Del Monte, Air Arabia, Carrefour, KPMG) |

---

## Part E: Negative Keywords (cap score at 40 unless two core categories also match)

These words signal a tender that mentions ICT-sounding terms but is actually civil works, facilities, or non-technical procurement. NETS does not bid on these.

security guard, guarding services, watchman, sewerage, drainage, civil works, building construction, road, bitumen, asphalt, cement, bricks, furniture, stationery, printing of, catering, vehicle, bus, truck, ambulance, medicine, pharmaceutical, surgical, laboratory reagent, uniform, janitorial, cleaning services, gardening, LPG, diesel, petrol, tyre, invertor AC, inverter AC, split AC, air conditioner, HVAC compressor, human resource consulting, executive search, head hunting, recruitment agency, legal services, law firm, auditor, chartered accountant, advertising agency, event management, travel agency, insurance services

---

## Part F: Pre-Bid Qualification Gates (hard rules)

| Gate | Pass condition | Fail action |
|---|---|---|
| 1. Annual turnover | RFP minimum turnover is PKR 2 billion or less (or not stated) | NOGO |
| 2. OEM partnership level | Required tier is at or below Cisco Gold, Dell Gold, Huawei Silver, Fortinet Advanced | NOGO, unless Bid Director overrides |
| 3. Domain expertise | At least one core category from Part C matched | NOGO |
| 4. Organisational experience | Required years of experience is 10 or fewer (NETS has 42) | Flag REVIEW if above 10 |
| 5. Qualified technical resources | Required certifications are within CCIE, CCNP, CCNA, HCIP, HCIA, NSE 4-8, VCP, VCAP, PMP, CEH, CISSP, ISO 27001 LA | Flag REVIEW if unusual cert demanded |
| 6. Pre-bid compliance | OEM deal registration secured by KAM; National Engineers entity documents attached | Manual action required before bid submission |

---

## Part G: How to use this checklist manually

1. Read the tender title and first page of scope.
2. Tick rows in Part C. Count ticks in Core rows.
3. Check Part E. If a negative word appears and fewer than two Core rows are ticked, stop: not for NETS.
4. Check Part D. Note the vertical; it tells you which reference customers to cite.
5. Open the RFP PDF. Work through Part F gates one by one. Write the exact page and clause number where each requirement appears.
6. If all six gates pass or are marked REVIEW (not NOGO), the tender goes to the Bid Board as Qualified.
7. Record any manual override with the Bid Director's name and reason.
