"""
Data Sourcing Agent
-------------------
Model  : Haiku (pure extraction, no judgment needed)
Input  : deal_context
Output : raw_data (JSON)
"""

import json

SYSTEM_PROMPT = """You are a Data Sourcing agent for an investment banking team.
Output ONLY valid compact JSON. No markdown. No explanations. No extra text.
If data is unavailable, use reasonable estimates based on public knowledge.
Always close all JSON brackets properly."""

MODEL = "claude-haiku-4-5-20251001"


def run(state: dict, runner) -> dict:
    ctx      = state["deal_context"]
    pdf_data = ctx.get("pdf_data", "").strip()

    # If PDF was uploaded, prepend it to the prompt so Claude uses real data
    pdf_section = ""
    if pdf_data:
        pdf_section = f"""
=== UPLOADED PDF DATA (USE THESE REAL NUMBERS) ===
{pdf_data[:6000]}
=== END OF PDF DATA ===

Use the above PDF data as the PRIMARY source for all financial figures.
Only fall back to estimates if specific data is missing from the PDF.

"""

    prompt = f"""{pdf_section}Return ONLY this JSON structure filled with data for {ctx['target_name']} ({ctx['target_ticker']}):

{{
  "company_overview": {{
    "name": "Tata Power Company Limited",
    "description": "one sentence",
    "hq": "Mumbai, India",
    "employees": 0
  }},
  "historical_financials": {{
    "FY22": {{"revenue_cr": 0, "ebitda_cr": 0, "pat_cr": 0, "net_debt_cr": 0}},
    "FY23": {{"revenue_cr": 0, "ebitda_cr": 0, "pat_cr": 0, "net_debt_cr": 0}},
    "FY24": {{"revenue_cr": 0, "ebitda_cr": 0, "pat_cr": 0, "net_debt_cr": 0}}
  }},
  "segment_revenue_fy24": {{
    "Thermal Generation": 0,
    "Renewable Energy": 0,
    "Distribution": 0,
    "EV Charging": 0,
    "Solar Manufacturing": 0
  }},
  "operational_metrics": {{
    "installed_capacity_mw": 0,
    "renewable_capacity_mw": 0,
    "plant_load_factor_pct": 0,
    "renewable_share_pct": 0
  }},
  "macro_context": ["point1", "point2", "point3"],
  "data_gaps": []
}}

Fill every numeric field with real estimated values. Output ONLY the JSON."""

    result = runner.run("data_sourcing", prompt)
    return {"raw_data": result}
