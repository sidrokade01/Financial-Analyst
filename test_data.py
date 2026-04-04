import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('.env') as f:
    for line in f:
        if 'ANTHROPIC_API_KEY' in line:
            os.environ['ANTHROPIC_API_KEY'] = line.strip().split('=',1)[1]

from data_fetcher import find_cik, fetch_sec_facts, fetch_yfinance

cik, name = find_cik('Apple')
print('CIK:', cik, name)
facts = fetch_sec_facts(cik)
hist  = facts.get('historical_financials', {})
print('Years:', list(hist.keys()))
for yr in sorted(hist.keys(), reverse=True):
    d = hist[yr]
    print(f'  {yr}: Rev=${d.get("revenue_usd_m")}M  NI=${d.get("net_income_usd_m")}M  Debt=${d.get("long_term_debt_usd_m")}M')

print()
yf = fetch_yfinance('AAPL')
print('Price    :', yf.get('stock_price'))
print('MarketCap:', yf.get('market_cap_usd_m'), 'M')
print('PE       :', yf.get('pe_ratio'))
print('Sector   :', yf.get('sector'))
