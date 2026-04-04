"""
Data Sourcing Agent
-------------------
Model  : Haiku (fast + low cost)
Input  : deal_context + real data from SEC EDGAR + yfinance
Output : raw_data (JSON)

Flow:
  1. SEC EDGAR  → find company CIK → fetch real financials (official filings)
  2. yfinance   → live stock price, market cap, ratios
  3. PDF upload → quarterly results (if provided)
  4. Claude Haiku structures everything into clean JSON
"""

import json

SYSTEM_PROMPT = """You are a Data Sourcing agent for an investment banking team.
You are given REAL financial data from SEC EDGAR official filings and Yahoo Finance.
Your job is to structure this real data into the required JSON format.
- Use REAL numbers from SEC EDGAR and yfinance — do NOT invent numbers
- All financial values are in USD Millions unless stated otherwise
- Only estimate fields where real data is genuinely missing
- Output ONLY valid compact JSON. No markdown. No explanations."""

MODEL = "claude-haiku-4-5-20251001"


def run(state: dict, runner) -> dict:
    ctx      = state["deal_context"]
    pdf_data = ctx.get("pdf_data", "").strip()
    ticker   = ctx.get("target_ticker", "").strip()
    company  = ctx.get("target_name", "")

    # ── Step 1: Fetch real data from SEC + yfinance ───────────
    real_data_section = ""
    try:
        from data_fetcher import fetch_all
        real_data = fetch_all(company_name=company, ticker=ticker)

        sec  = real_data.get("sec_edgar", {})
        yf   = real_data.get("yfinance", {})
        official_name = real_data.get("official_name", company)

        # Build compact SEC summary for prompt
        sec_summary = {}
        if sec:
            hist = sec.get("historical_financials", {})
            # Latest 3 years
            years = sorted(hist.keys(), reverse=True)[:3]
            sec_summary = {
                "official_name":         official_name,
                "cik":                   sec.get("cik"),
                "source":                sec.get("source"),
                "historical_financials": {yr: hist[yr] for yr in years},
                "operating_cash_flow":   sec.get("operating_cash_flow_usd_m", {}),
                "capex":                 sec.get("capex_usd_m", {}),
            }

        # Build compact yfinance summary
        yf_summary = {}
        if yf:
            yf_summary = {
                "stock_price":       yf.get("stock_price"),
                "market_cap_usd_m":  yf.get("market_cap_usd_m"),
                "pe_ratio":          yf.get("pe_ratio"),
                "forward_pe":        yf.get("forward_pe"),
                "pb_ratio":          yf.get("pb_ratio"),
                "ev_ebitda":         yf.get("ev_ebitda"),
                "roe_pct":           yf.get("roe_pct"),
                "profit_margin_pct": yf.get("profit_margin_pct"),
                "beta":              yf.get("beta"),
                "week_52_high":      yf.get("week_52_high"),
                "week_52_low":       yf.get("week_52_low"),
                "sector":            yf.get("sector"),
                "industry":          yf.get("industry"),
                "employees":         yf.get("employees"),
                "description":       yf.get("description", ""),
            }

        if sec_summary or yf_summary:
            real_data_section = f"""
=== REAL DATA FROM SEC EDGAR (OFFICIAL US GOVERNMENT FILINGS) ===
{json.dumps(sec_summary, indent=2, default=str)[:3000]}
=== END SEC DATA ===

=== REAL DATA FROM YAHOO FINANCE ===
{json.dumps(yf_summary, indent=2, default=str)[:1500]}
=== END YAHOO FINANCE DATA ===

IMPORTANT: Use ONLY these real numbers. Do not guess or fabricate any financial figures.
All values in USD Millions unless stated otherwise.
"""

    except Exception as e:
        print(f"  [Data Sourcing] Data fetch warning: {e}")
        real_data_section = ""

    # ── Step 2: PDF section ───────────────────────────────────
    pdf_section = ""
    if pdf_data:
        pdf_section = f"""
=== UPLOADED PDF DATA (HIGHEST PRIORITY) ===
{pdf_data[:3000]}
=== END PDF DATA ===
"""

    # ── Step 3: Build Claude prompt ───────────────────────────
    prompt = f"""{pdf_section}{real_data_section}
Structure the above real data into this exact JSON for {ctx['target_name']}:

{{
  "company_overview": {{
    "name": "",
    "official_sec_name": "",
    "description": "two sentences about the business",
    "sector": "",
    "industry": "",
    "hq": "",
    "employees": 0,
    "stock_price_usd": 0,
    "market_cap_usd_m": 0,
    "week_52_high": 0,
    "week_52_low": 0,
    "pe_ratio": 0,
    "forward_pe": 0,
    "pb_ratio": 0,
    "ev_ebitda": 0,
    "beta": 0,
    "roe_pct": 0,
    "profit_margin_pct": 0
  }},
  "historical_financials": {{
    "2022": {{"revenue_usd_m": 0, "gross_profit_usd_m": 0, "operating_income_usd_m": 0, "net_income_usd_m": 0, "total_assets_usd_m": 0, "long_term_debt_usd_m": 0, "cash_usd_m": 0, "net_debt_usd_m": 0}},
    "2023": {{"revenue_usd_m": 0, "gross_profit_usd_m": 0, "operating_income_usd_m": 0, "net_income_usd_m": 0, "total_assets_usd_m": 0, "long_term_debt_usd_m": 0, "cash_usd_m": 0, "net_debt_usd_m": 0}},
    "2024": {{"revenue_usd_m": 0, "gross_profit_usd_m": 0, "operating_income_usd_m": 0, "net_income_usd_m": 0, "total_assets_usd_m": 0, "long_term_debt_usd_m": 0, "cash_usd_m": 0, "net_debt_usd_m": 0}}
  }},
  "cash_flow": {{
    "operating_cash_flow_usd_m": {{}},
    "capex_usd_m": {{}},
    "fcf_usd_m": {{}}
  }},
  "segment_revenue": {{
    "segment_1": 0,
    "segment_2": 0
  }},
  "key_ratios": {{
    "gross_margin_pct": 0,
    "ebitda_margin_pct": 0,
    "net_margin_pct": 0,
    "debt_to_equity": 0,
    "current_ratio": 0,
    "revenue_cagr_3yr_pct": 0
  }},
  "macro_context": ["point1", "point2", "point3"],
  "data_sources": ["SEC EDGAR", "Yahoo Finance"],
  "data_gaps": []
}}

Replace segment names with actual business segments: {', '.join(ctx['segments'])}.
Fill FCF = Operating Cash Flow - Capex for each year.
Use ONLY real data from above. Output ONLY the JSON."""

    result = runner.run("data_sourcing", prompt)
    return {"raw_data": result}
