"""
Agent 5: Regulatory, PPRA & AI Governance Auditor.
Runs AFTER Agent 4 passes. A proposal must clear both technical (Agent 4)
and regulatory (Agent 5) before final approval.

Pipeline flow:
  Agent 3 (Writer) -> Agent 4 (Technical QA) -> Agent 5 (Regulatory QA)
      ^                    |                          |
      |                    | fail: back to 3          | fail: back to 3
      +--------------------+--------------------------+

Pydantic V2 schema, plugs into the existing LangGraph StateGraph.
"""
import os
import json
import logging
from typing import List, TypedDict, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("agent5")


# ── Pydantic V2 Schema ──

class RegulatoryAuditResult(BaseModel):
    regulatory_score: int = Field(..., ge=0, le=100,
        description="Score evaluating adherence to PPRA, SECP, and AI governance.")
    passed_regulatory_audit: bool = Field(...,
        description="True if score >= 90 and zero legal red flags.")
    ppra_compliance_status: str = Field(...,
        description="Evaluation of alignment with Federal/Provincial PPRA transparency rules.")
    data_sovereignty_verified: bool = Field(...,
        description="True if local data residency and privacy controls are explicitly guaranteed.")
    legal_red_flags: List[str] = Field(default_factory=list,
        description="List of clauses that violate procurement laws, SECP, or anti-corruption frameworks.")
    remediation_directives: str = Field(...,
        description="Exact legal and structural rewrites required from Agent 3.")


# ── Extended Pipeline State (adds regulatory fields to existing state) ──

class ProposalPipelineState(TypedDict):
    rfp_id: str
    rfp_text: str
    rag_context: str
    draft_text: str
    audit_feedback: Optional[str]
    audit_result: Optional[dict]           # Agent 4 technical audit
    regulatory_audit_result: Optional[dict] # Agent 5 regulatory audit
    retry_count: int
    regulatory_retry_count: int
    status: str


# ── Agent 5 Node (production: calls Claude API) ──

SYSTEM_PROMPT = (
    "You are Agent 5, a senior Legal, Regulatory & AI Governance Counsel specializing in Pakistani "
    "public procurement law (Federal PPRA 2004, Provincial PPRAs), SECP corporate compliance (Companies Act 2017), "
    "NAB/FIA anti-corruption standards, and enterprise AI data sovereignty. "
    "Audit the proposal draft rigorously. You MUST respond ONLY with valid JSON matching the requested schema."
)

USER_PROMPT_TEMPLATE = """
--- TENDER CONTEXT & JURISDICTION ---
Target: Pakistan Public Sector / SOE Procurement (PPRA & SECP Regulated)
RFP ID: {rfp_id}

--- PROPOSAL DRAFT TO AUDIT ---
{draft_text}

TASK:
Audit the draft against:
1. PPRA Transparency & Fair Competition Rules (no sole-source language, open competition, clear evaluation criteria).
2. Data Sovereignty & AI Governance (local hosting, explainability, audit logs, no offshore data transfer).
3. SECP & Anti-Corruption safeguarding (clear liability, no ambiguous preferential clauses, no conflict of interest).
4. SBP regulations for banking sector procurement (if applicable).

Return a JSON object matching this exact schema:
{{
  "regulatory_score": <int 0-100>,
  "passed_regulatory_audit": <boolean, true if score >= 90 and no red flags>,
  "ppra_compliance_status": "<string summary>",
  "data_sovereignty_verified": <boolean>,
  "legal_red_flags": [<list of strings or empty>],
  "remediation_directives": "<string with precise legal and structural rewrite instructions>"
}}
"""


def agent_5_regulatory_node(state: ProposalPipelineState) -> ProposalPipelineState:
    """
    Agent 5: Regulatory audit node for LangGraph.
    Calls Claude API in production; uses simulated response for testing.
    """
    attempt = state.get("regulatory_retry_count", 0)
    logger.info(f"[Agent 5] Regulatory audit attempt {attempt + 1} for {state['rfp_id']}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        # ── PRODUCTION: call Claude API ──
        result = _call_claude_api(api_key, state)
    else:
        # ── TESTING: simulated response ──
        logger.info("[Agent 5] No API key found, using simulated response")
        result = _simulated_response(attempt)

    try:
        validated = RegulatoryAuditResult(**result)
        state["regulatory_audit_result"] = validated.model_dump()

        if validated.passed_regulatory_audit:
            state["status"] = "FULLY_APPROVED"
            state["audit_feedback"] = None
            logger.info(f"[Agent 5] PASSED: {validated.regulatory_score}/100, no red flags")
        else:
            state["status"] = "REGULATORY_REVISION_REQUIRED"
            state["audit_feedback"] = validated.remediation_directives
            logger.info(
                f"[Agent 5] FAILED: {validated.regulatory_score}/100, "
                f"{len(validated.legal_red_flags)} red flags"
            )

    except Exception as e:
        logger.error(f"[Agent 5] Validation error: {e}")
        state["regulatory_audit_result"] = {"error": str(e), "passed_regulatory_audit": False}
        state["audit_feedback"] = "Ensure full alignment with PPRA transparency and local AI data residency rules."
        state["status"] = "REGULATORY_REVISION_REQUIRED"

    state["regulatory_retry_count"] = attempt + 1
    return state


def _call_claude_api(api_key: str, state: dict) -> dict:
    """Call the Claude API for regulatory audit."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        rfp_id=state.get("rfp_id", "UNKNOWN"),
        draft_text=state.get("draft_text", "")
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )

    return json.loads(response.content[0].text)


# ── Simulated responses for testing without API key ──

SIMULATED_AUDITS = [
    # Attempt 1: missing data sovereignty, PPRA concerns
    {
        "regulatory_score": 62,
        "passed_regulatory_audit": False,
        "ppra_compliance_status": "Partial compliance. Proposal lacks explicit reference to PPRA Rule 12 (open competitive bidding). Evaluation criteria section does not meet PPRA transparency requirements for weighted scoring disclosure.",
        "data_sovereignty_verified": False,
        "legal_red_flags": [
            "CRITICAL: No explicit guarantee of data residency within Pakistan borders",
            "MAJOR: Proposal language ('preferred partner') could be interpreted as sole-source justification, violating PPRA Rule 4(1)",
            "MAJOR: No mention of SECP Companies Act 2017 compliance for corporate governance",
            "MINOR: Liability limitation clause is ambiguous and could conflict with NAB oversight requirements"
        ],
        "remediation_directives": (
            "Agent 3 must: (1) Add explicit data sovereignty clause guaranteeing all data remains within Pakistan, "
            "hosted in NETS Karachi/Islamabad data centres; (2) Remove any 'preferred partner' language and replace with "
            "open-competition PPRA-compliant language; (3) Add SECP Companies Act 2017 corporate governance section; "
            "(4) Clarify liability and indemnity clauses to satisfy NAB/FIA anti-corruption requirements; "
            "(5) Include PPRA Rule 12 compliant evaluation methodology."
        )
    },
    # Attempt 2: improved but data sovereignty still weak
    {
        "regulatory_score": 81,
        "passed_regulatory_audit": False,
        "ppra_compliance_status": "Substantially compliant. PPRA Rule 12 open bidding language present. Evaluation criteria now include weighted scoring. Minor gap: no reference to Provincial Sindh PPRA variations.",
        "data_sovereignty_verified": False,
        "legal_red_flags": [
            "MAJOR: Data sovereignty clause mentions 'primary hosting in Pakistan' but does not exclude offshore backup or DR replication",
            "MINOR: No explicit reference to Sindh Provincial PPRA (distinct from Federal PPRA)"
        ],
        "remediation_directives": (
            "Agent 3 must: (1) Strengthen data sovereignty to state 'all data, including backups and disaster recovery, "
            "shall reside exclusively within Pakistan' with no offshore exceptions; "
            "(2) Add reference to Sindh Provincial PPRA Rules alongside Federal PPRA 2004."
        )
    },
    # Attempt 3: fully compliant
    {
        "regulatory_score": 96,
        "passed_regulatory_audit": True,
        "ppra_compliance_status": "Fully compliant with Federal PPRA 2004, Sindh Provincial PPRA Rules, and SECP Companies Act 2017. Evaluation methodology is transparent with published weighted criteria. Open competitive bidding language used throughout.",
        "data_sovereignty_verified": True,
        "legal_red_flags": [],
        "remediation_directives": "No remediation required. Proposal meets all regulatory, legal, and AI governance requirements for Pakistan public sector procurement."
    }
]


def _simulated_response(attempt: int) -> dict:
    """Return simulated audit for testing."""
    return SIMULATED_AUDITS[min(attempt, len(SIMULATED_AUDITS) - 1)]


# ── LangGraph routing logic ──

def should_continue_after_regulatory(state: ProposalPipelineState) -> str:
    """
    Routing after Agent 5:
      FULLY_APPROVED -> end (proposal is ready)
      REGULATORY_REVISION_REQUIRED + retries left -> back to Agent 3
      Max retries exceeded -> escalate to human
    """
    MAX_REGULATORY_RETRIES = 3

    if state["status"] == "FULLY_APPROVED":
        return "approved"

    if state.get("regulatory_retry_count", 0) >= MAX_REGULATORY_RETRIES:
        state["status"] = "ESCALATED_TO_HUMAN_REGULATORY"
        return "max_retries_exceeded"

    return "retry_rewrite"
