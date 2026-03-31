"""
Benchmarking Agent
------------------
Model  : Sonnet
Input  : raw_data + financial_model
Output : benchmarking (JSON)
"""

import json

SYSTEM_PROMPT = """You are a Benchmarking Analyst for an investment banking pitch team.
Output ONLY valid compact JSON. No markdown. No extra text. No explanations outside JSON.
Always close all JSON brackets properly."""

MODEL = "claude-sonnet-4-6"


def run(state: dict, runner) -> dict:
    ctx = state["deal_context"]
    raw = state.get("raw_data", {}) or {}
    fm  = state.get("financial_model", {}) or {}

    ops = raw.get("operational_metrics", {})
    hist = raw.get("historical_financials", {})
    fy24 = hist.get("FY24", {})

    prompt = f"""Fill this exact benchmarking JSON for {ctx['target_name']} vs Indian power peers.
Tata Power FY24: Revenue={fy24.get('revenue_cr', 54000)} Cr, EBITDA={fy24.get('ebitda_cr', 11000)} Cr,
Capacity={ops.get('installed_capacity_mw', 14000)} MW, Renewable share={ops.get('renewable_share_pct', 35)}%.

Output ONLY this JSON with real numbers:

{{
  "peers": [
    {{"name": "NTPC",         "ticker": "NTPC.NS",      "market_cap_cr": 0}},
    {{"name": "Adani Power",  "ticker": "ADANIPOWER.NS","market_cap_cr": 0}},
    {{"name": "JSW Energy",   "ticker": "JSWENERGY.NS", "market_cap_cr": 0}},
    {{"name": "Torrent Power","ticker": "TORNTPOWER.NS","market_cap_cr": 0}},
    {{"name": "Tata Power",   "ticker": "TATAPOWER.NS", "market_cap_cr": 0}}
  ],
  "financial_benchmarking": [
    {{"metric": "Revenue FY24 (INR Cr)",      "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0, "peer_median": 0}},
    {{"metric": "EBITDA Margin FY24 (%)",     "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0, "peer_median": 0}},
    {{"metric": "Net Debt / EBITDA (x)",      "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0, "peer_median": 0}},
    {{"metric": "EV / EBITDA (x)",            "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0, "peer_median": 0}},
    {{"metric": "P/E (x)",                    "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0, "peer_median": 0}},
    {{"metric": "ROE (%)",                    "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0, "peer_median": 0}},
    {{"metric": "Revenue 3Y CAGR (%)",        "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0, "peer_median": 0}}
  ],
  "operational_benchmarking": [
    {{"metric": "Installed Capacity (MW)",    "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0}},
    {{"metric": "Renewable Share (%)",        "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0}},
    {{"metric": "Plant Load Factor (%)",      "tata_power": 0, "ntpc": 0, "adani_power": 0, "jsw_energy": 0, "torrent_power": 0}}
  ],
  "tata_power_rankings": {{
    "ebitda_margin": "Top/Mid/Bottom quartile",
    "leverage":      "Top/Mid/Bottom quartile",
    "renewable_share":"Top/Mid/Bottom quartile",
    "revenue_growth": "Top/Mid/Bottom quartile"
  }},
  "key_takeaways": ["point1", "point2", "point3"],
  "outliers": [
    {{"metric": "metric name", "direction": "above/below", "note": "brief explanation"}}
  ]
}}

Replace all 0s with real estimated numbers. Output ONLY the JSON."""

    result = runner.run("benchmarking", prompt)
    return {"benchmarking": result}
