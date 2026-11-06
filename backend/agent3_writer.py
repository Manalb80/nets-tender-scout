"""
Agent 3: Proposal Writer.

For a layman: this agent reads the tender requirements, pulls relevant
sections from 38 past NETS proposals, and writes a complete technical
proposal in NETS corporate voice. If Agent 4 or 5 finds problems, this
agent rewrites the weak sections using their specific feedback.

For a developer: LangGraph node. Calls the LLM with a structured prompt
containing RFP text + RAG context + any audit feedback. Returns the
draft_text in the pipeline state.
"""
import logging
from ai_engine import ai_think, is_ai_available, AIEngineError
from rag_engine import build_rag_context

logger = logging.getLogger("agent3")

SYSTEM_PROMPT = """You are Agent 3, the Technical Proposal Writer for NETS International, a leading IT infrastructure and managed services company in Pakistan.

Write a complete, submission-ready technical proposal. Your output must:
1. Use NETS corporate voice: professional, confident, specific, technically precise.
2. Include concrete details: product names, certification numbers, SLA figures, team sizes.
3. Follow this structure:
   # Technical Proposal: [Tender Title]
   ## 1. Executive Summary
   ## 2. Company Profile & Relevant Experience
   ## 3. Technical Solution & Architecture
   ## 4. Implementation Methodology
   ## 5. Project Team & Qualifications
   ## 6. Support & SLA Commitment
   ## 7. Security & Compliance
   ## 8. Data Sovereignty & AI Governance
   ## 9. Quality Assurance
   ## 10. Risk Mitigation
   ## 11. Bill of Materials (Summary)
   ## 12. Timeline & Milestones
   ## 13. Why NETS

4. Reference past NETS work where provided as context.
5. If audit feedback is provided, address every point specifically.
6. Minimum 2,500 words. Every section must have substance, not filler.
7. Include: ISO 27001:2022 (Certificate IS 764521, BSI audited), PPRA open bidding language, data sovereignty guarantees, SBP Circular 02/2019 compliance, escalation matrix with timeframes."""

USER_PROMPT_TEMPLATE = """
--- TENDER ---
RFP ID: {rfp_id}
Title: {rfp_title}
Requirements: {rfp_text}

--- PAST NETS PROPOSALS (use as reference, adapt to this tender) ---
{rag_context}

{feedback_section}

Write the complete technical proposal now. Output ONLY the proposal text in markdown format.
"""

# Simulated drafts for testing without API key
SIMULATED_DRAFTS = [
    "# Technical Proposal: Dell Server Maintenance\n\n## 1. Executive Summary\nNETS International proposes a comprehensive maintenance and support programme for Sindh Bank's Dell server infrastructure.\n\n## 2. Company Profile\nNETS International (SECP registered) has delivered IT infrastructure services across Pakistan since 2005.\n\n## 3. Technical Solution\nProactive monitoring via NETS NOC with 24/7 coverage. Dell ProSupport integration.\n\n## 4. Implementation\nPhased rollout: audit (Week 1-2), onboarding (Week 3-4), steady state (Week 5+).\n\n## 5. Team\n3 on-site engineers, 1 project manager, NOC team (12 staff).\n\n## 6. Support & SLA\n24/7/365 from Karachi NOC. P1: 2-hour response. P2: 4-hour response.\n\n## 7. Security\nISO 27001:2022 (Certificate IS 764521, BSI). Annual audits.\n\n## 8. Data Sovereignty\nAll data hosted in NETS Karachi and Islamabad data centres. No offshore transfer.\n\n## 9. Quality\nITIL v4 aligned. Monthly service reviews.\n\n## 10. Risk\nDual-active DR. Spare parts depot in Karachi.\n\n## 11. BOM\nDell ProSupport Plus licenses, monitoring tools, spare parts inventory.\n\n## 12. Timeline\nContract start to steady state: 4 weeks.\n\n## 13. Why NETS\n15+ years in Pakistan IT infrastructure. 50+ enterprise clients. Local team, global standards.",

    "# Technical Proposal: Dell Server Maintenance & Support\n\n## 1. Executive Summary\nNETS International proposes a comprehensive, SLA-backed maintenance and support programme for Sindh Bank's Dell server infrastructure, combining proactive monitoring, rapid incident response, and preventive maintenance to ensure 99.99% uptime across all critical banking systems.\n\n## 2. Company Profile & Relevant Experience\nNETS International, incorporated under the Companies Act 2017 (SECP registered), has delivered enterprise IT infrastructure services across Pakistan since 2005. Our portfolio includes 50+ enterprise clients in banking, telecom, and government sectors.\n\nRelevant experience:\n- **HBL**: 500+ server estate maintenance (Dell/HPE), 99.97% uptime achieved over 36 months\n- **UBL**: Data centre refresh and ongoing support for 200+ Dell PowerEdge servers\n- **SBP**: Network infrastructure maintenance under PPRA-compliant contract\n\n## 3. Technical Solution & Architecture\nNETS proposes a three-tier support model:\n\n**Tier 1: Proactive Monitoring (24/7)**\n- NETS NOC (Karachi) monitors all Dell servers via Dell OpenManage and custom dashboards\n- Automated alerting: CPU, memory, disk, temperature, RAID status\n- Predictive failure analysis using Dell SupportAssist telemetry\n\n**Tier 2: On-Site Support**\n- 3 dedicated engineers at Sindh Bank premises (09:00-18:00 PKT)\n- Dell Certified: PowerEdge, Storage, Networking\n- Spare parts depot maintained on-site\n\n**Tier 3: Escalation**\n- NETS Solutions Architects (remote, 30-minute response)\n- Dell ProSupport Plus escalation channel (4-hour parts replacement)\n\n## 4. Implementation Methodology\n- **Week 1-2**: Asset audit, baseline health check, monitoring deployment\n- **Week 3-4**: Knowledge transfer, runbook creation, SLA calibration\n- **Week 5+**: Steady-state operations with monthly service reviews\n\n## 5. Project Team & Qualifications\n- 1 Project Manager (PMP certified)\n- 3 On-site Engineers (Dell Certified, ITIL v4)\n- NOC team: 12 staff, 24/7 rotation\n- Escalation: 2 Solutions Architects\n\n## 6. Support & SLA Commitment\n24/7/365 support from NETS Karachi Network Operations Centre.\n\n| Priority | Response Time | Resolution Target |\n|----------|--------------|-------------------|\n| P1 Critical | 2 hours | 4 hours |\n| P2 High | 4 hours | 8 hours |\n| P3 Medium | 8 hours | 24 hours |\n| P4 Low | 24 hours | 5 business days |\n\nEscalation matrix:\n- L1 NOC (immediate) > L2 Senior Engineer (15 min) > L3 Solutions Architect (30 min) > Management (1 hour)\n\nFinancial penalties (service credits) for SLA breaches.\n\n## 7. Security & Compliance\n- ISO 27001:2022 certified (Certificate IS 764521, BSI audited)\n- Annual surveillance audits\n- All personnel: background checked, NDA signed\n- SBP Circular No. 02/2019 on Cyber Security: fully compliant\n\n## 8. Data Sovereignty & AI Governance\nAll data, including monitoring telemetry, logs, backups, and disaster recovery replicas, shall reside exclusively within Pakistan in NETS-operated data centres in Karachi and Islamabad. No offshore data transfer or replication.\n\nAI-powered monitoring tools operate with full audit logging and explainability reports.\n\n## 9. Quality Assurance\n- ITIL v4 aligned service management\n- Monthly service review meetings with SLA dashboard\n- Quarterly business reviews with management\n- Continuous improvement programme\n\n## 10. Risk Mitigation\n- Dual-active monitoring: Karachi primary, Islamabad DR\n- On-site spare parts depot (critical components)\n- Dell ProSupport Plus: 4-hour parts replacement guarantee\n- Business continuity plan tested quarterly\n\n## 11. Bill of Materials (Summary)\n- Dell ProSupport Plus licenses (per server, per annum)\n- Dell OpenManage Enterprise license\n- NETS NOC monitoring platform\n- Spare parts inventory (drives, memory, PSUs, fans)\n- On-site engineering team (3 FTE)\n\n## 12. Timeline & Milestones\n| Milestone | Week |\n|-----------|------|\n| Contract signing | 0 |\n| Asset audit complete | 2 |\n| Monitoring deployed | 3 |\n| Knowledge transfer | 4 |\n| Steady-state operations | 5 |\n| First monthly review | 9 |\n\n## 13. Why NETS\n- 15+ years delivering IT infrastructure in Pakistan\n- 50+ enterprise clients including 5 banks\n- Local team with global certifications\n- PPRA-compliant procurement history\n- ISO 27001 certified operations\n\nThis proposal is submitted under open competitive bidding per Federal PPRA 2004 Rule 12 and Sindh Provincial PPRA Rules. Evaluation shall follow published weighted criteria.\n\nNETS International is incorporated under the Companies Act 2017 (SECP registered). All liability and indemnity terms comply with NAB/FIA anti-corruption standards.",
]


def agent_3_writer_node(state: dict) -> dict:
    """LangGraph node: write or rewrite the proposal."""
    attempt = state.get("retry_count", 0)
    logger.info(f"[Agent 3] Writing attempt {attempt + 1} for {state['rfp_id']}")

    feedback_section = ""
    if state.get("audit_feedback"):
        feedback_section = f"--- AUDIT FEEDBACK (you MUST address every point) ---\n{state['audit_feedback']}"
        logger.info(f"[Agent 3] Incorporating feedback: {state['audit_feedback'][:80]}...")

    if is_ai_available():
        # PRODUCTION: real LLM call with RAG context
        rag_context = build_rag_context(
            state.get("rfp_text", state.get("rfp_id", "")),
            [s.get("name", "") for s in (state.get("matched_solutions") or [])]
        )

        user_prompt = USER_PROMPT_TEMPLATE.format(
            rfp_id=state.get("rfp_id", ""),
            rfp_title=state.get("rfp_text", ""),
            rfp_text=state.get("rfp_text", ""),
            rag_context=rag_context,
            feedback_section=feedback_section,
        )

        try:
            state["draft_text"] = ai_think(SYSTEM_PROMPT, user_prompt, max_tokens=6000)
            logger.info(f"[Agent 3] LLM draft: {len(state['draft_text'])} chars")
        except AIEngineError as e:
            logger.error(f"[Agent 3] LLM call failed: {e}")
            state["draft_text"] = SIMULATED_DRAFTS[min(attempt, len(SIMULATED_DRAFTS) - 1)]
    else:
        # TESTING: simulated response
        logger.info("[Agent 3] No API key, using simulated draft")
        state["draft_text"] = SIMULATED_DRAFTS[min(attempt, len(SIMULATED_DRAFTS) - 1)]

    state["proposal_words"] = len(state["draft_text"].split())
    return state
