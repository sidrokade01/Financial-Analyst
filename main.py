"""
IB Pitch Multi-Agent System — Analyst Pipeline
===============================================
Entry point. Run with:
  python main.py
Output: JSON file in outputs/ folder
"""

from state import DealContext, AnalystState
from runner import SubAgentRunner
from pipeline import build_analyst_graph
from human_gate import human_gate


def get_user_inputs() -> dict:
    """Prompt user for company details in the terminal."""
    print("\n" + "=" * 60)
    print("  IB PITCH ANALYST SYSTEM")
    print("=" * 60)

    company = input("\nCompany Name       : ").strip()
    ticker  = input("Ticker Symbol      : ").strip()
    print("  (Example: TATAPOWER.NS / ADANIPOWER.NS / HDFCBANK.NS)")

    print("\nSector options:")
    sectors = [
        "Power / Utilities",
        "Oil & Gas / Conglomerate",
        "Banking & Financial Services",
        "IT Services",
        "FMCG",
        "Telecommunications",
    ]
    for i, s in enumerate(sectors, 1):
        print(f"  {i}. {s}")
    sec_idx = input("Choose sector (1-6): ").strip()
    sector  = sectors[int(sec_idx) - 1] if sec_idx.isdigit() and 1 <= int(sec_idx) <= 6 else sec_idx

    print("\nGeography options:  India / USA / UK / Singapore / UAE")
    geography = input("Geography          : ").strip() or "India"

    print("\nTransaction Type:   1. Buy  2. Sell  3. IPO  4. Merger  5. Acquisition")
    txn_map = {"1": "buy-side_advisory", "2": "sell-side_advisory", "3": "ipo", "4": "merger", "5": "acquisition"}
    txn_idx = input("Choose type (1-5)  : ").strip()
    transaction_type = txn_map.get(txn_idx, "sell-side_advisory")

    print("\nEnter business segments (comma-separated).")
    print("Example: Thermal Generation, Renewable Energy, Distribution")
    seg_input = input("Segments           : ").strip()
    segments  = [s.strip() for s in seg_input.split(",") if s.strip()]

    print("\nOptional: Path to a PDF file (quarterly results / annual report).")
    print("Press Enter to skip.")
    pdf_path = input("PDF path           : ").strip()
    pdf_text = ""
    if pdf_path:
        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
            for page in reader.pages:
                pdf_text += page.extract_text() + "\n"
            pdf_text = pdf_text[:8000]
            print(f"  PDF loaded — {len(pdf_text)} characters extracted")
        except Exception as e:
            print(f"  Could not read PDF: {e}")

    return {
        "company":          company,
        "ticker":           ticker,
        "sector":           sector,
        "geography":        geography,
        "transaction_type": transaction_type,
        "segments":         segments,
        "pdf_text":         pdf_text,
    }


def run_analyst_pipeline(inputs: dict = None):
    """Execute the full Analyst Agent pipeline."""

    if inputs is None:
        inputs = get_user_inputs()

    deal_context: DealContext = {
        "target_name":      inputs["company"],
        "target_ticker":    inputs["ticker"],
        "sector":           inputs["sector"],
        "segments":         inputs["segments"],
        "transaction_type": inputs["transaction_type"],
        "listed":           True,
        "geography":        inputs["geography"],
        "pdf_data":         inputs.get("pdf_text", ""),
    }

    analyst_manifest = {
        "priority": "high",
        "deadline": "T+48h",
        "iteration_budget": 3,
        "quality_thresholds": {
            "balance_check": True,
            "source_citation": "every_assumption",
            "segment_reconciliation": True,
        },
    }

    initial_state: AnalystState = {
        "deal_context":       deal_context,
        "analyst_manifest":   analyst_manifest,
        "raw_data":           None,
        "financial_model":    None,
        "valuation":          None,
        "benchmarking":       None,
        "analyst_package":    None,
        "consistency_report": None,
        "human_feedback":     None,
        "status":             "running",
        "errors":             [],
    }

    print("\n" + "=" * 60)
    print("IB PITCH AGENT SYSTEM — Analyst Pipeline")
    print(f"  Target  : {deal_context['target_name']}")
    print(f"  Sector  : {deal_context['sector']}")
    print(f"  Segments: {', '.join(deal_context['segments'])}")
    print("=" * 60)

    runner = SubAgentRunner()
    compiled_graph = build_analyst_graph(runner)

    if compiled_graph is not None:
        config      = {"configurable": {"thread_id": f"{inputs['company']}-pitch"}}
        final_state = compiled_graph.invoke(initial_state, config)
    else:
        print("\nRunning sequential pipeline...")
        import agents.data_sourcing     as data_sourcing
        import agents.financial_modeler as financial_modeler
        import agents.benchmarking      as benchmarking
        import agents.valuation         as valuation
        import agents.assembly          as assembly

        state = dict(initial_state)
        state.update(data_sourcing.run(state, runner))
        state.update(financial_modeler.run(state, runner))
        state.update(benchmarking.run(state, runner))
        state.update(valuation.run(state, runner))
        state.update(assembly.run(state, runner))
        final_state = state

    feedback = human_gate(
        final_state.get("analyst_package", {}),
        final_state.get("consistency_report", {}),
    )

    runner.print_cost_summary()

    return final_state, feedback


# ─────────────────────────────────────────────────────────────
# JSON writer
# ─────────────────────────────────────────────────────────────

def write_json(final_state: dict, feedback: dict, output_path: str):
    """Write all pipeline outputs into a single structured JSON file."""
    import json

    cr  = final_state.get("consistency_report") or {}
    ctx = final_state.get("deal_context") or {}

    output = {
        "summary": {
            "company":          ctx.get("target_name"),
            "ticker":           ctx.get("target_ticker"),
            "sector":           ctx.get("sector"),
            "geography":        ctx.get("geography"),
            "transaction_type": ctx.get("transaction_type"),
            "segments":         ctx.get("segments"),
            "decision":         feedback.get("decision"),
            "qc_status":        cr.get("status"),
            "overall_quality":  cr.get("overall_quality"),
            "ready_for_md":     cr.get("ready_for_md"),
        },
        "financial_model": final_state.get("financial_model"),
        "valuation":        final_state.get("valuation"),
        "benchmarking":     final_state.get("benchmarking"),
        "assembly_review":  final_state.get("consistency_report"),
        "human_feedback":   feedback,
        "formula_reference": {
            "financial_model": [
                {"output": "Revenue (FY+1)",      "formula": "Revenue_t = Revenue_(t-1) x (1 + Growth Rate)",         "notes": "CAGR-based projection"},
                {"output": "EBITDA",              "formula": "EBITDA = Revenue x EBITDA Margin %",                     "notes": "Margin applied to revenue"},
                {"output": "EBIT",                "formula": "EBIT = EBITDA - Depreciation",                           "notes": "D&A subtracted"},
                {"output": "PAT",                 "formula": "PAT = EBIT x (1 - Tax Rate)",                            "notes": "Effective tax rate applied"},
                {"output": "Free Cash Flow",      "formula": "FCF = EBITDA - Tax - Capex - Change in Working Capital", "notes": "Unlevered FCF"},
                {"output": "Net Working Capital", "formula": "NWC = Current Assets - Current Liabilities",             "notes": "Balance sheet derived"},
                {"output": "Net Debt",            "formula": "Net Debt = Total Debt - Cash & Equivalents",             "notes": "Used in EV bridge"},
                {"output": "Balance Check",       "formula": "Total Assets = Total Liabilities + Shareholders Equity", "notes": "Must balance"},
            ],
            "valuation": [
                {"output": "Cost of Equity",   "formula": "Re = Rf + Beta x (Rm - Rf)",                                       "notes": "CAPM"},
                {"output": "WACC",             "formula": "WACC = (E/V) x Re + (D/V) x Rd x (1 - Tax Rate)",                  "notes": "Weighted average cost of capital"},
                {"output": "Discounted FCF",   "formula": "PV = FCF_t / (1 + WACC)^t",                                        "notes": "Sum over projection period"},
                {"output": "Terminal Value",   "formula": "TV = FCF_last x (1 + g) / (WACC - g)",                             "notes": "Gordon Growth Model"},
                {"output": "Enterprise Value", "formula": "EV = Sum of PV(FCF) + PV(Terminal Value)",                         "notes": "DCF-based EV"},
                {"output": "Equity Value",     "formula": "Equity Value = EV - Net Debt",                                     "notes": "EV bridge"},
                {"output": "Implied Price",    "formula": "Price = Equity Value / Shares Outstanding",                        "notes": "Per share value"},
                {"output": "Upside %",         "formula": "Upside = (Implied Price - Current Price) / Current Price x 100",   "notes": "vs current market price"},
                {"output": "SOTP EV",          "formula": "Segment EV = Segment EBITDA x EV/EBITDA Multiple",                 "notes": "Sum of parts"},
                {"output": "Trading Comps EV", "formula": "EV = EBITDA x Peer Median EV/EBITDA",                              "notes": "Market multiple"},
            ],
            "benchmarking": [
                {"metric": "EV / EBITDA",       "formula": "EV / EBITDA",                                           "notes": "Primary valuation multiple"},
                {"metric": "P/E Ratio",         "formula": "Market Price / EPS",                                    "notes": "Equity market multiple"},
                {"metric": "Net Debt / EBITDA", "formula": "Net Debt / EBITDA",                                     "notes": "Leverage ratio"},
                {"metric": "ROE",               "formula": "Net Profit / Shareholders Equity x 100",                "notes": "Return on equity (%)"},
                {"metric": "EBITDA Margin",     "formula": "EBITDA / Revenue x 100",                                "notes": "Operating profitability (%)"},
                {"metric": "Revenue CAGR",      "formula": "(Revenue_end / Revenue_start) ^ (1/n) - 1",             "notes": "Compound annual growth rate"},
                {"metric": "EV / MW",           "formula": "Enterprise Value / Installed Capacity (MW)",            "notes": "Capacity-based valuation"},
                {"metric": "Peer Median",       "formula": "Median of all peer values per metric",                  "notes": "Benchmark vs target"},
            ],
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"  JSON saved → {output_path}")


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from datetime import datetime

    load_dotenv()

    final_state, feedback = run_analyst_pipeline()

    output_dir = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ctx       = final_state.get("deal_context") or {}
    safe_name = ctx.get("target_name", "Company").replace(" ", "_").replace("/", "-")

    json_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.json")

    write_json(final_state, feedback, json_path)

    cr = final_state.get("consistency_report") or {}
    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  Decision : {feedback['decision'].upper()}")
    print(f"  QC Status: {cr.get('status', 'N/A').upper()}")
    print(f"  JSON     : {json_path}")
    print(f"{'='*60}")
