"""
Real Data Fetcher
-----------------
Fetches live financial data from:
  1. yfinance     — stock price, market cap, ratios, financials
  2. Screener.in  — Indian company 5-year P&L, balance sheet, cash flow

This runs BEFORE Claude agents so they work on real numbers, not guesses.
"""

import re
import json
import time


# ─────────────────────────────────────────────────────────────
# yfinance fetcher
# ─────────────────────────────────────────────────────────────

def fetch_yfinance(ticker: str) -> dict:
    """Fetch live data from Yahoo Finance using yfinance."""
    try:
        import yfinance as yf
        print(f"  [yfinance] Fetching data for {ticker}...")

        stock = yf.Ticker(ticker)
        info  = stock.info or {}

        # ── Income Statement ──────────────────────────────────
        try:
            income = stock.financials  # annual, columns = dates
            rev_row    = income.loc["Total Revenue"]    if "Total Revenue"    in income.index else None
            ebitda_row = income.loc["EBITDA"]           if "EBITDA"           in income.index else None
            pat_row    = income.loc["Net Income"]       if "Net Income"       in income.index else None
            dep_row    = income.loc["Reconciled Depreciation"] if "Reconciled Depreciation" in income.index else None
        except Exception:
            rev_row = ebitda_row = pat_row = dep_row = None

        # ── Balance Sheet ─────────────────────────────────────
        try:
            bs        = stock.balance_sheet
            debt_row  = bs.loc["Total Debt"]            if "Total Debt"            in bs.index else None
            cash_row  = bs.loc["Cash And Cash Equivalents"] if "Cash And Cash Equivalents" in bs.index else None
            asset_row = bs.loc["Total Assets"]          if "Total Assets"          in bs.index else None
        except Exception:
            debt_row = cash_row = asset_row = None

        # ── Cash Flow ─────────────────────────────────────────
        try:
            cf       = stock.cashflow
            cfo_row  = cf.loc["Operating Cash Flow"]   if "Operating Cash Flow"   in cf.index else None
            capex_row= cf.loc["Capital Expenditure"]   if "Capital Expenditure"   in cf.index else None
        except Exception:
            cfo_row = capex_row = None

        def to_cr(val):
            """Convert from absolute INR to INR Crore (1 Cr = 10M)."""
            if val is None:
                return None
            try:
                return round(float(val) / 1e7, 1)
            except Exception:
                return None

        def safe_col(row, col_idx):
            """Safely get value from a pandas Series by column index."""
            try:
                if row is None:
                    return None
                vals = row.dropna()
                if col_idx < len(vals):
                    return vals.iloc[col_idx]
                return None
            except Exception:
                return None

        # Build historical financials (latest 3 years)
        historical = {}
        year_labels = ["FY24", "FY23", "FY22"]
        for i, label in enumerate(year_labels):
            rev   = to_cr(safe_col(rev_row,    i))
            ebitda= to_cr(safe_col(ebitda_row, i))
            pat   = to_cr(safe_col(pat_row,    i))
            debt  = to_cr(safe_col(debt_row,   i))
            cash  = to_cr(safe_col(cash_row,   i))
            net_debt = round(debt - cash, 1) if debt and cash else None
            historical[label] = {
                "revenue_cr":  rev,
                "ebitda_cr":   ebitda,
                "pat_cr":      pat,
                "net_debt_cr": net_debt,
            }

        # Latest year operating cash flow and capex
        cfo   = to_cr(safe_col(cfo_row,   0))
        capex = to_cr(safe_col(capex_row, 0))
        if capex and capex < 0:
            capex = abs(capex)  # capex is usually negative in yfinance

        # Market data
        market_cap_cr = to_cr(info.get("marketCap"))
        stock_price   = info.get("currentPrice") or info.get("regularMarketPrice")
        pe_ratio      = info.get("trailingPE")
        pb_ratio      = info.get("priceToBook")
        roe           = round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else None
        beta          = info.get("beta")
        shares_out    = to_cr(info.get("sharesOutstanding"))  # in crore shares
        week_52_high  = info.get("fiftyTwoWeekHigh")
        week_52_low   = info.get("fiftyTwoWeekLow")
        employees     = info.get("fullTimeEmployees")
        description   = info.get("longBusinessSummary", "")[:500]

        result = {
            "source":             "yfinance (Yahoo Finance)",
            "ticker":             ticker,
            "stock_price":        stock_price,
            "market_cap_cr":      market_cap_cr,
            "pe_ratio":           pe_ratio,
            "pb_ratio":           pb_ratio,
            "roe_pct":            roe,
            "beta":               beta,
            "shares_outstanding_cr": shares_out,
            "week_52_high":       week_52_high,
            "week_52_low":        week_52_low,
            "employees":          employees,
            "description":        description,
            "historical_financials": historical,
            "latest_cfo_cr":      cfo,
            "latest_capex_cr":    capex,
        }

        # Remove None values
        result = {k: v for k, v in result.items() if v is not None}
        print(f"  [yfinance] ✅ Got {len(result)} data points")
        return result

    except ImportError:
        print("  [yfinance] Not installed. Run: pip install yfinance")
        return {}
    except Exception as e:
        print(f"  [yfinance] ⚠️  Error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# Screener.in fetcher
# ─────────────────────────────────────────────────────────────

def fetch_screener(company_ticker: str) -> dict:
    """
    Fetch financial data from Screener.in.
    company_ticker: BSE/NSE symbol e.g. TATAPOWER, ADANIPOWER, HDFCBANK
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        # Strip exchange suffix (.NS / .BO)
        symbol = company_ticker.upper().replace(".NS", "").replace(".BO", "").replace(".BSE", "")
        url    = f"https://www.screener.in/company/{symbol}/consolidated/"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

        print(f"  [Screener] Fetching {url}...")
        resp = requests.get(url, headers=headers, timeout=15)

        if resp.status_code == 404:
            # Try standalone (non-consolidated)
            url  = f"https://www.screener.in/company/{symbol}/"
            resp = requests.get(url, headers=headers, timeout=15)

        if resp.status_code != 200:
            print(f"  [Screener] ⚠️  HTTP {resp.status_code}")
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")

        # ── Helper: parse a table by section id ───────────────
        def parse_table(section_id: str) -> dict:
            """Parse a financial table from Screener into dict of {metric: {year: value}}"""
            section = soup.find("section", {"id": section_id})
            if not section:
                return {}

            table = section.find("table")
            if not table:
                return {}

            rows   = table.find_all("tr")
            if not rows:
                return {}

            # Header row — get years
            headers = [th.get_text(strip=True) for th in rows[0].find_all("th")]
            years   = headers[1:]  # skip first col (metric name)

            data = {}
            for row in rows[1:]:
                cols   = row.find_all("td")
                if not cols:
                    continue
                metric = cols[0].get_text(strip=True)
                values = {}
                for i, col in enumerate(cols[1:]):
                    if i < len(years):
                        raw = col.get_text(strip=True).replace(",", "").replace("%", "")
                        try:
                            values[years[i]] = float(raw)
                        except ValueError:
                            values[years[i]] = raw
                data[metric] = values
            return data

        # ── Key Metrics (top of page) ──────────────────────────
        def parse_key_metrics() -> dict:
            metrics = {}
            ul = soup.find("ul", {"id": "top-ratios"})
            if ul:
                for li in ul.find_all("li"):
                    name_el  = li.find("span", {"class": "name"})
                    value_el = li.find("span", {"class": "number"})
                    if name_el and value_el:
                        name  = name_el.get_text(strip=True)
                        value = value_el.get_text(strip=True).replace(",", "").replace("%", "").replace("₹", "")
                        try:
                            metrics[name] = float(value)
                        except ValueError:
                            metrics[name] = value
            return metrics

        key_metrics = parse_key_metrics()
        pl          = parse_table("profit-loss")
        balance     = parse_table("balance-sheet")
        cashflow    = parse_table("cash-flow")
        ratios      = parse_table("ratios")

        result = {
            "source":       "Screener.in",
            "symbol":       symbol,
            "key_metrics":  key_metrics,
            "profit_loss":  pl,
            "balance_sheet":balance,
            "cash_flow":    cashflow,
            "ratios":       ratios,
        }

        # Count data points found
        total = sum(len(v) for v in [pl, balance, cashflow, ratios] if v)
        print(f"  [Screener] ✅ Got {total} metrics across P&L, Balance Sheet, Cash Flow, Ratios")
        return result

    except ImportError:
        print("  [Screener] beautifulsoup4/requests not installed. Run: pip install requests beautifulsoup4")
        return {}
    except Exception as e:
        print(f"  [Screener] ⚠️  Error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# Master fetch function
# ─────────────────────────────────────────────────────────────

def fetch_all(ticker: str) -> dict:
    """
    Fetch data from both yfinance and Screener.in.
    Returns a combined dict passed to the Data Sourcing agent.
    """
    print(f"\n{'='*60}")
    print(f"  REAL DATA FETCH — {ticker}")
    print(f"{'='*60}")

    yf_data      = fetch_yfinance(ticker)
    time.sleep(1)  # polite delay
    screener_data = fetch_screener(ticker)

    combined = {
        "yfinance":  yf_data,
        "screener":  screener_data,
        "data_quality": {
            "yfinance_available":  bool(yf_data),
            "screener_available":  bool(screener_data),
            "real_data_used":      bool(yf_data or screener_data),
        }
    }

    if yf_data:
        print(f"\n  Stock Price  : ₹{yf_data.get('stock_price', 'N/A')}")
        print(f"  Market Cap   : ₹{yf_data.get('market_cap_cr', 'N/A')} Cr")
        print(f"  P/E Ratio    : {yf_data.get('pe_ratio', 'N/A')}x")

    return combined
