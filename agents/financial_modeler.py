"""
Financial Modeler Agent
-----------------------
Model  : Sonnet (structured model building)
Input  : raw_data (from Data Sourcing)
Output : financial_model (JSON)
"""

import json

SYSTEM_PROMPT = """You are a Financial Modeler for an investment banking pitch team.
Output ONLY valid compact JSON. No markdown. No extra text. No explanations outside JSON.
Always close all JSON brackets properly. Use numbers not strings for numeric fields."""

MODEL = "claude-sonnet-4-6"


def run(state: dict, runner) -> dict:
    ctx = state["deal_context"]
    raw = state.get("raw_data", {}) or {}

    # Extract only key numbers to keep input short
    hist = raw.get("historical_financials", {})
    fy24 = hist.get("FY24", {})
    base_rev = fy24.get("revenue_cr", 54000)
    base_ebitda = fy24.get("ebitda_cr", 11000)

    prompt = f"""Fill this exact JSON for {ctx['target_name']} 5-year model. Use INR Crore.
FY24 base: Revenue={base_rev} Cr, EBITDA={base_ebitda} Cr.
Segments: {', '.join(ctx['segments'])}.

Output ONLY this JSON with real numbers:

{{
  "projections": {{
    "revenue":           {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}},
    "ebitda":            {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}},
    "ebitda_margin_pct": {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}},
    "pat":               {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}},
    "capex":             {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}},
    "fcf":               {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}},
    "net_debt":          {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}},
    "cfo":               {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}}
  }},
  "segment_revenue_fy25": {{
    "Thermal Generation": 0,
    "Renewable Energy": 0,
    "Distribution": 0,
    "EV Charging": 0,
    "Solar Manufacturing": 0
  }},
  "debt_schedule": {{
    "total_debt_fy25_cr": 0,
    "avg_cost_of_debt_pct": 0,
    "debt_maturity_profile": {{"within_1yr": 0, "1_3yr": 0, "3_5yr": 0, "beyond_5yr": 0}},
    "annual_repayment_cr": {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}},
    "interest_expense_cr": {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}}
  }},
  "working_capital": {{
    "debtor_days": 0,
    "creditor_days": 0,
    "inventory_days": 0,
    "net_working_capital_cr": {{"FY25": 0, "FY26": 0, "FY27": 0, "FY28": 0, "FY29": 0}}
  }},
  "sensitivity_tables": {{
    "revenue_vs_tariff_pct": {{
      "tariff_minus5pct": {{"FY25": 0, "FY26": 0, "FY27": 0}},
      "tariff_base":      {{"FY25": 0, "FY26": 0, "FY27": 0}},
      "tariff_plus5pct":  {{"FY25": 0, "FY26": 0, "FY27": 0}}
    }},
    "ebitda_vs_fuel_cost_pct": {{
      "fuel_minus10pct": {{"FY25": 0, "FY26": 0, "FY27": 0}},
      "fuel_base":       {{"FY25": 0, "FY26": 0, "FY27": 0}},
      "fuel_plus10pct":  {{"FY25": 0, "FY26": 0, "FY27": 0}}
    }},
    "fcf_vs_capex_pct": {{
      "capex_minus15pct": {{"FY25": 0, "FY26": 0, "FY27": 0}},
      "capex_base":       {{"FY25": 0, "FY26": 0, "FY27": 0}},
      "capex_plus15pct":  {{"FY25": 0, "FY26": 0, "FY27": 0}}
    }}
  }},
  "assumptions": {{
    "revenue_growth_pct": 0,
    "ebitda_margin_target_pct": 0,
    "capex_growth_cr": 0,
    "wacc_pct": 0,
    "terminal_growth_pct": 0,
    "rationale": "one sentence"
  }},
  "balance_check": {{
    "assets_eq_liabilities": true,
    "notes": "one sentence"
  }},
  "high_uncertainty": ["item1"]
}}

Replace all 0s with real estimated numbers. Output ONLY the JSON."""

    result = runner.run("financial_modeler", prompt)
    return {"financial_model": result}
