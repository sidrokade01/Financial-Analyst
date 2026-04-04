"""
Benchmarking Agent
------------------
Model  : Sonnet (takeaways + outlier analysis only)
Input  : raw_data + financial_model
Output : benchmarking (JSON)

Approach:
  - Python fetches real peer data from yfinance
  - Python calculates ALL metrics using proper IB formulas
  - Python calculates peer medians and quartile rankings
  - Claude Sonnet only writes key takeaways and outlier notes

FORMULAS USED:
  1. EBITDA Margin     = EBITDA / Revenue x 100
  2. Net Debt / EBITDA = Net Debt / EBITDA
  3. EV / EBITDA       = Enterprise Value / EBITDA
  4. P/E Ratio         = Market Price / EPS
  5. ROE               = Net Income / Shareholders Equity x 100
  6. Revenue CAGR      = (Latest Revenue / Oldest Revenue)^(1/n) - 1
  7. Peer Median       = Median of all peer values per metric
  8. EV                = Market Cap + Net Debt
  9. Net Debt          = Total Debt - Cash
  10. Quartile Rank    = position of target vs sorted peer values
"""

import json
import statistics

SYSTEM_PROMPT = """You are a Benchmarking Analyst for a Goldman Sachs IB pitch team.
You will receive pre-calculated benchmarking numbers.
Your job is ONLY to write key takeaways and identify outliers.
Output ONLY valid compact JSON. No markdown. No extra text."""

MODEL = "claude-sonnet-4-6"


# ════════════════════════════════════════════════════════════════════════════
# SECTOR → US PEER MAPPING
# ════════════════════════════════════════════════════════════════════════════

SECTOR_PEERS = {
    "Technology": [
        {"name": "Microsoft",  "ticker": "MSFT"},
        {"name": "Alphabet",   "ticker": "GOOGL"},
        {"name": "Meta",       "ticker": "META"},
        {"name": "Amazon",     "ticker": "AMZN"},
    ],
    "Consumer Electronics": [
        {"name": "Samsung",    "ticker": "005930.KS"},
        {"name": "Sony",       "ticker": "SONY"},
        {"name": "HP Inc",     "ticker": "HPQ"},
        {"name": "Dell",       "ticker": "DELL"},
    ],
    "Communication Services": [
        {"name": "Alphabet",   "ticker": "GOOGL"},
        {"name": "Meta",       "ticker": "META"},
        {"name": "Netflix",    "ticker": "NFLX"},
        {"name": "Disney",     "ticker": "DIS"},
    ],
    "Healthcare": [
        {"name": "Johnson & Johnson", "ticker": "JNJ"},
        {"name": "UnitedHealth",      "ticker": "UNH"},
        {"name": "Pfizer",            "ticker": "PFE"},
        {"name": "Abbott Labs",       "ticker": "ABT"},
    ],
    "Financials": [
        {"name": "JPMorgan Chase", "ticker": "JPM"},
        {"name": "Bank of America","ticker": "BAC"},
        {"name": "Goldman Sachs",  "ticker": "GS"},
        {"name": "Morgan Stanley", "ticker": "MS"},
    ],
    "Consumer Cyclical": [
        {"name": "Tesla",      "ticker": "TSLA"},
        {"name": "Nike",       "ticker": "NKE"},
        {"name": "McDonald's", "ticker": "MCD"},
        {"name": "Starbucks",  "ticker": "SBUX"},
    ],
    "Consumer Defensive": [
        {"name": "Procter & Gamble", "ticker": "PG"},
        {"name": "Coca-Cola",        "ticker": "KO"},
        {"name": "PepsiCo",          "ticker": "PEP"},
        {"name": "Walmart",          "ticker": "WMT"},
    ],
    "Energy": [
        {"name": "ExxonMobil",  "ticker": "XOM"},
        {"name": "Chevron",     "ticker": "CVX"},
        {"name": "ConocoPhillips","ticker": "COP"},
        {"name": "EOG Resources","ticker": "EOG"},
    ],
    "Industrials": [
        {"name": "Honeywell",   "ticker": "HON"},
        {"name": "Caterpillar", "ticker": "CAT"},
        {"name": "Boeing",      "ticker": "BA"},
        {"name": "Deere & Co",  "ticker": "DE"},
    ],
    "Real Estate": [
        {"name": "Prologis",    "ticker": "PLD"},
        {"name": "American Tower","ticker": "AMT"},
        {"name": "Crown Castle", "ticker": "CCI"},
        {"name": "Equinix",     "ticker": "EQIX"},
    ],
    "Utilities": [
        {"name": "NextEra Energy","ticker": "NEE"},
        {"name": "Duke Energy",   "ticker": "DUK"},
        {"name": "Southern Co",   "ticker": "SO"},
        {"name": "Dominion Energy","ticker": "D"},
    ],
    "Basic Materials": [
        {"name": "Linde",        "ticker": "LIN"},
        {"name": "Air Products",  "ticker": "APD"},
        {"name": "Freeport-McMoRan","ticker": "FCX"},
        {"name": "Nucor",        "ticker": "NUE"},
    ],
}

DEFAULT_PEERS = [
    {"name": "Microsoft",  "ticker": "MSFT"},
    {"name": "Alphabet",   "ticker": "GOOGL"},
    {"name": "Amazon",     "ticker": "AMZN"},
    {"name": "Meta",       "ticker": "META"},
]


# ════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def safe_div(a, b, default=0.0):
    try:
        return float(a) / float(b) if b and float(b) != 0 else default
    except:
        return default


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except:
        return default


def peer_median(values: list) -> float:
    """Formula 7: Median of all peer values per metric."""
    clean = [v for v in values if isinstance(v, (int, float)) and v != 0]
    return round(statistics.median(clean), 2) if clean else 0.0


def quartile_rank(target_val: float, peer_vals: list) -> str:
    """
    Formula 10: Quartile ranking of target vs peers.
    Returns: Top Quartile / Mid Quartile / Bottom Quartile
    For metrics where HIGHER is better (Revenue, Margin, ROE, CAGR):
      Top Quartile = target >= 75th percentile
    For metrics where LOWER is better (Net Debt/EBITDA):
      Top Quartile = target <= 25th percentile
    """
    clean = sorted([v for v in peer_vals if v and v != 0])
    if not clean or target_val == 0:
        return "N/A"
    pct_rank = sum(1 for v in clean if v <= target_val) / len(clean)
    if pct_rank >= 0.75:
        return "Top Quartile"
    elif pct_rank >= 0.25:
        return "Mid Quartile"
    else:
        return "Bottom Quartile"


def fetch_peer_data(peers: list) -> dict:
    """
    Fetch real market data for each peer from yfinance.
    Returns dict of ticker -> metrics.
    """
    peer_data = {}
    try:
        import yfinance as yf
        for peer in peers:
            ticker = peer["ticker"]
            try:
                info = yf.Ticker(ticker).info
                market_cap    = safe_float(info.get("marketCap", 0)) / 1e6
                ev_ebitda     = safe_float(info.get("enterpriseToEbitda", 0))
                pe_ratio      = safe_float(info.get("trailingPE", 0))
                roe           = safe_float(info.get("returnOnEquity", 0)) * 100
                profit_margin = safe_float(info.get("profitMargins", 0)) * 100
                revenue       = safe_float(info.get("totalRevenue", 0)) / 1e6
                ebitda        = safe_float(info.get("ebitda", 0)) / 1e6
                total_debt    = safe_float(info.get("totalDebt", 0)) / 1e6
                cash          = safe_float(info.get("totalCash", 0)) / 1e6
                beta          = safe_float(info.get("beta", 1.0))

                # Formula 9: Net Debt = Total Debt - Cash
                net_debt = round(total_debt - cash, 2)

                # Formula 8: EV = Market Cap + Net Debt
                ev = round(market_cap + net_debt, 2)

                # Formula 1: EBITDA Margin = EBITDA / Revenue x 100
                ebitda_margin = round(safe_div(ebitda, revenue) * 100, 2)

                # Formula 2: Net Debt / EBITDA
                net_debt_ebitda = round(safe_div(net_debt, ebitda), 2) if ebitda > 0 else 0

                # Formula 3: EV / EBITDA (use yfinance value — most accurate)
                ev_ebitda_calc = round(safe_div(ev, ebitda), 2) if ebitda > 0 else ev_ebitda

                peer_data[ticker] = {
                    "name":              peer["name"],
                    "ticker":            ticker,
                    "market_cap_usd_m":  round(market_cap, 2),
                    "ev_usd_m":          round(ev, 2),
                    "revenue_usd_m":     round(revenue, 2),
                    "ebitda_usd_m":      round(ebitda, 2),
                    "ebitda_margin_pct": ebitda_margin,
                    "net_debt_usd_m":    net_debt,
                    "net_debt_ebitda":   net_debt_ebitda,
                    "ev_ebitda":         ev_ebitda_calc if ev_ebitda_calc > 0 else ev_ebitda,
                    "pe_ratio":          round(pe_ratio, 2),
                    "roe_pct":           round(roe, 2),
                    "beta":              round(beta, 2),
                }
                print(f"    [Benchmarking] Fetched {peer['name']} ({ticker})")
            except Exception as e:
                print(f"    [Benchmarking] Could not fetch {ticker}: {e}")
                peer_data[ticker] = {"name": peer["name"], "ticker": ticker}
    except ImportError:
        print("    [Benchmarking] yfinance not available for peer data")

    return peer_data


# ════════════════════════════════════════════════════════════════════════════
# MAIN BENCHMARKING ENGINE
# ════════════════════════════════════════════════════════════════════════════

def calculate_benchmarking(raw_data: dict, financial_model: dict, peers: list) -> dict:
    """
    Calculate all benchmarking metrics using proper IB formulas.
    All values in USD Millions.
    """

    # ── Target company data ───────────────────────────────────────────────
    overview  = raw_data.get("company_overview", {})
    hist      = raw_data.get("historical_financials", {})
    proj      = financial_model.get("projections", {})
    assump    = financial_model.get("assumptions", {})

    target_name       = overview.get("name", "Target")
    target_market_cap = safe_float(overview.get("market_cap_usd_m", 0))
    target_pe         = safe_float(overview.get("pe_ratio", 0))
    target_ev_ebitda  = safe_float(overview.get("ev_ebitda", 0))
    target_roe        = safe_float(overview.get("roe_pct", 0))
    target_beta       = safe_float(overview.get("beta", 1.0))

    # Get latest year base data
    valid_years = sorted(
        [y for y in hist.keys() if safe_float(hist[y].get("revenue_usd_m", 0)) > 0],
        reverse=True
    )
    base_yr   = valid_years[0] if valid_years else "2024"
    base      = hist.get(base_yr, {})

    target_revenue    = safe_float(base.get("revenue_usd_m", 0))
    target_op_income  = safe_float(base.get("operating_income_usd_m", 0))
    target_net_income = safe_float(base.get("net_income_usd_m", 0))
    target_debt       = safe_float(base.get("long_term_debt_usd_m", 0))
    target_cash       = safe_float(base.get("cash_usd_m", 0))

    # Formula 9: Net Debt = Total Debt - Cash
    target_net_debt = round(target_debt - target_cash, 2)

    # Formula 1: EBITDA Margin
    da_pct         = safe_float(assump.get("da_pct_of_revenue", 4))
    target_da       = round(target_revenue * da_pct / 100, 2)
    target_ebitda   = round(target_op_income + target_da, 2)
    target_margin   = round(safe_div(target_ebitda, target_revenue) * 100, 2)

    # Formula 2: Net Debt / EBITDA
    target_nd_ebitda = round(safe_div(target_net_debt, target_ebitda), 2)

    # Formula 8: EV = Market Cap + Net Debt
    target_ev = round(target_market_cap + target_net_debt, 2)

    # Formula 3: EV / EBITDA
    target_ev_ebitda_calc = round(safe_div(target_ev, target_ebitda), 2) if target_ebitda > 0 else target_ev_ebitda

    # Formula 6: Revenue CAGR
    target_cagr = safe_float(assump.get("revenue_cagr_used_pct", 0))

    # Formula 5: ROE = Net Income / Equity x 100
    # Approximate equity = assets - debt
    target_assets = safe_float(base.get("total_assets_usd_m", 0))
    target_equity = round(target_assets - target_debt, 2)
    target_roe_calc = round(safe_div(target_net_income, target_equity) * 100, 2) if target_equity > 0 else target_roe

    # ── Fetch real peer data from yfinance ────────────────────────────────
    print(f"  [Benchmarking] Fetching peer data from yfinance...")
    peer_data = fetch_peer_data(peers)

    # ── Build benchmarking metrics table ──────────────────────────────────
    metrics = [
        "revenue_usd_m",
        "ebitda_margin_pct",
        "net_debt_ebitda",
        "ev_ebitda",
        "pe_ratio",
        "roe_pct",
        "revenue_cagr_pct",
    ]

    # Target values
    target_values = {
        "revenue_usd_m":    target_revenue,
        "ebitda_margin_pct":target_margin,
        "net_debt_ebitda":  target_nd_ebitda,
        "ev_ebitda":        target_ev_ebitda_calc if target_ev_ebitda_calc > 0 else target_ev_ebitda,
        "pe_ratio":         target_pe,
        "roe_pct":          target_roe_calc if target_roe_calc != 0 else target_roe,
        "revenue_cagr_pct": target_cagr,
    }

    # Build financial benchmarking table
    financial_benchmarking = []
    metric_labels = {
        "revenue_usd_m":    "Revenue (USD M)",
        "ebitda_margin_pct":"EBITDA Margin (%)",
        "net_debt_ebitda":  "Net Debt / EBITDA (x)",
        "ev_ebitda":        "EV / EBITDA (x)",
        "pe_ratio":         "P/E Ratio (x)",
        "roe_pct":          "ROE (%)",
        "revenue_cagr_pct": "Revenue 3Y CAGR (%)",
    }
    formula_map = {
        "revenue_usd_m":    "From SEC EDGAR 10-K filing",
        "ebitda_margin_pct":"EBITDA / Revenue x 100",
        "net_debt_ebitda":  "Net Debt / EBITDA",
        "ev_ebitda":        "EV / EBITDA | EV = Market Cap + Net Debt",
        "pe_ratio":         "Market Price / EPS  (from yfinance)",
        "roe_pct":          "Net Income / Shareholders Equity x 100",
        "revenue_cagr_pct": "(Latest Revenue / Oldest Revenue)^(1/n) - 1",
    }

    for metric in metrics:
        peer_vals = {}
        all_vals  = []

        for ticker, pdata in peer_data.items():
            val = safe_float(pdata.get(metric, 0))
            # revenue_cagr not available from yfinance — skip
            if metric == "revenue_cagr_pct":
                val = 0
            peer_vals[ticker] = val
            if val != 0:
                all_vals.append(val)

        # Formula 7: Peer Median = Median of all peer values
        median_val = peer_median(all_vals) if all_vals else 0

        row = {
            "metric":       metric_labels[metric],
            "formula":      formula_map[metric],
            "target":       target_values[metric],
            "peer_median":  median_val,
        }
        for ticker, pdata in peer_data.items():
            row[pdata.get("name", ticker).replace(" ", "_").lower()] = safe_float(pdata.get(metric, 0))

        financial_benchmarking.append(row)

    # ── Quartile Rankings ─────────────────────────────────────────────────
    # Formula 10: Rank target vs peers for each metric
    def get_peer_vals_for(metric):
        if metric == "revenue_cagr_pct":
            return []
        return [safe_float(p.get(metric, 0)) for p in peer_data.values() if safe_float(p.get(metric, 0)) != 0]

    # For Net Debt/EBITDA — LOWER is better (inverse ranking)
    nd_peers = get_peer_vals_for("net_debt_ebitda")
    nd_rank  = quartile_rank(target_nd_ebitda, [-v for v in nd_peers]) if nd_peers else "N/A"

    rankings = {
        "revenue":       quartile_rank(target_revenue, get_peer_vals_for("revenue_usd_m")),
        "ebitda_margin": quartile_rank(target_margin,  get_peer_vals_for("ebitda_margin_pct")),
        "leverage":      nd_rank,
        "ev_ebitda":     quartile_rank(target_ev_ebitda_calc, get_peer_vals_for("ev_ebitda")),
        "pe_ratio":      quartile_rank(target_pe,      get_peer_vals_for("pe_ratio")),
        "roe":           quartile_rank(target_roe_calc, get_peer_vals_for("roe_pct")),
        "revenue_cagr":  "N/A — peer CAGR not available from yfinance",
    }

    # ── Peer summary list ─────────────────────────────────────────────────
    peers_summary = []
    for ticker, pdata in peer_data.items():
        if pdata.get("revenue_usd_m", 0):
            peers_summary.append({
                "name":             pdata.get("name", ticker),
                "ticker":           ticker,
                "market_cap_usd_m": pdata.get("market_cap_usd_m", 0),
                "ev_usd_m":         pdata.get("ev_usd_m", 0),
                "revenue_usd_m":    pdata.get("revenue_usd_m", 0),
                "ebitda_margin_pct":pdata.get("ebitda_margin_pct", 0),
                "ev_ebitda":        pdata.get("ev_ebitda", 0),
                "pe_ratio":         pdata.get("pe_ratio", 0),
                "roe_pct":          pdata.get("roe_pct", 0),
                "net_debt_ebitda":  pdata.get("net_debt_ebitda", 0),
            })

    return {
        "target_metrics": {
            "name":              target_name,
            "base_year":         base_yr,
            "revenue_usd_m":     target_revenue,
            "ebitda_usd_m":      target_ebitda,
            "ebitda_margin_pct": target_margin,
            "net_debt_usd_m":    target_net_debt,
            "net_debt_ebitda":   target_nd_ebitda,
            "ev_usd_m":          target_ev,
            "ev_ebitda":         target_ev_ebitda_calc if target_ev_ebitda_calc > 0 else target_ev_ebitda,
            "pe_ratio":          target_pe,
            "roe_pct":           target_roe_calc if target_roe_calc != 0 else target_roe,
            "revenue_cagr_pct":  target_cagr,
            "market_cap_usd_m":  target_market_cap,
        },
        "peers":                  peers_summary,
        "financial_benchmarking": financial_benchmarking,
        "quartile_rankings":      rankings,
        "formula_audit": {
            "1_ebitda_margin":   "EBITDA / Revenue x 100",
            "2_net_debt_ebitda": "Net Debt / EBITDA",
            "3_ev_ebitda":       "EV / EBITDA | EV = Market Cap + Net Debt",
            "4_pe_ratio":        "Market Price / EPS",
            "5_roe":             "Net Income / Shareholders Equity x 100",
            "6_revenue_cagr":    "(Latest/Oldest Revenue)^(1/n) - 1",
            "7_peer_median":     "statistics.median() of all peer values",
            "8_ev":              "EV = Market Cap + Net Debt",
            "9_net_debt":        "Net Debt = Total Debt - Cash",
            "10_quartile":       "Target position vs sorted peer values",
            "data_sources":      "Target: SEC EDGAR 10-K | Peers: yfinance live data",
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# AGENT RUN
# ════════════════════════════════════════════════════════════════════════════

def run(state: dict, runner) -> dict:
    ctx = state["deal_context"]
    raw = state.get("raw_data", {})       or {}
    fm  = state.get("financial_model", {}) or {}

    print("\n  [Benchmarking] Selecting peers and fetching real market data...")

    # ── Select peers based on sector ──────────────────────────────────────
    sector  = raw.get("company_overview", {}).get("sector", "Technology")
    industry= raw.get("company_overview", {}).get("industry", "")
    peers   = SECTOR_PEERS.get(sector, DEFAULT_PEERS)
    print(f"  [Benchmarking] Sector: {sector} | Peers: {[p['name'] for p in peers]}")

    # ── Step 1: Python calculates all metrics using real formulas ─────────
    bm = calculate_benchmarking(raw, fm, peers)

    # Print summary
    tm = bm["target_metrics"]
    print(f"  [Benchmarking] Target Revenue    : ${tm['revenue_usd_m']}M")
    print(f"  [Benchmarking] Target EBITDA Margin: {tm['ebitda_margin_pct']}%")
    print(f"  [Benchmarking] Target EV/EBITDA  : {tm['ev_ebitda']}x")
    print(f"  [Benchmarking] Target PE         : {tm['pe_ratio']}x")
    print(f"  [Benchmarking] Target ROE        : {tm['roe_pct']}%")
    print(f"  [Benchmarking] EBITDA Margin Rank: {bm['quartile_rankings']['ebitda_margin']}")
    print(f"  [Benchmarking] Leverage Rank     : {bm['quartile_rankings']['leverage']}")

    # ── Step 2: Claude Sonnet writes takeaways + outlier analysis ─────────
    prompt = f"""You are a benchmarking analyst for a Goldman Sachs IB pitch.
Company  : {ctx['target_name']}
Sector   : {sector}

Pre-calculated benchmarking results (DO NOT change numbers):
Target Metrics   : {json.dumps(tm, default=str)}
Peer Count       : {len(bm['peers'])} real peers from yfinance
Quartile Rankings: {json.dumps(bm['quartile_rankings'], default=str)}

Financial Benchmarking Table:
{json.dumps(bm['financial_benchmarking'], default=str)[:2000]}

Your job — provide ONLY these 2 things:
1. Key Takeaways: 4 concise bullet points comparing target vs peers
2. Outliers: metrics where target is significantly above or below peers

Output ONLY this JSON:
{{
  "key_takeaways": [
    "point 1 — specific metric comparison",
    "point 2 — specific metric comparison",
    "point 3 — specific metric comparison",
    "point 4 — specific metric comparison"
  ],
  "outliers": [
    {{"metric": "metric name", "target_value": 0, "peer_median": 0, "direction": "above/below", "note": "brief explanation"}},
    {{"metric": "metric name", "target_value": 0, "peer_median": 0, "direction": "above/below", "note": "brief explanation"}}
  ],
  "competitive_positioning": "one sentence on overall competitive position vs peers"
}}

Use real numbers from the pre-calculated data above. Output ONLY the JSON."""

    sonnet_result = runner.run("benchmarking", prompt)

    # ── Merge Python calculations + Claude analysis ────────────────────────
    final_benchmarking = {
        **bm,
        "key_takeaways":          sonnet_result.get("key_takeaways", []),
        "outliers":                sonnet_result.get("outliers", []),
        "competitive_positioning": sonnet_result.get("competitive_positioning", ""),
    }

    return {"benchmarking": final_benchmarking}
