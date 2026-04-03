"""
Valuation Agent
---------------
Model  : Opus (high reasoning for complex valuation judgment)
Input  : financial_model + raw_data
Output : valuation (JSON)
"""

import json

SYSTEM_PROMPT = """You are a Valuation Analyst for a Goldman Sachs IB pitch team.
Output ONLY valid compact JSON. No markdown. No extra text. No explanations outside JSON.
Always close all JSON brackets properly. Use numbers not strings for numeric fields."""

MODEL = "claude-opus-4-6"


def run(state: dict, runner) -> dict:
    ctx = state["deal_context"]
    fm  = state.get("financial_model", {}) or {}

    # Pass only key projection numbers
    proj = fm.get("projections", {})
    rev  = proj.get("revenue", {})
    ebitda = proj.get("ebitda", {})
    fcf    = proj.get("fcf", {})
    assump = fm.get("assumptions", {})

    prompt = f"""Fill this exact valuation JSON for {ctx['target_name']} (Goldman Sachs sell-side pitch, India).
Segments: {', '.join(ctx['segments'])}.
Model projections — Revenue (Cr): {rev}, EBITDA (Cr): {ebitda}, FCF (Cr): {fcf}.
Assumptions: WACC={assump.get('wacc_pct','10')}%, terminal growth={assump.get('terminal_growth_pct','4')}%.

Output ONLY this JSON with real numbers:

{{
  "dcf": {{
    "wacc_pct": 0,
    "terminal_growth_pct": 0,
    "terminal_value_cr": 0,
    "enterprise_value_cr": 0,
    "net_debt_cr": 0,
    "equity_value_cr": 0,
    "implied_price_inr": 0,
    "current_price_inr": 0,
    "upside_pct": 0
  }},
  "sotp": [
    {{"segment": "Thermal Generation",  "ebitda_cr": 0, "ev_ebitda_multiple": 0, "ev_cr": 0}},
    {{"segment": "Renewable Energy",    "ebitda_cr": 0, "ev_ebitda_multiple": 0, "ev_cr": 0}},
    {{"segment": "Distribution",        "ebitda_cr": 0, "ev_ebitda_multiple": 0, "ev_cr": 0}},
    {{"segment": "EV Charging",         "ebitda_cr": 0, "ev_ebitda_multiple": 0, "ev_cr": 0}},
    {{"segment": "Solar Manufacturing", "ebitda_cr": 0, "ev_ebitda_multiple": 0, "ev_cr": 0}},
    {{"segment": "TOTAL SOTP EV",       "ebitda_cr": 0, "ev_ebitda_multiple": 0, "ev_cr": 0}}
  ],
  "trading_comps": [
    {{"peer": "NTPC",        "ev_ebitda": 0, "pe": 0, "ev_capacity_cr_mw": 0}},
    {{"peer": "Adani Power", "ev_ebitda": 0, "pe": 0, "ev_capacity_cr_mw": 0}},
    {{"peer": "JSW Energy",  "ev_ebitda": 0, "pe": 0, "ev_capacity_cr_mw": 0}},
    {{"peer": "Torrent Power","ev_ebitda": 0, "pe": 0, "ev_capacity_cr_mw": 0}},
    {{"peer": "Tata Power (implied)", "ev_ebitda": 0, "pe": 0, "ev_capacity_cr_mw": 0}}
  ],
  "precedent_transactions": [
    {{"year": 0, "deal": "Acquirer acquired Target", "ev_cr": 0, "ev_ebitda": 0, "ev_mw_cr": 0, "premium_pct": 0}},
    {{"year": 0, "deal": "Acquirer acquired Target", "ev_cr": 0, "ev_ebitda": 0, "ev_mw_cr": 0, "premium_pct": 0}},
    {{"year": 0, "deal": "Acquirer acquired Target", "ev_cr": 0, "ev_ebitda": 0, "ev_mw_cr": 0, "premium_pct": 0}},
    {{"year": 0, "deal": "Acquirer acquired Target", "ev_cr": 0, "ev_ebitda": 0, "ev_mw_cr": 0, "premium_pct": 0}}
  ],
  "football_field": {{
    "dcf":                   {{"low_cr": 0, "mid_cr": 0, "high_cr": 0}},
    "sotp":                  {{"low_cr": 0, "mid_cr": 0, "high_cr": 0}},
    "trading_comps":         {{"low_cr": 0, "mid_cr": 0, "high_cr": 0}},
    "precedent_transactions":{{"low_cr": 0, "mid_cr": 0, "high_cr": 0}},
    "recommended":           {{"low_cr": 0, "mid_cr": 0, "high_cr": 0}}
  }},
  "recommended_ev_range": "INR X,XXX - X,XXX Cr",
  "positioning_rationale": "one paragraph on why this range wins the mandate"
}}

Replace all 0s and placeholder text with real estimated numbers and deal names. Output ONLY the JSON."""

    result = runner.run("valuation", prompt, temperature=0.3)
    return {"valuation": result}
