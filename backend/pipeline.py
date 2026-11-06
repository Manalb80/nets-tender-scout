"""
NETS Presales: Full 5-Agent Production Pipeline.

Agent 3 (Writer) -> Agent 4 (Technical QA) -> Agent 5 (Regulatory QA) -> APPROVED

Each agent uses the AI Engine (ai_engine.py) to call Claude or GPT.
If no API key is set, agents fall back to simulated responses for testing.

Run:  python pipeline.py                    # test with simulations
      ANTHROPIC_API_KEY=sk-... python pipeline.py  # test with real LLM
"""
import os
import sys
import json
import logging
from typing import List, TypedDict, Optional
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from langgraph.graph import StateGraph, END
from ai_engine import is_ai_available, get_ai_status
from agent3_writer import agent_3_writer_node
from agent4_technical import agent_4_technical_node
from agent5_regulatory import agent_5_regulatory_node, should_continue_after_regulatory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("pipeline")


# ── Pipeline State ──

class PipelineState(TypedDict):
    rfp_id: str
    rfp_text: str
    rag_context: str
    draft_text: str
    proposal_words: int
    audit_feedback: Optional[str]
    audit_result: Optional[dict]
    verified_requirements: Optional[List[str]]
    missing_requirements: Optional[List[str]]
    regulatory_audit_result: Optional[dict]
    retry_count: int
    regulatory_retry_count: int
    matched_solutions: Optional[List[dict]]
    status: str


# ── Routing ──

def route_after_technical(state: PipelineState) -> str:
    MAX_RETRIES = 3
    if state["status"] == "TECH_PASSED":
        return "to_regulatory"
    if state["retry_count"] >= MAX_RETRIES:
        state["status"] = "ESCALATED_TO_HUMAN_TECHNICAL"
        return "max_retries_exceeded"
    return "retry_rewrite"


# ── Build Graph ──

def build_pipeline():
    wf = StateGraph(PipelineState)
    wf.add_node("agent_3_writer", agent_3_writer_node)
    wf.add_node("agent_4_technical", agent_4_technical_node)
    wf.add_node("agent_5_regulatory", agent_5_regulatory_node)
    wf.set_entry_point("agent_3_writer")
    wf.add_edge("agent_3_writer", "agent_4_technical")
    wf.add_conditional_edges("agent_4_technical", route_after_technical,
        {"to_regulatory": "agent_5_regulatory", "retry_rewrite": "agent_3_writer", "max_retries_exceeded": END})
    wf.add_conditional_edges("agent_5_regulatory", should_continue_after_regulatory,
        {"approved": END, "retry_rewrite": "agent_3_writer", "max_retries_exceeded": END})
    return wf.compile()


# ── Test Runner ──

if __name__ == "__main__":
    ai_status = get_ai_status()
    mode = "LIVE (LLM)" if ai_status["available"] else "SIMULATED (no API key)"

    print("=" * 70)
    print(f"NETS PRESALES: 5-Agent Pipeline [{mode}]")
    print(f"AI Provider: {ai_status.get('provider','none')}")
    print(f"Model: {ai_status.get('model','simulated')}")
    print("Agent 3 (Writer) -> Agent 4 (Technical) -> Agent 5 (Regulatory)")
    print("=" * 70)

    app = build_pipeline()

    initial: PipelineState = {
        "rfp_id": "SNDB/CO/IT/PRO/2026/042",
        "rfp_text": "Maintenance & Support of Dell Servers. Requirements: 99.99% uptime SLA, ISO27001, 24/7 local support with 2-hour P1 response, automated monitoring, PPRA compliant procurement.",
        "rag_context": "",
        "draft_text": "",
        "proposal_words": 0,
        "audit_feedback": None,
        "audit_result": None,
        "verified_requirements": None,
        "missing_requirements": None,
        "regulatory_audit_result": None,
        "retry_count": 0,
        "regulatory_retry_count": 0,
        "matched_solutions": [{"id": "dc", "name": "Data Centre", "group": "Infrastructure"},
                               {"id": "maintenance", "name": "Maintenance & Support", "group": "Managed IT"}],
        "status": "INITIALIZING",
    }

    final = app.invoke(initial)

    # ── Summary ──
    tech = final.get("audit_result", {})
    reg = final.get("regulatory_audit_result", {})

    print("\n" + "=" * 70)
    print("PIPELINE RESULT")
    print("=" * 70)
    print(f"Mode:                  {mode}")
    print(f"Final Status:          {final['status']}")
    print(f"Writer Iterations:     {final['retry_count']}")
    print(f"Regulatory Iterations: {final.get('regulatory_retry_count', 0)}")
    print(f"Proposal Words:        {final.get('proposal_words', 0)}")
    print(f"Technical Score:       {tech.get('compliance_score', 'N/A')}/100")
    print(f"Regulatory Score:      {reg.get('regulatory_score', 'N/A')}/100")
    print(f"Data Sovereignty:      {reg.get('data_sovereignty_verified', 'N/A')}")
    print(f"Red Flags:             {len(reg.get('legal_red_flags', []))}")

    # ── Validation ──
    print("\n" + "-" * 70)
    print("VALIDATION:")
    checks = [
        ("Pipeline completed without errors", final["status"] in ["FULLY_APPROVED", "ESCALATED_TO_HUMAN_TECHNICAL", "ESCALATED_TO_HUMAN_REGULATORY"]),
        ("Draft text is not empty", len(final.get("draft_text", "")) > 100),
        ("Technical audit produced a score", tech.get("compliance_score") is not None),
        ("At least 1 writer iteration ran", final["retry_count"] >= 1),
    ]

    if final["status"] == "FULLY_APPROVED":
        checks += [
            ("Technical score >= 85", tech.get("compliance_score", 0) >= 85),
            ("Regulatory score >= 90", reg.get("regulatory_score", 0) >= 90),
            ("Data sovereignty verified", reg.get("data_sovereignty_verified") is True),
            ("Zero legal red flags", len(reg.get("legal_red_flags", ["x"])) == 0),
        ]

    all_ok = True
    for name, ok in checks:
        print(f"  {chr(9989) if ok else chr(10060)} {name}")
        if not ok: all_ok = False

    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED." if all_ok else "SOME CHECKS FAILED.")
    print("=" * 70)

    # Save
    results = {
        "mode": mode,
        "final_status": final["status"],
        "writer_iterations": final["retry_count"],
        "regulatory_iterations": final.get("regulatory_retry_count", 0),
        "proposal_words": final.get("proposal_words", 0),
        "technical_score": tech.get("compliance_score"),
        "regulatory_score": reg.get("regulatory_score"),
        "data_sovereignty": reg.get("data_sovereignty_verified"),
        "red_flags": reg.get("legal_red_flags", []),
        "all_checks_passed": all_ok,
        "timestamp": datetime.utcnow().isoformat(),
    }
    outpath = os.path.join(os.path.dirname(__file__), "..", "scripts", "pipeline_results.json")
    with open(outpath, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults: {outpath}")
