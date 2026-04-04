"""
Test script — runs full pipeline with Apple Inc.
No interactive input needed.
"""

import os
import sys
import json
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Fix Unicode for Windows terminal
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Explicitly set API key from .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
with open(env_path) as f:
    for line in f:
        if line.startswith("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = line.strip().split("=", 1)[1]
            break

# ── Add project root to path ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runner import SubAgentRunner
from pipeline import build_analyst_graph

def run_test():
    print("\n" + "="*60)
    print("  IB PITCH ANALYST — TEST RUN")
    print("  Company : Apple Inc.")
    print("  Ticker  : AAPL")
    print("  Type    : Sell-Side Advisory")
    print("  Segments: iPhone, Mac, Services, Wearables")
    print("="*60)

    # ── Test inputs ───────────────────────────────────────────────────────
    deal_context = {
        "target_name":    "Apple Inc.",
        "target_ticker":  "AAPL",
        "sector":         "Technology",
        "geography":      "USA",
        "transaction_type": "sell-side_advisory",
        "segments":       ["iPhone", "Mac", "Services", "Wearables"],
        "listed":         True,
        "pdf_data":       "",
    }

    initial_state = {
        "deal_context":     deal_context,
        "analyst_manifest": {
            "version":          "2.0",
            "company":          deal_context["target_name"],
            "transaction_type": deal_context["transaction_type"],
            "geography":        "USA",
            "data_sources":     ["SEC EDGAR", "yfinance"],
        },
        "raw_data":          None,
        "financial_model":   None,
        "valuation":         None,
        "benchmarking":      None,
        "analyst_package":   None,
        "consistency_report":None,
        "human_feedback":    None,
        "status":            "running",
        "errors":            [],
    }

    # ── Run pipeline ──────────────────────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    runner  = SubAgentRunner(api_key=api_key)
    graph   = build_analyst_graph(runner)

    if not graph:
        print("ERROR: Could not build pipeline graph")
        return

    config      = {"configurable": {"thread_id": "test_apple_001"}}
    final_state = graph.invoke(initial_state, config=config)

    # ── Print cost summary ────────────────────────────────────────────────
    runner.print_cost_summary()

    # ── Print QC results ──────────────────────────────────────────────────
    cr = final_state.get("consistency_report", {})
    print(f"\n{'='*60}")
    print("QC REPORT")
    print(f"{'='*60}")
    print(f"  Status         : {cr.get('status', 'N/A').upper()}")
    print(f"  Quality        : {cr.get('overall_quality', 'N/A')}")
    print(f"  Ready for MD   : {cr.get('ready_for_md', False)}")
    summary = cr.get("summary", {})
    print(f"  Checks Passed  : {summary.get('passed', 0)}/8")
    print(f"  Warnings       : {summary.get('warnings', 0)}")
    print(f"  Critical       : {summary.get('critical', 0)}")

    issues = cr.get("issues", [])
    if issues:
        print(f"\n  Issues Found:")
        for issue in issues:
            icon = "❌" if issue.get("severity") == "critical" else "⚠️ "
            print(f"    {icon} {issue.get('check')}: {issue.get('description')}")

    recs = cr.get("recommendations", [])
    if recs:
        print(f"\n  Recommendations:")
        for r in recs:
            print(f"    → {r}")

    # ── Save output JSON ───────────────────────────────────────────────────
    import datetime
    os.makedirs("outputs", exist_ok=True)
    timestamp   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"outputs/Apple_test_{timestamp}.json"

    output = {
        "company":           "Apple Inc.",
        "ticker":            "AAPL",
        "transaction_type":  "sell-side_advisory",
        "financial_model":   final_state.get("financial_model", {}),
        "valuation":         final_state.get("valuation", {}),
        "benchmarking":      final_state.get("benchmarking", {}),
        "consistency_report":cr,
        "total_cost_usd":    runner.get_total_cost(),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"  OUTPUT SAVED : {output_path}")
    print(f"  TOTAL COST   : ${runner.get_total_cost():.4f}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    run_test()
