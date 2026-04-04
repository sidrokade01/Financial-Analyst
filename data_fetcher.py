"""
Real Data Fetcher — US Companies
----------------------------------
Sources:
  1. SEC EDGAR Company Search  → find CIK from company name (no API key)
  2. SEC EDGAR Company Facts   → fetch real financials from official filings
  3. yfinance                  → live stock price, market cap, ratios

Flow:
  User enters "Apple"
       ↓
  Search SEC EDGAR → CIK0000320193
       ↓
  Fetch companyfacts JSON → Revenue, NetIncome, Assets, Debt, Cash
       ↓
  yfinance → Stock price, Market cap, P/E, Beta
       ↓
  All real data → Claude agents
"""

import requests
import json
import time


# ── SEC EDGAR headers (required by SEC) ──────────────────────
SEC_HEADERS = {
    "User-Agent": "IB-Pitch-Analyst/1.0 (analyst@ibpitch.com)",
    "Accept":     "application/json",
}

BASE_URL = "https://data.sec.gov"


# ─────────────────────────────────────────────────────────────
# Step 1: Find CIK from company name
# ─────────────────────────────────────────────────────────────

def find_cik(company_name: str) -> tuple:
    """
    Search SEC EDGAR for a company by name.
    Returns (cik_str, official_name) e.g. ("0000320193", "Apple Inc.")
    Uses the company_tickers.json file — lists all SEC-registered companies.
    """
    print(f"  [SEC] Searching for '{company_name}'...")

    try:
        # SEC maintains a full list of all companies with CIK + ticker
        url  = "https://www.sec.gov/files/company_tickers.json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        tickers = resp.json()  # {0: {cik_str, ticker, title}, 1: {...}, ...}

        name_lower = company_name.lower().strip()

        # Try exact match first
        for entry in tickers.values():
            if entry.get("title", "").lower() == name_lower:
                cik = str(entry["cik_str"]).zfill(10)
                print(f"  [SEC] ✅ Found exact match: {entry['title']} (CIK: {cik})")
                return cik, entry["title"]

        # Try partial match
        matches = []
        for entry in tickers.values():
            title = entry.get("title", "").lower()
            if name_lower in title or all(w in title for w in name_lower.split()):
                matches.append(entry)

        if matches:
            # Pick best match (shortest name = most likely exact company)
            best = min(matches, key=lambda x: len(x.get("title", "")))
            cik  = str(best["cik_str"]).zfill(10)
            print(f"  [SEC] ✅ Found: {best['title']} (CIK: {cik})")
            return cik, best["title"]

        # Try ticker symbol match
        for entry in tickers.values():
            if entry.get("ticker", "").lower() == name_lower:
                cik = str(entry["cik_str"]).zfill(10)
                print(f"  [SEC] ✅ Found by ticker: {entry['title']} (CIK: {cik})")
                return cik, entry["title"]

        print(f"  [SEC] ⚠️  Company '{company_name}' not found in SEC database")
        return None, None

    except Exception as e:
        print(f"  [SEC] ⚠️  Search error: {e}")
        return None, None


# ─────────────────────────────────────────────────────────────
# Step 2: Fetch financial facts using CIK
# ─────────────────────────────────────────────────────────────

def fetch_sec_facts(cik: str) -> dict:
    """
    Fetch all company financial facts from SEC EDGAR XBRL API.
    Returns structured financial data.
    """
    url = f"{BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json"
    print(f"  [SEC] Fetching company facts...")

    try:
        resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        facts    = data.get("facts", {})
        us_gaap  = facts.get("us-gaap", {})
        dei      = facts.get("dei", {})

        # ── Helper: get latest annual value for a metric ──────
        def get_annual_values(metric_keys: list, n_years: int = 5) -> dict:
            """
            Try multiple metric key names, return {year: value_in_millions}.
            SEC reports in USD, we convert to millions.
            """
            for key in metric_keys:
                if key not in us_gaap:
                    continue
                units = us_gaap[key].get("units", {})
                usd   = units.get("USD", [])
                if not usd:
                    continue

                # Filter 10-K annual filings only
                annual = [
                    entry for entry in usd
                    if entry.get("form") in ("10-K", "10-K/A")
                    and entry.get("fp") == "FY"
                ]

                if not annual:
                    # fallback — take any 10-K entries
                    annual = [e for e in usd if e.get("form") in ("10-K", "10-K/A")]

                if not annual:
                    continue

                # Sort by end date descending
                annual.sort(key=lambda x: x.get("end", ""), reverse=True)

                # De-duplicate by year
                seen  = {}
                for entry in annual:
                    year = entry.get("end", "")[:4]
                    if year and year not in seen:
                        seen[year] = round(entry.get("val", 0) / 1e6, 1)  # USD → $M

                # Return latest n_years
                result = {}
                for year in sorted(seen.keys(), reverse=True)[:n_years]:
                    result[year] = seen[year]
                return result

            return {}

        # ── Pull key financial metrics ─────────────────────────
        revenue = get_annual_values([
            "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"
        ])

        net_income = get_annual_values([
            "NetIncomeLoss", "ProfitLoss", "NetIncome"
        ])

        total_assets = get_annual_values([
            "Assets"
        ])

        total_liabilities = get_annual_values([
            "Liabilities"
        ])

        long_term_debt = get_annual_values([
            "LongTermDebt", "LongTermDebtNoncurrent"
        ])

        cash = get_annual_values([
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsAndShortTermInvestments",
            "CashAndCashEquivalents"
        ])

        operating_cash_flow = get_annual_values([
            "NetCashProvidedByUsedInOperatingActivities"
        ])

        capex = get_annual_values([
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "CapitalExpendituresIncurredButNotYetPaid"
        ])

        gross_profit = get_annual_values([
            "GrossProfit"
        ])

        operating_income = get_annual_values([
            "OperatingIncomeLoss"
        ])

        # ── Shares outstanding ────────────────────────────────
        shares = get_annual_values(["CommonStockSharesOutstanding"])

        # ── Build structured output ───────────────────────────
        # Get sorted years
        years = sorted(revenue.keys(), reverse=True)[:5] if revenue else []

        historical = {}
        for yr in years:
            rev  = revenue.get(yr)
            ni   = net_income.get(yr)
            debt = long_term_debt.get(yr)
            csh  = cash.get(yr)
            net_debt = round(debt - csh, 1) if debt and csh else None
            historical[yr] = {
                "revenue_usd_m":     rev,
                "gross_profit_usd_m":gross_profit.get(yr),
                "operating_income_usd_m": operating_income.get(yr),
                "net_income_usd_m":  ni,
                "total_assets_usd_m":total_assets.get(yr),
                "long_term_debt_usd_m": debt,
                "cash_usd_m":        csh,
                "net_debt_usd_m":    net_debt,
            }
            # Remove None values
            historical[yr] = {k: v for k, v in historical[yr].items() if v is not None}

        result = {
            "source":           "SEC EDGAR (Official US Government Filing)",
            "cik":              cik,
            "company_name":     data.get("entityName", ""),
            "historical_financials": historical,
            "operating_cash_flow_usd_m": operating_cash_flow,
            "capex_usd_m":      capex,
            "shares_outstanding": shares,
            "metrics_available": list(us_gaap.keys())[:20],  # first 20 available metrics
        }

        total = sum(len(v) for v in historical.values())
        print(f"  [SEC] ✅ Got {len(historical)} years of data ({total} data points)")
        return result

    except requests.HTTPError as e:
        print(f"  [SEC] ⚠️  HTTP Error: {e}")
        return {}
    except Exception as e:
        print(f"  [SEC] ⚠️  Error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# Step 3: yfinance for live market data
# ─────────────────────────────────────────────────────────────

def fetch_yfinance(ticker: str) -> dict:
    """Fetch live market data from Yahoo Finance."""
    try:
        import yfinance as yf
        print(f"  [yfinance] Fetching live market data for {ticker}...")

        stock = yf.Ticker(ticker)
        info  = stock.info or {}

        result = {
            "source":        "Yahoo Finance (yfinance)",
            "ticker":        ticker,
            "stock_price":   info.get("currentPrice") or info.get("regularMarketPrice"),
            "market_cap_usd_m": round(info.get("marketCap", 0) / 1e6, 1),
            "pe_ratio":      info.get("trailingPE"),
            "forward_pe":    info.get("forwardPE"),
            "pb_ratio":      info.get("priceToBook"),
            "ps_ratio":      info.get("priceToSalesTrailing12Months"),
            "ev_ebitda":     info.get("enterpriseToEbitda"),
            "roe_pct":       round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else None,
            "roa_pct":       round(info.get("returnOnAssets", 0) * 100, 2) if info.get("returnOnAssets") else None,
            "profit_margin_pct": round(info.get("profitMargins", 0) * 100, 2) if info.get("profitMargins") else None,
            "beta":          info.get("beta"),
            "week_52_high":  info.get("fiftyTwoWeekHigh"),
            "week_52_low":   info.get("fiftyTwoWeekLow"),
            "dividend_yield":info.get("dividendYield"),
            "employees":     info.get("fullTimeEmployees"),
            "sector":        info.get("sector"),
            "industry":      info.get("industry"),
            "description":   (info.get("longBusinessSummary") or "")[:500],
        }

        # Remove None values
        result = {k: v for k, v in result.items() if v is not None}
        print(f"  [yfinance] ✅ Got live price: ${result.get('stock_price', 'N/A')}, Market Cap: ${result.get('market_cap_usd_m', 'N/A')}M")
        return result

    except ImportError:
        print("  [yfinance] Not installed. Run: pip install yfinance")
        return {}
    except Exception as e:
        print(f"  [yfinance] ⚠️  Error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# Master fetch function
# ─────────────────────────────────────────────────────────────

def fetch_all(company_name: str, ticker: str = "") -> dict:
    """
    Full data fetch for a US company:
      1. SEC EDGAR → find CIK from company name
      2. SEC EDGAR → fetch all financial facts
      3. yfinance  → live stock price + market ratios

    Returns combined dict passed to Data Sourcing agent.
    """
    print(f"\n{'='*60}")
    print(f"  REAL DATA FETCH — {company_name}")
    print(f"{'='*60}")

    # Step 1 + 2: SEC EDGAR
    cik, official_name = find_cik(company_name)
    sec_data = {}
    if cik:
        time.sleep(0.5)  # polite delay for SEC servers
        sec_data = fetch_sec_facts(cik)

    # Step 3: yfinance (use ticker if provided, else skip)
    yf_data = {}
    if ticker:
        time.sleep(0.5)
        yf_data = fetch_yfinance(ticker)

    # Summary
    print(f"\n  {'─'*40}")
    print(f"  SEC Data    : {'✅ Available' if sec_data else '❌ Not found'}")
    print(f"  Market Data : {'✅ Available' if yf_data else '⚠️  No ticker provided'}")
    print(f"  {'─'*40}")

    return {
        "sec_edgar":    sec_data,
        "yfinance":     yf_data,
        "official_name": official_name or company_name,
        "data_quality": {
            "sec_available": bool(sec_data),
            "yfinance_available": bool(yf_data),
            "real_data_used": bool(sec_data or yf_data),
        }
    }
