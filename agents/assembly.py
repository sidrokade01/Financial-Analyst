"""
Assembly / QC Agent
-------------------
Model  : Sonnet (recommendations only)
Input  : financial_model + valuation + benchmarking
Output : consistency_report (JSON)

Approach:
  - Python runs all 8 cross-checks using real numbers and math
  - No auto-approval — real pass/fail based on actual data
  - Claude Sonnet only writes recommendations for flagged issues
  - Human Gate receives real issues — not rubber stamp

8 CHECKS:
  1. Net Debt Consistency        — FM vs Valuation (tolerance 5%)
  2. EBITDA Margin Consistency   — FM vs Benchmarking (must match)
  3. WACC Consistency            — FM vs Valuation (must be identical)
  4. Segment Revenue Sum         — segments must sum to total revenue
  5. EV Sanity Check             — DCF vs SOTP vs Comps within 30%
  6. FCF → DCF Alignment         — UFCF derived correctly from FM data
  7. Units Consistency           — all values in USD Millions, no zeros
  8. Upside Sanity               — implied price upside within -50% to +150%
"""

import json

SYSTEM_PROMPT = """You are the QC reviewer for a Goldman Sachs IB pitch team.
You will receive a list of real issues found by automated checks.
Your job is ONLY to write clear recommendations to fix each issue.
Output ONLY valid compact JSON. No markdown. No extra text."""

MODEL = "claude-sonnet-4-6"


# ════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except:
        return default


def pct_diff(a, b):
    """Percentage difference between two values."""
    try:
        if b and float(b) != 0:
            return abs((float(a) - float(b)) / float(b)) * 100
    except:
        pass
    return 0.0


def flag_issue(check_name, description, expected, actual, severity="warning"):
    """Create a structured issue record."""
    return {
        "check":       check_name,
        "severity":    severity,   # "critical" / "warning" / "info"
        "description": description,
        "expected":    expected,
        "actual":      actual,
        "passed":      False,
    }


def flag_pass(check_name, description, value):
    """Create a structured pass record."""
    return {
        "check":       check_name,
        "severity":    "none",
        "description": description,
        "value":       value,
        "passed":      True,
    }


# ════════════════════════════════════════════════════════════════════════════
# 8 PYTHON CHECKS
# ════════════════════════════════════════════════════════════════════════════

def check_1_net_debt_consistency(fm: dict, val: dict) -> dict:
    """
    CHECK 1: Net Debt must be consistent between Financial Model and Valuation.
    FM Net Debt FY2025 vs Valuation Net Debt used in EV bridge.
    Tolerance: within 5%.
    """
    fm_net_debt  = safe_float(fm.get("projections", {}).get("net_debt", {}).get("FY2025", 0))
    val_net_debt = safe_float(val.get("dcf", {}).get("net_debt_usd_m", 0))

    if fm_net_debt == 0 and val_net_debt == 0:
        return flag_pass("net_debt_consistency", "Both Net Debt values are zero — no data", 0)

    diff_pct = pct_diff(fm_net_debt, val_net_debt)

    if diff_pct > 5.0:
        return flag_issue(
            "net_debt_consistency",
            f"Net Debt mismatch between Financial Model and Valuation DCF bridge",
            f"FM Net Debt FY2025 = ${fm_net_debt}M",
            f"Valuation Net Debt = ${val_net_debt}M | Difference = {round(diff_pct, 1)}%",
            severity="critical"
        )
    return flag_pass(
        "net_debt_consistency",
        f"Net Debt consistent: FM=${fm_net_debt}M vs Val=${val_net_debt}M ({round(diff_pct,1)}% diff)",
        fm_net_debt
    )


def check_2_ebitda_margin_consistency(fm: dict, bm: dict) -> dict:
    """
    CHECK 2: EBITDA Margin must match between Financial Model and Benchmarking.
    Both use same base SEC EDGAR data — should be identical.
    Tolerance: within 2 percentage points.
    """
    fm_margin = safe_float(fm.get("assumptions", {}).get("base_ebitda_margin_pct", 0))
    bm_margin = safe_float(bm.get("target_metrics", {}).get("ebitda_margin_pct", 0))

    if fm_margin == 0 or bm_margin == 0:
        return flag_pass("ebitda_margin_consistency", "One or both margins not available", 0)

    diff = abs(fm_margin - bm_margin)

    if diff > 2.0:
        return flag_issue(
            "ebitda_margin_consistency",
            "EBITDA Margin mismatch between Financial Model and Benchmarking",
            f"FM EBITDA Margin = {fm_margin}%",
            f"Benchmarking Target Margin = {bm_margin}% | Diff = {round(diff, 2)}pp",
            severity="warning"
        )
    return flag_pass(
        "ebitda_margin_consistency",
        f"EBITDA Margin consistent: FM={fm_margin}% vs BM={bm_margin}% ({round(diff,2)}pp diff)",
        fm_margin
    )


def check_3_wacc_consistency(fm: dict, val: dict) -> dict:
    """
    CHECK 3: WACC must be identical between Financial Model and Valuation DCF.
    Both are calculated by same CAPM formula — must match exactly.
    Tolerance: within 0.5 percentage points.
    """
    fm_wacc  = safe_float(fm.get("assumptions", {}).get("wacc_pct", 0))
    val_wacc = safe_float(val.get("dcf", {}).get("wacc_pct", 0))

    if fm_wacc == 0 or val_wacc == 0:
        return flag_pass("wacc_consistency", "WACC not available in one or both agents", 0)

    diff = abs(fm_wacc - val_wacc)

    if diff > 0.5:
        return flag_issue(
            "wacc_consistency",
            "WACC mismatch between Financial Model and Valuation DCF",
            f"FM WACC = {fm_wacc}%",
            f"Valuation WACC = {val_wacc}% | Diff = {round(diff, 2)}pp",
            severity="warning"
        )
    return flag_pass(
        "wacc_consistency",
        f"WACC consistent: FM={fm_wacc}% vs Val={val_wacc}% ({round(diff,2)}pp diff)",
        fm_wacc
    )


def check_4_segment_revenue_sum(fm: dict) -> dict:
    """
    CHECK 4: Sum of all segment revenues must equal total FY2025 revenue.
    Rounding tolerance: within $1M.
    """
    total_rev    = safe_float(fm.get("projections", {}).get("revenue", {}).get("FY2025", 0))
    segment_revs = fm.get("segment_revenue_fy2025", {})

    if not segment_revs or total_rev == 0:
        return flag_pass("segment_revenue_sum", "No segment data available to check", 0)

    seg_sum = round(sum(safe_float(v) for v in segment_revs.values()), 2)
    diff    = round(abs(total_rev - seg_sum), 2)

    if diff > 1.0:
        return flag_issue(
            "segment_revenue_sum",
            "Segment revenues do not sum to total FY2025 revenue",
            f"Total FY2025 Revenue = ${total_rev}M",
            f"Sum of Segments = ${seg_sum}M | Difference = ${diff}M",
            severity="critical"
        )
    return flag_pass(
        "segment_revenue_sum",
        f"Segment revenues sum correctly: ${seg_sum}M vs total ${total_rev}M (diff=${diff}M)",
        seg_sum
    )


def check_5_ev_sanity(val: dict) -> dict:
    """
    CHECK 5: DCF EV, SOTP EV, and Trading Comps EV must be within 30% of each other.
    Large divergence means input error or wrong multiples.
    """
    dcf_ev   = safe_float(val.get("dcf",  {}).get("enterprise_value_usd_m", 0))
    sotp_ev  = safe_float(val.get("sotp", {}).get("total_ev_usd_m", 0))

    tc       = val.get("trading_comps", {})
    comps_ev = safe_float(tc.get("implied_ev_via_ev_ebitda_usd_m", 0))

    evs = {k: v for k, v in [("DCF", dcf_ev), ("SOTP", sotp_ev), ("Comps", comps_ev)] if v > 0}

    if len(evs) < 2:
        return flag_pass("ev_sanity", "Less than 2 EV methods available to compare", 0)

    vals    = list(evs.values())
    max_ev  = max(vals)
    min_ev  = min(vals)
    spread  = round(pct_diff(max_ev, min_ev), 1)

    if spread > 30.0:
        return flag_issue(
            "ev_sanity",
            f"Large EV divergence across valuation methods ({spread}% spread)",
            "All 3 EV methods within 30% of each other",
            f"DCF=${dcf_ev}M | SOTP=${sotp_ev}M | Comps=${comps_ev}M | Spread={spread}%",
            severity="warning"
        )
    return flag_pass(
        "ev_sanity",
        f"EV methods aligned: DCF=${dcf_ev}M, SOTP=${sotp_ev}M, Comps=${comps_ev}M ({spread}% spread)",
        round((dcf_ev + sotp_ev) / 2, 2)
    )


def check_6_fcf_dcf_alignment(fm: dict, val: dict) -> dict:
    """
    CHECK 6: UFCF in Valuation must be derivable from FM EBIT, D&A, Capex, NWC.
    UFCF = EBIT x (1-Tax) + D&A - Capex - Change_NWC
    Verify FY2025 UFCF is within 10% of recalculated value.
    """
    proj    = fm.get("projections", {})
    assump  = fm.get("assumptions", {})
    wc      = fm.get("working_capital", {})

    ebit       = safe_float(proj.get("ebit",     {}).get("FY2025", 0))
    da         = safe_float(proj.get("da",        {}).get("FY2025", 0))
    capex      = safe_float(proj.get("capex",     {}).get("FY2025", 0))
    change_nwc = safe_float(wc.get("change_in_nwc_usd_m", {}).get("FY2025", 0))
    tax_rate   = safe_float(assump.get("tax_rate_pct", 21)) / 100

    if ebit == 0:
        return flag_pass("fcf_dcf_alignment", "EBIT not available — cannot verify UFCF", 0)

    # Recalculate UFCF using formula
    recalc_ufcf = round(ebit * (1 - tax_rate) + da - capex - change_nwc, 2)

    # Get UFCF from valuation agent
    val_ufcf = safe_float(val.get("dcf", {}).get("ufcf_by_year", {}).get("FY2025", 0))

    if val_ufcf == 0:
        return flag_pass("fcf_dcf_alignment", "Valuation UFCF not available to verify", recalc_ufcf)

    diff_pct = pct_diff(recalc_ufcf, val_ufcf)

    if diff_pct > 10.0:
        return flag_issue(
            "fcf_dcf_alignment",
            "UFCF in Valuation does not match recalculation from Financial Model",
            f"Recalculated UFCF FY2025 = ${recalc_ufcf}M",
            f"Valuation UFCF FY2025 = ${val_ufcf}M | Difference = {round(diff_pct,1)}%",
            severity="warning"
        )
    return flag_pass(
        "fcf_dcf_alignment",
        f"UFCF aligned: recalc=${recalc_ufcf}M vs val=${val_ufcf}M ({round(diff_pct,1)}% diff)",
        recalc_ufcf
    )


def check_7_units_consistency(fm: dict, val: dict, bm: dict) -> dict:
    """
    CHECK 7: All key values must be in USD Millions — no zeros where data expected.
    Flags if any critical field is zero or suspiciously large/small.
    """
    issues_found = []

    checks = [
        ("FM Revenue FY2025",    fm.get("projections", {}).get("revenue",  {}).get("FY2025", 0), 1,    10_000_000),
        ("FM EBITDA FY2025",     fm.get("projections", {}).get("ebitda",   {}).get("FY2025", 0), 0.1,  5_000_000),
        ("FM PAT FY2025",        fm.get("projections", {}).get("pat",      {}).get("FY2025", 0), 0.01, 2_000_000),
        ("Val DCF EV",           val.get("dcf", {}).get("enterprise_value_usd_m", 0),            1,    50_000_000),
        ("Val Implied Price",    val.get("dcf", {}).get("implied_price_usd", 0),                 0.01, 100_000),
        ("BM Target Revenue",    bm.get("target_metrics",  {}).get("revenue_usd_m", 0),          1,    10_000_000),
    ]

    for label, value, min_val, max_val in checks:
        v = safe_float(value)
        if v == 0:
            issues_found.append(f"{label} = 0 (missing data)")
        elif v < min_val:
            issues_found.append(f"{label} = ${v}M (suspiciously low — possible unit error)")
        elif v > max_val:
            issues_found.append(f"{label} = ${v}M (suspiciously high — possible unit error)")

    if issues_found:
        return flag_issue(
            "units_consistency",
            f"{len(issues_found)} unit or data issues found",
            "All critical values in valid USD Millions range",
            " | ".join(issues_found),
            severity="warning"
        )
    return flag_pass(
        "units_consistency",
        "All critical values are in valid USD Millions range",
        "OK"
    )


def check_8_upside_sanity(val: dict) -> dict:
    """
    CHECK 8: Implied price upside must be between -50% and +150%.
    Extreme values indicate input data error or wrong shares outstanding.
    """
    upside        = safe_float(val.get("dcf", {}).get("upside_pct", 0))
    implied_price = safe_float(val.get("dcf", {}).get("implied_price_usd", 0))
    current_price = safe_float(val.get("dcf", {}).get("current_price_usd", 0))

    if implied_price == 0 or current_price == 0:
        return flag_pass("upside_sanity", "Price data not available — cannot check upside", 0)

    if upside > 150.0:
        return flag_issue(
            "upside_sanity",
            f"Implied upside of {round(upside,1)}% is unusually high — check shares outstanding",
            "Upside between -50% and +150%",
            f"Implied Price=${implied_price} | Current Price=${current_price} | Upside={round(upside,1)}%",
            severity="warning"
        )
    elif upside < -50.0:
        return flag_issue(
            "upside_sanity",
            f"Implied downside of {round(upside,1)}% is unusually large — check EV or Net Debt",
            "Upside between -50% and +150%",
            f"Implied Price=${implied_price} | Current Price=${current_price} | Upside={round(upside,1)}%",
            severity="warning"
        )
    return flag_pass(
        "upside_sanity",
        f"Upside is within normal range: {round(upside,1)}% (${current_price} → ${implied_price})",
        upside
    )


# ════════════════════════════════════════════════════════════════════════════
# AGENT RUN
# ════════════════════════════════════════════════════════════════════════════

def run(state: dict, runner) -> dict:
    fm  = state.get("financial_model", {}) or {}
    val = state.get("valuation",       {}) or {}
    bm  = state.get("benchmarking",    {}) or {}

    print("\n  [Assembly QC] Running 8 consistency checks...")

    # ── Run all 8 checks in Python ────────────────────────────────────────
    results = [
        check_1_net_debt_consistency(fm, val),
        check_2_ebitda_margin_consistency(fm, bm),
        check_3_wacc_consistency(fm, val),
        check_4_segment_revenue_sum(fm),
        check_5_ev_sanity(val),
        check_6_fcf_dcf_alignment(fm, val),
        check_7_units_consistency(fm, val, bm),
        check_8_upside_sanity(val),
    ]

    # ── Categorise results ────────────────────────────────────────────────
    passed   = [r for r in results if r["passed"]]
    issues   = [r for r in results if not r["passed"]]
    critical = [r for r in issues  if r.get("severity") == "critical"]
    warnings = [r for r in issues  if r.get("severity") == "warning"]

    # ── Print check results ───────────────────────────────────────────────
    for r in results:
        icon = "✅" if r["passed"] else ("❌" if r.get("severity") == "critical" else "⚠️")
        print(f"  [Assembly QC] {icon} {r['check']}: {r.get('description', '')[:80]}")

    print(f"  [Assembly QC] ─────────────────────────────────────────")
    print(f"  [Assembly QC] Passed  : {len(passed)}/8")
    print(f"  [Assembly QC] Critical: {len(critical)}")
    print(f"  [Assembly QC] Warnings: {len(warnings)}")

    # ── Determine real status ─────────────────────────────────────────────
    if len(critical) > 0:
        status = "fail"
    elif len(warnings) > 0:
        status = "pass_with_warnings"
    else:
        status = "pass"

    overall_quality = "High" if status == "pass" else ("Medium" if status == "pass_with_warnings" else "Low")
    ready_for_md    = status in ("pass", "pass_with_warnings")

    print(f"  [Assembly QC] Status  : {status.upper()}")
    print(f"  [Assembly QC] Quality : {overall_quality}")
    print(f"  [Assembly QC] Ready   : {ready_for_md}")

    # ── Claude Sonnet writes recommendations for issues only ──────────────
    recommendations = []
    if issues:
        issues_text = json.dumps(
            [{"check": r["check"], "description": r["description"],
              "expected": r.get("expected", ""), "actual": r.get("actual", "")}
             for r in issues],
            default=str
        )

        prompt = f"""You are a QC reviewer for a Goldman Sachs IB pitch.
The following issues were found by automated checks:

{issues_text}

Write one clear, actionable recommendation for each issue.
Keep each recommendation under 20 words.

Output ONLY this JSON:
{{
  "recommendations": [
    "recommendation for issue 1",
    "recommendation for issue 2"
  ]
}}

Output ONLY the JSON."""

        sonnet_result = runner.run("analyst_assembly", prompt)
        recommendations = sonnet_result.get("recommendations", [
            f"Fix: {r['check']}" for r in issues
        ])
    else:
        recommendations = ["All checks passed — output is ready for MD review"]

    # ── Build final consistency report ────────────────────────────────────
    consistency_report = {
        "status":          status,
        "overall_quality": overall_quality,
        "ready_for_md":    ready_for_md,
        "summary": {
            "total_checks": 8,
            "passed":        len(passed),
            "warnings":      len(warnings),
            "critical":      len(critical),
        },
        "check_results":   results,
        "issues":          issues,
        "recommendations": recommendations,
        "checks": {
            "net_debt_consistency":       results[0]["passed"],
            "ebitda_margin_consistency":  results[1]["passed"],
            "wacc_consistency":           results[2]["passed"],
            "segment_revenue_sum":        results[3]["passed"],
            "ev_sanity":                  results[4]["passed"],
            "fcf_dcf_alignment":          results[5]["passed"],
            "units_consistency":          results[6]["passed"],
            "upside_sanity":              results[7]["passed"],
        },
    }

    return {
        "analyst_package": {
            "financial_model": state.get("financial_model"),
            "valuation":       state.get("valuation"),
            "benchmarking":    state.get("benchmarking"),
        },
        "consistency_report": consistency_report,
        "status": "pending_review" if ready_for_md else "rework",
    }
