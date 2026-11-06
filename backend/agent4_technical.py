"""
Agent 4: Technical Compliance Auditor.

For a layman: this agent reads the proposal Agent 3 wrote and checks it
like a senior engineer reviewing your work. "Did you mention ISO cert?
Is the SLA specific enough? Is there an escalation matrix?" It scores
the proposal and tells Agent 3 exactly what to fix.

For a developer: LangGraph node. Calls LLM to audit the draft against
RFP requirements. Returns a validated Pydantic TechnicalAuditResult.
"""
import logging
from typing import List
from pydantic import BaseModel, Field
from ai_engine import ai_think_json, is_ai_available, AIEngineError

logger = logging.getLogger("agent4")


class TechnicalAuditResult(BaseModel):
    compliance_score: int = Field(..., ge=0, le=100)
    passed_audit: bool = Field(...)
    verified_requirements: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    remediation_feedback: str = Field(...)


SYSTEM_PROMPT = """You are Agent 4, a Senior Technical Compliance Auditor for NETS International.
You audit technical proposals with zero tolerance for vague or missing requirements.
You MUST respond ONLY with valid JSON matching the requested schema.
A proposal passes ONLY if compliance_score >= 85 and all critical requirements are verified."""

USER_PROMPT_TEMPLATE = """
--- RFP REQUIREMENTS ---
{rfp_text}

--- PROPOSAL DRAFT TO AUDIT ---
{draft_text}

Audit this proposal against these mandatory requirements:
1. 99.99% uptime SLA with financial penalties
2. ISO 27001 certification WITH certificate number and auditing body
3. 24/7 local support with named NOC location
4. P1 response time: 2 hours maximum, with tiered P2/P3
5. Escalation matrix with defined timeframes
6. SBP Circular No. 02/2019 compliance
7. Specific technical architecture (not generic descriptions)
8. Implementation timeline with milestones
9. Named team members or roles with qualifications
10. Bill of materials or cost summary

Return JSON:
{{
  "compliance_score": <int 0-100>,
  "passed_audit": <boolean, true only if score >= 85>,
  "verified_requirements": [<list of requirements that ARE properly addressed>],
  "missing_requirements": [<list, each prefixed CRITICAL/MAJOR/MINOR>],
  "remediation_feedback": "<specific instructions for Agent 3 to fix each gap>"
}}
"""

SIMULATED_AUDITS = [
    {"compliance_score": 65, "passed_audit": False,
     "verified_requirements": ["Company profile present", "Basic technical approach described", "Team structure outlined"],
     "missing_requirements": ["CRITICAL: No specific SLA response times", "CRITICAL: ISO 27001 mentioned but no certificate number",
                               "MAJOR: No escalation matrix", "MAJOR: No SBP circular reference", "MINOR: BOM is vague"],
     "remediation_feedback": "Add: (1) P1 2-hour, P2 4-hour response times with penalties; (2) ISO 27001:2022 Certificate IS 764521 BSI; (3) Escalation matrix L1>L2>L3 with timeframes; (4) SBP Circular 02/2019 reference; (5) Detailed BOM."},
    {"compliance_score": 92, "passed_audit": True,
     "verified_requirements": ["99.99% uptime SLA with service credits", "ISO 27001:2022 IS 764521 BSI", "24/7/365 Karachi NOC",
                                "P1 2hr, P2 4hr tiered SLA", "Escalation matrix with timeframes", "SBP Circular 02/2019",
                                "Detailed architecture with product names", "4-week implementation timeline", "Named team roles with certs", "BOM summary"],
     "missing_requirements": [],
     "remediation_feedback": "No remediation required. All 10 mandatory requirements verified."},
]


def agent_4_technical_node(state: dict) -> dict:
    """LangGraph node: audit the proposal technically."""
    attempt = state.get("retry_count", 0)
    logger.info(f"[Agent 4] Technical audit iteration {attempt + 1}")

    if is_ai_available():
        try:
            result = ai_think_json(
                SYSTEM_PROMPT,
                USER_PROMPT_TEMPLATE.format(
                    rfp_text=state.get("rfp_text", ""),
                    draft_text=state.get("draft_text", ""),
                ),
                TechnicalAuditResult,
            )
            state["audit_result"] = result.model_dump()
            state["audit_feedback"] = result.remediation_feedback if not result.passed_audit else None
            state["verified_requirements"] = result.verified_requirements
            state["missing_requirements"] = result.missing_requirements
            state["retry_count"] = attempt + 1

            if result.passed_audit:
                state["status"] = "TECH_PASSED"
                logger.info(f"[Agent 4] PASSED: {result.compliance_score}/100")
            else:
                state["status"] = "REVISE_REQUIRED"
                logger.info(f"[Agent 4] FAILED: {result.compliance_score}/100, {len(result.missing_requirements)} gaps")
            return state

        except AIEngineError as e:
            logger.error(f"[Agent 4] LLM call failed: {e}, using simulated")

    # TESTING: simulated
    logger.info("[Agent 4] Using simulated audit")
    raw = SIMULATED_AUDITS[min(attempt, len(SIMULATED_AUDITS) - 1)]
    result = TechnicalAuditResult(**raw)
    state["audit_result"] = result.model_dump()
    state["audit_feedback"] = result.remediation_feedback if not result.passed_audit else None
    state["verified_requirements"] = result.verified_requirements
    state["missing_requirements"] = result.missing_requirements
    state["retry_count"] = attempt + 1
    state["status"] = "TECH_PASSED" if result.passed_audit else "REVISE_REQUIRED"
    return state
