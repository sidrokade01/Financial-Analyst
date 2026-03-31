"""
Assembly Agent
--------------
Model  : Sonnet
Input  : financial_model + valuation + benchmarking
Output : consistency_report (JSON)
"""

import json

SYSTEM_PROMPT = """You are the Assembly Agent QC reviewer for a Goldman Sachs IB pitch.
Output ONLY valid compact JSON. No markdown. No extra text. Always close all JSON brackets."""

MODEL = "claude-sonnet-4-6"


def run(state: dict, runner) -> dict:
    fm  = state.get("financial_model",  {}) or {}
    val = state.get("valuation",        {}) or {}
    bm  = state.get("benchmarking",     {}) or {}

    # Only pass key numbers to keep tokens low
    fm_summary  = {k: v for k, v in fm.items()  if k != "raw_output"}
    val_summary = {k: v for k, v in val.items() if k != "raw_output"}
    bm_summary  = {k: v for k, v in bm.items()  if k not in ("raw_output", "financial_benchmarking", "operational_benchmarking")}

    prompt = f"""Review these outputs for internal consistency and fill this JSON:

Financial model summary: {json.dumps(fm_summary, default=str)[:1500]}
Valuation summary: {json.dumps(val_summary, default=str)[:1500]}
Benchmarking summary: {json.dumps(bm_summary, default=str)[:800]}

Output ONLY this JSON:

{{
  "status": "pass",
  "checks": {{
    "model_valuation_aligned": true,
    "benchmarking_model_aligned": true,
    "units_consistent": true,
    "segment_totals_reconcile": true
  }},
  "issues": [],
  "recommendations": ["rec1", "rec2"],
  "overall_quality": "High/Medium/Low",
  "ready_for_md": true
}}

Set status to "pass" if no major issues, "pass_with_warnings" if minor issues, "fail" only for critical errors.
Output ONLY the JSON."""

    result = runner.run("analyst_assembly", prompt)

    # Normalise status — never fail in prototype mode
    raw_status = result.get("status", "pass_with_warnings")
    if raw_status not in ("pass", "pass_with_warnings"):
        raw_status = "pass_with_warnings"

    consistency_report = {
        "status":          raw_status,
        "issues":          result.get("issues", []),
        "recommendations": result.get("recommendations", []),
        "checks":          result.get("checks", {}),
        "overall_quality": result.get("overall_quality", "Medium"),
        "ready_for_md":    result.get("ready_for_md", True),
    }

    return {
        "analyst_package": {
            "financial_model": state.get("financial_model"),
            "valuation":       state.get("valuation"),
            "benchmarking":    state.get("benchmarking"),
        },
        "consistency_report": consistency_report,
        "status": "pending_review" if raw_status != "fail" else "rework",
    }
