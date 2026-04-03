"""
Data Sourcing Agent
-------------------
Model  : Haiku (pure extraction, no judgment needed)
Input  : deal_context + real data from yfinance + Screener.in
Output : raw_data (JSON)

Flow:
  1. Fetch real data from yfinance + Screener.in
  2. Pass real numbers to Claude Haiku
  3. Claude structures and fills gaps
  4. Output clean raw_data JSON
"""

import json

SYSTEM_PROMPT = """You are a Data Sourcing agent for an investment banking team.
You are given REAL financial data fetched from Yahoo Finance and Screener.in.
Your job is to structure this real data into the required JSON format.
Use the real numbers provided — do NOT guess or estimate if real data is available.
Only estimate for fields where real data is missing.
Output ONLY valid compact JSON. No markdown. No explanations. Always close all brackets."""

MODEL = "claude-haiku-4-5-20251001"


def run(state: dict, runner) -> dict:
    ctx      = state["deal_context"]
    pdf_data = ctx.get("pdf_data", "").strip()
    ticker   = ctx.get("target_ticker", "").strip()

    # ── Step 1: Fetch real data ───────────────────────────────
    real_data_section = ""
    if ticker:
        try:
            from data_fetcher import fetch_all
            real_data = fetch_all(ticker)

            yf       = real_data.get("yfinance", {})
            screener = real_data.get("screener", {})

            # Build a compact summary for the prompt
            yf_summary = {}
            if yf:
                yf_summary = {
                    "stock_price":       yf.get("stock_price"),
                    "market_cap_cr":     yf.get("market_cap_cr"),
                    "pe_ratio":          yf.get("pe_ratio"),
                    "pb_ratio":          yf.get("pb_ratio"),
                    "roe_pct":           yf.get("roe_pct"),
                    "beta":              yf.get("beta"),
                    "week_52_high":      yf.get("week_52_high"),
                    "week_52_low":       yf.get("week_52_low"),
                    "employees":         yf.get("employees"),
                    "historical_financials": yf.get("historical_financials", {}),
                    "latest_cfo_cr":     yf.get("latest_cfo_cr"),
                    "latest_capex_cr":   yf.get("latest_capex_cr"),
                }

            # Screener P&L summary (last 3 years)
            screener_summary = {}
            if screener:
                pl      = screener.get("profit_loss", {})
                bs      = screener.get("balance_sheet", {})
                cf      = screener.get("cash_flow", {})
                ratios  = screener.get("ratios", {})
                km      = screener.get("key_metrics", {})
                screener_summary = {
                    "key_metrics":   km,
                    "profit_loss":   {k: v for k, v in list(pl.items())[:10]},
                    "balance_sheet": {k: v for k, v in list(bs.items())[:8]},
                    "cash_flow":     {k: v for k, v in list(cf.items())[:6]},
                    "ratios":        {k: v for k, v in list(ratios.items())[:8]},
                }

            real_data_section = f"""
=== REAL DATA FROM YAHOO FINANCE (yfinance) ===
{json.dumps(yf_summary, indent=2, default=str)[:3000]}
=== END YAHOO FINANCE DATA ===

=== REAL DATA FROM SCREENER.IN ===
{json.dumps(screener_summary, indent=2, default=str)[:3000]}
=== END SCREENER DATA ===

INSTRUCTIONS:
- Use the above REAL numbers directly in your output
- All financials are in INR Crore unless stated otherwise
- For missing fields only, use reasonable estimates
"""
        except Exception as e:
            print(f"  [Data Fetcher] Warning: {e}")
            real_data_section = ""

    # ── Step 2: PDF section ───────────────────────────────────
    pdf_section = ""
    if pdf_data:
        pdf_section = f"""
=== UPLOADED PDF DATA (HIGHEST PRIORITY — USE THESE NUMBERS) ===
{pdf_data[:4000]}
=== END PDF DATA ===
"""

    # ── Step 3: Build prompt ──────────────────────────────────
    prompt = f"""{pdf_section}{real_data_section}
Using the real data above, fill this JSON for {ctx['target_name']}:

{{
  "company_overview": {{
    "name": "",
    "description": "two sentences",
    "hq": "",
    "employees": 0,
    "stock_price": 0,
    "market_cap_cr": 0,
    "week_52_high": 0,
    "week_52_low": 0,
    "pe_ratio": 0,
    "pb_ratio": 0,
    "beta": 0
  }},
  "historical_financials": {{
    "FY22": {{"revenue_cr": 0, "ebitda_cr": 0, "pat_cr": 0, "net_debt_cr": 0}},
    "FY23": {{"revenue_cr": 0, "ebitda_cr": 0, "pat_cr": 0, "net_debt_cr": 0}},
    "FY24": {{"revenue_cr": 0, "ebitda_cr": 0, "pat_cr": 0, "net_debt_cr": 0}}
  }},
  "cash_flow": {{
    "cfo_cr": 0,
    "capex_cr": 0,
    "fcf_cr": 0
  }},
  "segment_revenue_fy24": {{
    "segment_1": 0,
    "segment_2": 0
  }},
  "operational_metrics": {{
    "installed_capacity_mw": 0,
    "renewable_capacity_mw": 0,
    "plant_load_factor_pct": 0,
    "renewable_share_pct": 0,
    "roe_pct": 0
  }},
  "key_ratios": {{
    "pe_ratio": 0,
    "pb_ratio": 0,
    "ev_ebitda": 0,
    "debt_to_equity": 0,
    "roce_pct": 0
  }},
  "macro_context": ["point1", "point2", "point3"],
  "data_gaps": [],
  "data_sources": ["yfinance", "screener.in"]
}}

Replace segment names with actual segments: {', '.join(ctx['segments'])}.
Use ONLY real numbers from the data above. Output ONLY the JSON."""

    result = runner.run("data_sourcing", prompt)
    return {"raw_data": result}
