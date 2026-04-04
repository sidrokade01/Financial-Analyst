"""
Valuation Agent
---------------
Model  : Opus (rationale, peer multiples, precedent transactions)
Input  : financial_model + raw_data
Output : valuation (JSON)

Approach:
  - Python calculates DCF + SOTP using correct IB formulas
  - Uses UNLEVERED FCF (UFCF) for EV-based DCF (not levered FCF)
  - PE multiple gives Equity Value, not EV (fixed)
  - Control premium applied to equity value only (fixed)
  - Claude Opus only judges peer multiples + writes rationale
"""

import json
import math

SYSTEM_PROMPT = """You are a Valuation Analyst for a Goldman Sachs IB pitch team.
You will receive pre-calculated DCF and SOTP numbers. Your job is:
1. Provide realistic peer EV/EBITDA and PE multiples for trading comps
2. Provide 4 real precedent M&A transactions in the same sector
3. Write the positioning rationale
Output ONLY valid compact JSON. No markdown. No extra text."""

MODEL = "claude-opus-4-6"


# ════════════════════════════════════════════════════════════════════════════
# PYTHON FORMULA ENGINE — DCF + SOTP calculated here, not by Claude
# ════════════════════════════════════════════════════════════════════════════

def safe_div(a, b, default=0.0):
    try:
        return float(a) / float(b) if b and float(b) != 0 else default
    except:
        return default


def calculate_dcf(financial_model: dict, raw_data: dict) -> dict:
    """
    DCF using CORRECT IB formula:
    - UFCF = EBIT x (1 - Tax Rate) + D&A - Capex - Change in NWC
    - Discounted at WACC → Enterprise Value
    - EV - Net Debt → Equity Value
    - Equity Value / Shares → Implied Price
    """

    proj   = financial_model.get("projections", {})
    assump = financial_model.get("assumptions", {})
    wc     = financial_model.get("working_capital", {})

    # ── Pull assumptions calculated by financial_modeler ────────────────
    wacc            = float(assump.get("wacc_pct", 9.8)) / 100
    terminal_growth = float(assump.get("terminal_growth_pct", 2.5)) / 100
    tax_rate        = float(assump.get("tax_rate_pct", 21)) / 100

    # ── Net Debt from last projection year's ending net debt ─────────────
    net_debt_proj = proj.get("net_debt", {})
    # Use FY2025 net debt for EV bridge (closest to today)
    net_debt = float(net_debt_proj.get("FY2025", 0))

    # ── Shares outstanding from yfinance ─────────────────────────────────
    overview         = raw_data.get("company_overview", {})
    current_price    = float(overview.get("stock_price_usd", 0) or 0)
    market_cap_usd_m = float(overview.get("market_cap_usd_m", 0) or 0)
    shares_outstanding = safe_div(market_cap_usd_m, current_price)  # in millions

    proj_years = ["FY2025", "FY2026", "FY2027", "FY2028", "FY2029"]

    # ── Calculate UFCF for each year ─────────────────────────────────────
    # CORRECT FORMULA: UFCF = EBIT x (1 - Tax) + D&A - Capex - Change in NWC
    # This is BEFORE interest — capital structure neutral → discounted at WACC → EV
    ufcf_by_year = {}
    pv_ufcf_by_year = {}
    sum_pv_ufcf = 0.0

    change_nwc_dict = wc.get("change_in_nwc_usd_m", {})

    for t, yr in enumerate(proj_years, start=1):
        ebit       = float(proj.get("ebit", {}).get(yr, 0))
        da         = float(proj.get("da", {}).get(yr, 0))
        capex      = float(proj.get("capex", {}).get(yr, 0))
        change_nwc = float(change_nwc_dict.get(yr, 0))

        # UFCF = EBIT x (1 - Tax Rate) + D&A - Capex - Change in NWC
        ufcf = round(ebit * (1 - tax_rate) + da - capex - change_nwc, 2)

        # PV(UFCF_t) = UFCF_t / (1 + WACC)^t
        pv_ufcf = round(ufcf / ((1 + wacc) ** t), 2)

        ufcf_by_year[yr]    = ufcf
        pv_ufcf_by_year[yr] = pv_ufcf
        sum_pv_ufcf        += pv_ufcf

    sum_pv_ufcf = round(sum_pv_ufcf, 2)

    # ── Terminal Value (Gordon Growth Model) ──────────────────────────────
    # TV = UFCF_last x (1 + g) / (WACC - g)
    ufcf_last      = ufcf_by_year.get("FY2029", 0)
    terminal_value = round(
        ufcf_last * (1 + terminal_growth) / (wacc - terminal_growth), 2
    ) if wacc > terminal_growth else 0

    # PV(TV) = TV / (1 + WACC)^5
    pv_terminal_value = round(terminal_value / ((1 + wacc) ** 5), 2)

    # ── Enterprise Value ──────────────────────────────────────────────────
    # EV = Sum of PV(UFCF) + PV(Terminal Value)
    enterprise_value = round(sum_pv_ufcf + pv_terminal_value, 2)

    # ── Equity Value Bridge ───────────────────────────────────────────────
    # Equity Value = EV - Net Debt
    equity_value = round(enterprise_value - net_debt, 2)

    # ── Implied Share Price ───────────────────────────────────────────────
    # Implied Price = Equity Value / Shares Outstanding
    implied_price = round(safe_div(equity_value, shares_outstanding), 2) if shares_outstanding > 0 else 0

    # ── Upside % ─────────────────────────────────────────────────────────
    # Upside = (Implied Price - Current Price) / Current Price x 100
    upside_pct = round(safe_div(implied_price - current_price, current_price) * 100, 2) if current_price > 0 else 0

    # ── Bear / Bull WACC sensitivity ─────────────────────────────────────
    def dcf_ev(wacc_rate):
        pv_sum = sum(
            ufcf_by_year.get(yr, 0) / ((1 + wacc_rate) ** (t + 1))
            for t, yr in enumerate(proj_years)
        )
        tv  = ufcf_last * (1 + terminal_growth) / (wacc_rate - terminal_growth) if wacc_rate > terminal_growth else 0
        pvtv= tv / ((1 + wacc_rate) ** 5)
        return round(pv_sum + pvtv, 2)

    dcf_low  = dcf_ev(wacc + 0.01)   # WACC + 1% → lower EV
    dcf_high = dcf_ev(wacc - 0.01)   # WACC - 1% → higher EV

    return {
        "ufcf_by_year":       ufcf_by_year,
        "pv_ufcf_by_year":    pv_ufcf_by_year,
        "sum_pv_ufcf":        sum_pv_ufcf,
        "terminal_value":     terminal_value,
        "pv_terminal_value":  pv_terminal_value,
        "enterprise_value":   enterprise_value,
        "net_debt":           net_debt,
        "equity_value":       equity_value,
        "shares_outstanding": shares_outstanding,
        "implied_price":      implied_price,
        "current_price":      current_price,
        "upside_pct":         upside_pct,
        "wacc_used":          round(wacc * 100, 2),
        "terminal_growth_used": round(terminal_growth * 100, 2),
        "dcf_range": {
            "low_usd_m":  dcf_low  - net_debt,   # equity value low
            "mid_usd_m":  equity_value,
            "high_usd_m": dcf_high - net_debt,    # equity value high
        },
        "formula_used": "UFCF = EBIT x (1-Tax) + D&A - Capex - Change_NWC | PV = UFCF/(1+WACC)^t | TV = UFCF_last x (1+g)/(WACC-g)",
    }


def calculate_sotp(financial_model: dict, raw_data: dict, segments: list) -> dict:
    """
    SOTP using correct IB formula:
    Segment EV = Segment EBITDA x Segment EV/EBITDA Multiple
    Total SOTP EV = Sum of all Segment EVs
    SOTP Equity Value = Total SOTP EV - Net Debt
    """

    proj    = financial_model.get("projections", {})
    assump  = financial_model.get("assumptions", {})
    seg_rev = financial_model.get("segment_revenue_fy2025", {})

    fy25_revenue = float(proj.get("revenue", {}).get("FY2025", 0))
    fy25_ebitda  = float(proj.get("ebitda", {}).get("FY2025", 0))
    ebitda_margin = float(assump.get("base_ebitda_margin_pct", 25)) / 100

    net_debt     = float(proj.get("net_debt", {}).get("FY2025", 0))

    # ── EV/EBITDA multiples by segment type ──────────────────────────────
    # Based on US sector standards (April 2026)
    sector = raw_data.get("company_overview", {}).get("sector", "Technology")

    # Default multiples by segment growth profile
    default_multiple = 15.0

    segment_multiples = {
        # High growth segments → higher multiples
        "cloud": 25.0, "services": 22.0, "software": 24.0,
        "ai": 30.0, "streaming": 20.0, "subscription": 22.0,
        # Mid growth
        "hardware": 12.0, "devices": 12.0, "consumer": 13.0,
        "iphone": 12.0, "mac": 11.0, "ipad": 10.0,
        "wearables": 14.0, "automotive": 16.0,
        # Mature / stable
        "enterprise": 15.0, "traditional": 9.0,
    }

    sotp_segments = []
    total_sotp_ev = 0.0

    for seg in segments:
        # Segment EBITDA = Segment Revenue x EBITDA Margin
        seg_revenue = float(seg_rev.get(seg, fy25_revenue / len(segments)))
        seg_ebitda  = round(seg_revenue * ebitda_margin, 2)

        # Find best matching multiple
        seg_lower   = seg.lower()
        multiple    = default_multiple
        for key, mult in segment_multiples.items():
            if key in seg_lower:
                multiple = mult
                break

        # Segment EV = Segment EBITDA x EV/EBITDA Multiple
        seg_ev = round(seg_ebitda * multiple, 2)
        total_sotp_ev += seg_ev

        sotp_segments.append({
            "segment":           seg,
            "revenue_usd_m":     seg_revenue,
            "ebitda_usd_m":      seg_ebitda,
            "ev_ebitda_multiple":multiple,
            "ev_usd_m":          seg_ev,
        })

    total_sotp_ev = round(total_sotp_ev, 2)

    # SOTP Equity Value = Total SOTP EV - Net Debt
    sotp_equity_value = round(total_sotp_ev - net_debt, 2)

    sotp_segments.append({
        "segment":           "TOTAL SOTP",
        "revenue_usd_m":     fy25_revenue,
        "ebitda_usd_m":      fy25_ebitda,
        "ev_ebitda_multiple": round(safe_div(total_sotp_ev, fy25_ebitda), 2),
        "ev_usd_m":          total_sotp_ev,
    })

    return {
        "segments":          sotp_segments,
        "total_ev_usd_m":    total_sotp_ev,
        "net_debt_usd_m":    net_debt,
        "equity_value_usd_m":sotp_equity_value,
        "sotp_range": {
            "low_usd_m":  round(total_sotp_ev * 0.90, 2),   # -10% multiple compression
            "mid_usd_m":  total_sotp_ev,
            "high_usd_m": round(total_sotp_ev * 1.10, 2),   # +10% multiple expansion
        },
        "formula_used": "Segment_EV = Segment_EBITDA x EV/EBITDA_Multiple | Total_SOTP_EV = Sum(Segment_EVs) | Equity_Value = Total_EV - Net_Debt",
    }


# ════════════════════════════════════════════════════════════════════════════
# AGENT RUN
# ════════════════════════════════════════════════════════════════════════════

def run(state: dict, runner) -> dict:
    ctx = state["deal_context"]
    fm  = state.get("financial_model", {}) or {}
    raw = state.get("raw_data", {})        or {}

    print("\n  [Valuation] Calculating DCF using UFCF + WACC (correct IB formula)...")

    # ── Step 1: Python calculates DCF + SOTP ─────────────────────────────
    dcf  = calculate_dcf(fm, raw)
    sotp = calculate_sotp(fm, raw, ctx.get("segments", []))

    print(f"  [Valuation] UFCF FY2025         : ${dcf['ufcf_by_year'].get('FY2025', 0)}M")
    print(f"  [Valuation] Sum PV(UFCF)        : ${dcf['sum_pv_ufcf']}M")
    print(f"  [Valuation] PV(Terminal Value)  : ${dcf['pv_terminal_value']}M")
    print(f"  [Valuation] Enterprise Value    : ${dcf['enterprise_value']}M")
    print(f"  [Valuation] Net Debt            : ${dcf['net_debt']}M")
    print(f"  [Valuation] Equity Value        : ${dcf['equity_value']}M")
    print(f"  [Valuation] Implied Price       : ${dcf['implied_price']}")
    print(f"  [Valuation] Current Price       : ${dcf['current_price']}")
    print(f"  [Valuation] Upside %            : {dcf['upside_pct']}%")
    print(f"  [Valuation] SOTP Total EV       : ${sotp['total_ev_usd_m']}M")

    # ── Step 2: Claude Opus provides peer multiples + precedent deals ─────
    overview = raw.get("company_overview", {})
    sector   = overview.get("sector", "Technology")
    industry = overview.get("industry", "")

    proj     = fm.get("projections", {})
    fy25_ebitda = proj.get("ebitda", {}).get("FY2025", 0)
    fy25_pat    = proj.get("pat", {}).get("FY2025", 0)
    net_debt    = dcf["net_debt"]

    prompt = f"""You are a Goldman Sachs valuation analyst.
Company  : {ctx['target_name']}
Sector   : {sector} | Industry: {industry}
Geography: USA

Pre-calculated numbers (DO NOT change these):
  DCF Enterprise Value   : ${dcf['enterprise_value']}M
  DCF Equity Value       : ${dcf['equity_value']}M
  DCF Implied Price      : ${dcf['implied_price']}
  SOTP Total EV          : ${sotp['total_ev_usd_m']}M
  FY2025 EBITDA          : ${fy25_ebitda}M
  FY2025 PAT             : ${fy25_pat}M
  Net Debt               : ${net_debt}M
  Current Stock Price    : ${dcf['current_price']}
  WACC Used              : {dcf['wacc_used']}%

Your job — provide ONLY these 3 things with real numbers:

1. TRADING COMPS — 4 real US peers in {sector}:
   CORRECT FORMULAS:
   EV via EV/EBITDA = Target EBITDA x Peer Median EV/EBITDA  → gives EV directly
   Equity Value via PE = Target PAT x Peer Median PE          → gives Equity Value (NOT EV)
   EV via PE = (Target PAT x Peer Median PE) + Net Debt       → convert to EV

2. PRECEDENT TRANSACTIONS — 4 real M&A deals in {sector} (last 10 years):
   CORRECT FORMULAS:
   Transaction EV/EBITDA = Deal EV / Target EBITDA at time of deal
   Control Premium = (Offer Price - Unaffected Price) / Unaffected Price x 100
   Implied EV = Target EBITDA x Transaction EV/EBITDA  (premium already included in multiple)
   Do NOT apply control premium again on top of EV

3. POSITIONING RATIONALE — one paragraph

Output ONLY this JSON:

{{
  "trading_comps": {{
    "peers": [
      {{"name": "Peer1", "ticker": "XXX", "ev_ebitda_multiple": 0, "pe_multiple": 0, "market_cap_usd_m": 0}},
      {{"name": "Peer2", "ticker": "XXX", "ev_ebitda_multiple": 0, "pe_multiple": 0, "market_cap_usd_m": 0}},
      {{"name": "Peer3", "ticker": "XXX", "ev_ebitda_multiple": 0, "pe_multiple": 0, "market_cap_usd_m": 0}},
      {{"name": "Peer4", "ticker": "XXX", "ev_ebitda_multiple": 0, "pe_multiple": 0, "market_cap_usd_m": 0}}
    ],
    "peer_median_ev_ebitda": 0,
    "peer_median_pe": 0,
    "implied_ev_via_ev_ebitda_usd_m": 0,
    "implied_equity_value_via_pe_usd_m": 0,
    "implied_ev_via_pe_usd_m": 0,
    "formula_ev_ebitda": "EV = EBITDA x Peer_Median_EV_EBITDA",
    "formula_pe": "Equity_Value = PAT x Peer_Median_PE | EV = Equity_Value + Net_Debt"
  }},
  "precedent_transactions": [
    {{"year": 0, "acquirer": "", "target": "", "sector": "", "deal_ev_usd_m": 0, "ev_ebitda_multiple": 0, "control_premium_pct": 0, "implied_ev_for_target_usd_m": 0}},
    {{"year": 0, "acquirer": "", "target": "", "sector": "", "deal_ev_usd_m": 0, "ev_ebitda_multiple": 0, "control_premium_pct": 0, "implied_ev_for_target_usd_m": 0}},
    {{"year": 0, "acquirer": "", "target": "", "sector": "", "deal_ev_usd_m": 0, "ev_ebitda_multiple": 0, "control_premium_pct": 0, "implied_ev_for_target_usd_m": 0}},
    {{"year": 0, "acquirer": "", "target": "", "sector": "", "deal_ev_usd_m": 0, "ev_ebitda_multiple": 0, "control_premium_pct": 0, "implied_ev_for_target_usd_m": 0}}
  ],
  "precedent_range": {{
    "low_ev_usd_m": 0,
    "mid_ev_usd_m": 0,
    "high_ev_usd_m": 0
  }},
  "positioning_rationale": "one paragraph"
}}

Use REAL peer company names and REAL M&A transactions.
Replace all 0s with real numbers. Output ONLY the JSON."""

    opus_result = runner.run("valuation", prompt, temperature=0.2)

    # ── Step 3: Build final valuation output ──────────────────────────────
    trading_comps = opus_result.get("trading_comps", {})
    prec_tx       = opus_result.get("precedent_transactions", [])
    prec_range    = opus_result.get("precedent_range", {})
    rationale     = opus_result.get("positioning_rationale", "")

    # Comps range
    comp_ev = trading_comps.get("implied_ev_via_ev_ebitda_usd_m", dcf["enterprise_value"])
    comp_range = {
        "low_usd_m":  round(float(comp_ev) * 0.90, 2),
        "mid_usd_m":  round(float(comp_ev), 2),
        "high_usd_m": round(float(comp_ev) * 1.10, 2),
    }

    # ── Football Field — correct aggregation ──────────────────────────────
    # Low  = minimum equity value across all methods
    # High = maximum equity value across all methods
    all_lows  = [
        dcf["dcf_range"]["low_usd_m"],
        sotp["sotp_range"]["low_usd_m"] - dcf["net_debt"],
        comp_range["low_usd_m"] - dcf["net_debt"],
        float(prec_range.get("low_ev_usd_m", dcf["enterprise_value"]) or 0) - dcf["net_debt"],
    ]
    all_highs = [
        dcf["dcf_range"]["high_usd_m"],
        sotp["sotp_range"]["high_usd_m"] - dcf["net_debt"],
        comp_range["high_usd_m"] - dcf["net_debt"],
        float(prec_range.get("high_ev_usd_m", dcf["enterprise_value"]) or 0) - dcf["net_debt"],
    ]

    football_field = {
        "dcf": {
            "low_ev_usd_m":    dcf["dcf_range"]["low_usd_m"],
            "mid_ev_usd_m":    dcf["dcf_range"]["mid_usd_m"],
            "high_ev_usd_m":   dcf["dcf_range"]["high_usd_m"],
        },
        "sotp": {
            "low_ev_usd_m":    sotp["sotp_range"]["low_usd_m"],
            "mid_ev_usd_m":    sotp["sotp_range"]["mid_usd_m"],
            "high_ev_usd_m":   sotp["sotp_range"]["high_usd_m"],
        },
        "trading_comps": {
            "low_ev_usd_m":    comp_range["low_usd_m"],
            "mid_ev_usd_m":    comp_range["mid_usd_m"],
            "high_ev_usd_m":   comp_range["high_usd_m"],
        },
        "precedent_transactions": {
            "low_ev_usd_m":    prec_range.get("low_ev_usd_m", 0),
            "mid_ev_usd_m":    prec_range.get("mid_ev_usd_m", 0),
            "high_ev_usd_m":   prec_range.get("high_ev_usd_m", 0),
        },
        "recommended": {
            "low_ev_usd_m":    round(min(v for v in all_lows  if v != 0), 2) if any(all_lows)  else 0,
            "mid_ev_usd_m":    round(dcf["equity_value"], 2),
            "high_ev_usd_m":   round(max(v for v in all_highs if v != 0), 2) if any(all_highs) else 0,
        },
    }

    rec_low  = football_field["recommended"]["low_ev_usd_m"]
    rec_high = football_field["recommended"]["high_ev_usd_m"]

    final_valuation = {
        "dcf": {
            "ufcf_by_year":         dcf["ufcf_by_year"],
            "pv_ufcf_by_year":      dcf["pv_ufcf_by_year"],
            "sum_pv_ufcf_usd_m":    dcf["sum_pv_ufcf"],
            "terminal_value_usd_m": dcf["terminal_value"],
            "pv_terminal_value_usd_m": dcf["pv_terminal_value"],
            "enterprise_value_usd_m":  dcf["enterprise_value"],
            "net_debt_usd_m":          dcf["net_debt"],
            "equity_value_usd_m":      dcf["equity_value"],
            "shares_outstanding_m":    dcf["shares_outstanding"],
            "implied_price_usd":       dcf["implied_price"],
            "current_price_usd":       dcf["current_price"],
            "upside_pct":              dcf["upside_pct"],
            "wacc_pct":                dcf["wacc_used"],
            "terminal_growth_pct":     dcf["terminal_growth_used"],
            "formula": dcf["formula_used"],
        },
        "sotp": {
            "segments":            sotp["segments"],
            "total_ev_usd_m":      sotp["total_ev_usd_m"],
            "net_debt_usd_m":      sotp["net_debt_usd_m"],
            "equity_value_usd_m":  sotp["equity_value_usd_m"],
            "formula": sotp["formula_used"],
        },
        "trading_comps": trading_comps,
        "precedent_transactions": prec_tx,
        "football_field": football_field,
        "recommended_ev_range_usd_m": f"${rec_low}M — ${rec_high}M",
        "positioning_rationale": rationale,
        "formula_audit": {
            "dcf_fcf_type":    "UFCF = EBIT x (1-Tax) + D&A - Capex - Change_NWC  [Unlevered — before interest]",
            "dcf_discount":    "PV = UFCF_t / (1 + WACC)^t",
            "terminal_value":  "TV = UFCF_last x (1+g) / (WACC-g)  [Gordon Growth Model]",
            "ev_bridge":       "EV = Sum_PV_UFCF + PV_TV | Equity_Value = EV - Net_Debt",
            "sotp":            "Segment_EV = Segment_EBITDA x EV/EBITDA_Multiple | Total = Sum(Segment_EVs)",
            "comps_ev_ebitda": "EV = Target_EBITDA x Peer_Median_EV_EBITDA",
            "comps_pe":        "Equity_Value = Target_PAT x Peer_Median_PE | EV = Equity_Value + Net_Debt",
            "control_premium": "Applied to Equity Value only | Prec Tx EV/EBITDA already includes premium",
            "football_field":  "Low = min across methods | High = max across methods",
        },
    }

    return {"valuation": final_valuation}
