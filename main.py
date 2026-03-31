"""
IB Pitch Multi-Agent System — Analyst Pipeline
===============================================
Entry point. Run with:
  python main.py
Output: Excel file in outputs/ folder
"""

from state import DealContext, AnalystState
from runner import SubAgentRunner
from pipeline import build_analyst_graph
from human_gate import human_gate


def run_analyst_pipeline():
    """Execute the full Analyst Agent pipeline for Tata Power."""

    deal_context: DealContext = {
        "target_name": "Tata Power Company Limited",
        "target_ticker": "TATAPOWER.NS",
        "sector": "Power / Utilities",
        "segments": [
            "Thermal Generation",
            "Renewable Energy",
            "Distribution",
            "EV Charging",
            "Solar Manufacturing",
        ],
        "transaction_type": "sell-side_advisory",
        "listed": True,
        "geography": "India",
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
        "deal_context": deal_context,
        "analyst_manifest": analyst_manifest,
        "raw_data": None,
        "financial_model": None,
        "valuation": None,
        "benchmarking": None,
        "analyst_package": None,
        "consistency_report": None,
        "human_feedback": None,
        "status": "running",
        "errors": [],
    }

    print("\n" + "=" * 60)
    print("IB PITCH AGENT SYSTEM — Analyst Pipeline")
    print(f"Target: {deal_context['target_name']}")
    print("=" * 60)

    runner = SubAgentRunner()
    compiled_graph = build_analyst_graph(runner)

    if compiled_graph is not None:
        config = {"configurable": {"thread_id": "tata-power-pitch-001"}}
        final_state = compiled_graph.invoke(initial_state, config)
    else:
        print("\nRunning sequential fallback (no LangGraph)...")
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
# Excel writer
# ─────────────────────────────────────────────────────────────

def write_excel(final_state: dict, feedback: dict, output_path: str):
    """Write all pipeline outputs into a formatted Excel workbook."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("openpyxl not installed. Run: pip install openpyxl")
        return

    wb = Workbook()

    # ── Colour palette ──────────────────────────────────────────
    DARK_BLUE  = "003366"
    LIGHT_BLUE = "D9E1F2"
    GOLD       = "C9A84C"
    WHITE      = "FFFFFF"
    LIGHT_GREY = "F2F2F2"

    def header_font(color=WHITE):
        return Font(name="Calibri", bold=True, color=color, size=11)

    def normal_font():
        return Font(name="Calibri", size=10)

    def title_font():
        return Font(name="Calibri", bold=True, color=DARK_BLUE, size=14)

    def fill(hex_color):
        return PatternFill("solid", fgColor=hex_color)

    def center():
        return Alignment(horizontal="center", vertical="center", wrap_text=True)

    def left():
        return Alignment(horizontal="left", vertical="center", wrap_text=True)

    def thin_border():
        s = Side(style="thin", color="CCCCCC")
        return Border(left=s, right=s, top=s, bottom=s)

    def set_col_width(ws, col, width):
        ws.column_dimensions[get_column_letter(col)].width = width

    def write_section_title(ws, row, col, text, colspan=6):
        cell = ws.cell(row=row, column=col, value=text)
        cell.font = Font(name="Calibri", bold=True, color=DARK_BLUE, size=12)
        cell.fill = fill(LIGHT_BLUE)
        cell.alignment = left()
        cell.border = thin_border()
        if colspan > 1:
            ws.merge_cells(
                start_row=row, start_column=col,
                end_row=row, end_column=col + colspan - 1
            )

    def write_header_row(ws, row, headers, start_col=1):
        for i, h in enumerate(headers):
            cell = ws.cell(row=row, column=start_col + i, value=h)
            cell.font = header_font()
            cell.fill = fill(DARK_BLUE)
            cell.alignment = center()
            cell.border = thin_border()

    def write_data_row(ws, row, values, start_col=1, shade=False):
        bg = LIGHT_GREY if shade else WHITE
        for i, v in enumerate(values):
            cell = ws.cell(row=row, column=start_col + i, value=v)
            cell.font = normal_font()
            cell.fill = fill(bg)
            cell.alignment = left()
            cell.border = thin_border()

    def flatten(obj, prefix=""):
        """Flatten nested dict to list of (key, value) pairs."""
        items = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                full_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, (dict, list)):
                    items.extend(flatten(v, full_key))
                else:
                    items.append((full_key, str(v) if v is not None else ""))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                items.extend(flatten(v, f"{prefix}[{i}]"))
        else:
            items.append((prefix, str(obj) if obj is not None else ""))
        return items

    # ══════════════════════════════════════════════════════════════
    # Sheet 1: SUMMARY
    # ══════════════════════════════════════════════════════════════
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 40
    ws.row_dimensions[2].height = 20

    # Title banner
    ws.merge_cells("A1:F1")
    t = ws["A1"]
    t.value = "TATA POWER — IB PITCH ANALYST PACKAGE"
    t.font = Font(name="Calibri", bold=True, color=WHITE, size=16)
    t.fill = fill(DARK_BLUE)
    t.alignment = center()

    ws.merge_cells("A2:F2")
    sub = ws["A2"]
    sub.value = "Goldman Sachs India IBD | Sell-Side Advisory | Confidential"
    sub.font = Font(name="Calibri", italic=True, color=DARK_BLUE, size=10)
    sub.fill = fill(LIGHT_BLUE)
    sub.alignment = center()

    ctx = final_state.get("deal_context", {})
    row = 4
    write_section_title(ws, row, 1, "Deal Context", 3)
    row += 1
    for label, val in [
        ("Company",          ctx.get("target_name", "")),
        ("Ticker",           ctx.get("target_ticker", "")),
        ("Sector",           ctx.get("sector", "")),
        ("Geography",        ctx.get("geography", "")),
        ("Transaction Type", ctx.get("transaction_type", "")),
        ("Segments",         ", ".join(ctx.get("segments", []))),
    ]:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True, name="Calibri", size=10)
        ws.cell(row=row, column=1).fill = fill(LIGHT_GREY)
        ws.cell(row=row, column=2, value=val).font = normal_font()
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        row += 1

    row += 1
    write_section_title(ws, row, 1, "Pipeline Status", 3)
    row += 1
    cr = final_state.get("consistency_report") or {}
    for label, val in [
        ("Human Gate Decision", feedback.get("decision", "").upper()),
        ("Consistency Status",  cr.get("status", "N/A").upper()),
        ("Approved Artifacts",  ", ".join(feedback.get("approved_artifacts", []))),
    ]:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True, name="Calibri", size=10)
        ws.cell(row=row, column=1).fill = fill(LIGHT_GREY)
        ws.cell(row=row, column=2, value=val).font = normal_font()
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        row += 1

    for col, width in [(1, 25), (2, 30), (3, 20), (4, 20), (5, 20), (6, 20)]:
        set_col_width(ws, col, width)

    # ══════════════════════════════════════════════════════════════
    # Sheet 2: FINANCIAL MODEL
    # ══════════════════════════════════════════════════════════════
    ws2 = wb.create_sheet("Financial Model")
    ws2.sheet_view.showGridLines = False

    ws2.merge_cells("A1:G1")
    t2 = ws2["A1"]
    t2.value = "FINANCIAL MODEL — 5-YEAR PROJECTIONS"
    t2.font = Font(name="Calibri", bold=True, color=WHITE, size=14)
    t2.fill = fill(DARK_BLUE)
    t2.alignment = center()
    ws2.row_dimensions[1].height = 35

    fm = final_state.get("financial_model") or {}

    if fm.get("parse_error"):
        ws2.cell(row=3, column=1, value="Raw Output (parse error — see below):").font = Font(bold=True, name="Calibri")
        raw = fm.get("raw_output", "")
        lines = str(raw).split("\n")
        for i, line in enumerate(lines[:200]):
            ws2.cell(row=4 + i, column=1, value=line).font = normal_font()
    else:
        row = 3
        # Projections table
        projections = fm.get("projections", {})
        if projections:
            write_section_title(ws2, row, 1, "Revenue & EBITDA Projections (INR Cr)", 7)
            row += 1
            years = ["FY25", "FY26", "FY27", "FY28", "FY29"]
            write_header_row(ws2, row, ["Metric"] + years + ["CAGR"], 1)
            row += 1
            for metric_name, values in projections.items():
                if isinstance(values, list):
                    data_row = [metric_name.replace("_", " ").title()] + [str(v) for v in values[:5]]
                    write_data_row(ws2, row, data_row, shade=(row % 2 == 0))
                elif isinstance(values, dict):
                    data_row = [metric_name.replace("_", " ").title()] + [str(values.get(y, "")) for y in years]
                    write_data_row(ws2, row, data_row, shade=(row % 2 == 0))
                row += 1

        row += 1
        # Assumptions table
        assumptions = fm.get("assumptions", {})
        if assumptions:
            write_section_title(ws2, row, 1, "Key Assumptions", 7)
            row += 1
            write_header_row(ws2, row, ["Assumption Category", "Value / Description", "Rationale"], 1)
            ws2.merge_cells(start_row=row, start_column=3, end_row=row, end_column=7)
            row += 1
            flat = flatten(assumptions)
            for i, (k, v) in enumerate(flat):
                ws2.cell(row=row, column=1, value=k).font = normal_font()
                ws2.cell(row=row, column=2, value=v).font = normal_font()
                if i % 2 == 0:
                    ws2.cell(row=row, column=1).fill = fill(LIGHT_GREY)
                    ws2.cell(row=row, column=2).fill = fill(LIGHT_GREY)
                row += 1

        row += 1
        # All remaining keys
        skip = {"projections", "assumptions"}
        remaining = {k: v for k, v in fm.items() if k not in skip}
        if remaining:
            write_section_title(ws2, row, 1, "Additional Model Data", 7)
            row += 1
            write_header_row(ws2, row, ["Field", "Value"], 1)
            row += 1
            for k, v in flatten(remaining):
                write_data_row(ws2, row, [k, v], shade=(row % 2 == 0))
                row += 1

    for col, w in [(1, 30), (2, 18), (3, 18), (4, 18), (5, 18), (6, 18), (7, 15)]:
        set_col_width(ws2, col, w)

    # ══════════════════════════════════════════════════════════════
    # Sheet 3: VALUATION
    # ══════════════════════════════════════════════════════════════
    ws3 = wb.create_sheet("Valuation")
    ws3.sheet_view.showGridLines = False

    ws3.merge_cells("A1:F1")
    t3 = ws3["A1"]
    t3.value = "VALUATION SUMMARY — DCF | SOTP | TRADING COMPS | PRECEDENT TRANSACTIONS"
    t3.font = Font(name="Calibri", bold=True, color=WHITE, size=14)
    t3.fill = fill(DARK_BLUE)
    t3.alignment = center()
    ws3.row_dimensions[1].height = 35

    val = final_state.get("valuation") or {}

    if val.get("parse_error"):
        ws3.cell(row=3, column=1, value="Raw Output:").font = Font(bold=True, name="Calibri")
        for i, line in enumerate(str(val.get("raw_output", "")).split("\n")[:200]):
            ws3.cell(row=4 + i, column=1, value=line).font = normal_font()
    else:
        row = 3
        # DCF
        dcf = val.get("dcf", {})
        if dcf:
            write_section_title(ws3, row, 1, "DCF Valuation", 4)
            row += 1
            write_header_row(ws3, row, ["Metric", "Value"], 1)
            row += 1
            for k, v in dcf.items():
                write_data_row(ws3, row, [k.replace("_", " ").title(), str(v)], shade=(row % 2 == 0))
                row += 1

        row += 1
        # SOTP
        sotp = val.get("sotp", [])
        if sotp:
            write_section_title(ws3, row, 1, "Sum-of-Parts (SOTP)", 4)
            row += 1
            if isinstance(sotp, list) and sotp:
                headers = list(sotp[0].keys()) if isinstance(sotp[0], dict) else ["Value"]
                write_header_row(ws3, row, headers, 1)
                row += 1
                for i, item in enumerate(sotp):
                    if isinstance(item, dict):
                        write_data_row(ws3, row, list(item.values()), shade=(i % 2 == 0))
                    else:
                        write_data_row(ws3, row, [str(item)])
                    row += 1
            else:
                write_data_row(ws3, row, [str(sotp)])
                row += 1

        row += 1
        # Trading comps
        comps = val.get("trading_comps", [])
        if comps:
            write_section_title(ws3, row, 1, "Trading Comparables", 4)
            row += 1
            if isinstance(comps, list) and comps:
                headers = list(comps[0].keys()) if isinstance(comps[0], dict) else ["Value"]
                write_header_row(ws3, row, headers, 1)
                row += 1
                for i, item in enumerate(comps):
                    if isinstance(item, dict):
                        write_data_row(ws3, row, list(item.values()), shade=(i % 2 == 0))
                    row += 1
            else:
                write_data_row(ws3, row, [str(comps)])
                row += 1

        row += 1
        # Recommended range
        rec = val.get("recommended_ev_range", "")
        pos = val.get("positioning_rationale", "")
        if rec or pos:
            write_section_title(ws3, row, 1, "Positioning", 4)
            row += 1
            write_data_row(ws3, row, ["Recommended EV Range", str(rec)])
            row += 1
            ws3.merge_cells(start_row=row, start_column=2, end_row=row + 3, end_column=4)
            ws3.cell(row=row, column=1, value="Positioning Rationale").font = Font(bold=True, name="Calibri", size=10)
            c = ws3.cell(row=row, column=2, value=str(pos))
            c.font = normal_font()
            c.alignment = Alignment(wrap_text=True, vertical="top")
            row += 4

        row += 1
        # Precedent Transactions
        prec = val.get("precedent_transactions", [])
        if prec:
            write_section_title(ws3, row, 1, "Precedent Transactions (Indian Power M&A)", 4)
            row += 1
            if isinstance(prec, list) and prec and isinstance(prec[0], dict):
                headers = list(prec[0].keys())
                write_header_row(ws3, row, headers, 1)
                row += 1
                for i, item in enumerate(prec):
                    write_data_row(ws3, row, list(item.values()), shade=(i % 2 == 0))
                    row += 1
            row += 1

        # Football Field — structured
        ff = val.get("football_field", {})
        if ff:
            write_section_title(ws3, row, 1, "Football Field — Valuation Range (INR Cr EV)", 4)
            row += 1
            write_header_row(ws3, row, ["Methodology", "Low", "Mid", "High"], 1)
            row += 1
            for method, vals in ff.items():
                if isinstance(vals, dict):
                    write_data_row(ws3, row, [
                        method.replace("_", " ").title(),
                        vals.get("low_cr", vals.get("low", "-")),
                        vals.get("mid_cr", vals.get("mid", "-")),
                        vals.get("high_cr", vals.get("high", "-")),
                    ], shade=(row % 2 == 0))
                else:
                    write_data_row(ws3, row, [method.replace("_", " ").title(), str(vals), "", ""], shade=(row % 2 == 0))
                row += 1
            row += 1

        # Any remaining fields
        skip = {"dcf", "sotp", "trading_comps", "football_field", "precedent_transactions", "recommended_ev_range", "positioning_rationale"}
        remaining = {k: v for k, v in val.items() if k not in skip}
        if remaining:
            write_section_title(ws3, row, 1, "Additional Valuation Data", 4)
            row += 1
            for k, v in flatten(remaining):
                write_data_row(ws3, row, [k, str(v)], shade=(row % 2 == 0))
                row += 1

    for col, w in [(1, 30), (2, 22), (3, 22), (4, 22), (5, 20), (6, 20)]:
        set_col_width(ws3, col, w)

    # ══════════════════════════════════════════════════════════════
    # Sheet 4: BENCHMARKING
    # ══════════════════════════════════════════════════════════════
    ws4 = wb.create_sheet("Benchmarking")
    ws4.sheet_view.showGridLines = False

    ws4.merge_cells("A1:F1")
    t4 = ws4["A1"]
    t4.value = "PEER BENCHMARKING — OPERATIONAL & FINANCIAL METRICS"
    t4.font = Font(name="Calibri", bold=True, color=WHITE, size=14)
    t4.fill = fill(DARK_BLUE)
    t4.alignment = center()
    ws4.row_dimensions[1].height = 35

    bm = final_state.get("benchmarking") or {}

    if bm.get("parse_error"):
        ws4.cell(row=3, column=1, value="Raw Output:").font = Font(bold=True, name="Calibri")
        for i, line in enumerate(str(bm.get("raw_output", "")).split("\n")[:200]):
            ws4.cell(row=4 + i, column=1, value=line).font = normal_font()
    else:
        row = 3
        # Peers
        peers = bm.get("peers", [])
        if peers:
            write_section_title(ws4, row, 1, "Peer Universe", 4)
            row += 1
            if isinstance(peers, list) and peers and isinstance(peers[0], dict):
                headers = list(peers[0].keys())
                write_header_row(ws4, row, headers, 1)
                row += 1
                for i, p in enumerate(peers):
                    write_data_row(ws4, row, list(p.values()), shade=(i % 2 == 0))
                    row += 1
            else:
                for p in peers:
                    write_data_row(ws4, row, [str(p)])
                    row += 1

        row += 1
        # Financial benchmarking
        fin_bm = bm.get("financial_benchmarking", [])
        if fin_bm:
            write_section_title(ws4, row, 1, "Financial Benchmarking", 5)
            row += 1
            if isinstance(fin_bm, list) and fin_bm and isinstance(fin_bm[0], dict):
                headers = list(fin_bm[0].keys())
                write_header_row(ws4, row, headers, 1)
                row += 1
                for i, item in enumerate(fin_bm):
                    write_data_row(ws4, row, list(item.values()), shade=(i % 2 == 0))
                    row += 1
            else:
                flat = flatten(fin_bm)
                write_header_row(ws4, row, ["Metric", "Value"], 1)
                row += 1
                for k, v in flat:
                    write_data_row(ws4, row, [k, v], shade=(row % 2 == 0))
                    row += 1

        row += 1
        # Operational benchmarking
        op_bm = bm.get("operational_benchmarking", [])
        if op_bm:
            write_section_title(ws4, row, 1, "Operational Benchmarking", 5)
            row += 1
            if isinstance(op_bm, list) and op_bm and isinstance(op_bm[0], dict):
                headers = list(op_bm[0].keys())
                write_header_row(ws4, row, headers, 1)
                row += 1
                for i, item in enumerate(op_bm):
                    write_data_row(ws4, row, list(item.values()), shade=(i % 2 == 0))
                    row += 1

        row += 1
        # Key takeaways
        takeaways = bm.get("key_takeaways", [])
        if takeaways:
            write_section_title(ws4, row, 1, "Key Takeaways", 5)
            row += 1
            for i, t in enumerate(takeaways):
                ws4.cell(row=row, column=1, value=f"• {t}").font = normal_font()
                ws4.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
                ws4.cell(row=row, column=1).fill = fill(LIGHT_GREY if i % 2 == 0 else WHITE)
                row += 1

        row += 1
        # Outliers
        outliers = bm.get("outliers", [])
        if outliers:
            write_section_title(ws4, row, 1, "Outlier Flags", 5)
            row += 1
            if isinstance(outliers, list) and outliers and isinstance(outliers[0], dict):
                headers = list(outliers[0].keys())
                write_header_row(ws4, row, headers, 1)
                row += 1
                for i, item in enumerate(outliers):
                    write_data_row(ws4, row, list(item.values()), shade=(i % 2 == 0))
                    row += 1

    for col, w in [(1, 30), (2, 20), (3, 20), (4, 20), (5, 20)]:
        set_col_width(ws4, col, w)

    # ══════════════════════════════════════════════════════════════
    # Sheet 5: SENSITIVITY TABLES
    # ══════════════════════════════════════════════════════════════
    ws5 = wb.create_sheet("Sensitivity Tables")
    ws5.sheet_view.showGridLines = False
    ws5.merge_cells("A1:E1")
    t5 = ws5["A1"]
    t5.value = "SENSITIVITY ANALYSIS — REVENUE | EBITDA | FCF"
    t5.font = Font(name="Calibri", bold=True, color=WHITE, size=14)
    t5.fill = fill(DARK_BLUE)
    t5.alignment = center()
    ws5.row_dimensions[1].height = 35

    fm = final_state.get("financial_model") or {}
    sens = fm.get("sensitivity_tables", {})
    row = 3

    sens_titles = {
        "revenue_vs_tariff_pct":    ("Revenue Sensitivity vs Tariff (%)", ["Scenario", "FY25", "FY26", "FY27"]),
        "ebitda_vs_fuel_cost_pct":  ("EBITDA Sensitivity vs Fuel Cost (%)", ["Scenario", "FY25", "FY26", "FY27"]),
        "fcf_vs_capex_pct":         ("FCF Sensitivity vs Capex (%)", ["Scenario", "FY25", "FY26", "FY27"]),
    }

    if sens and not fm.get("parse_error"):
        for key, (title, headers) in sens_titles.items():
            table = sens.get(key, {})
            write_section_title(ws5, row, 1, title, len(headers))
            row += 1
            write_header_row(ws5, row, headers, 1)
            row += 1
            if isinstance(table, dict):
                for i, (scenario, values) in enumerate(table.items()):
                    label = scenario.replace("_", " ").title()
                    if isinstance(values, dict):
                        data = [label] + [values.get(y, "-") for y in ["FY25", "FY26", "FY27"]]
                    else:
                        data = [label, str(values), "", ""]
                    write_data_row(ws5, row, data, shade=(i % 2 == 0))
                    row += 1
            row += 2
    else:
        ws5.cell(row=3, column=1, value="Run pipeline to populate sensitivity tables.").font = normal_font()

    for col, w in [(1, 30), (2, 20), (3, 20), (4, 20), (5, 20)]:
        set_col_width(ws5, col, w)

    # ══════════════════════════════════════════════════════════════
    # Sheet 6: DEBT SCHEDULE
    # ══════════════════════════════════════════════════════════════
    ws6 = wb.create_sheet("Debt Schedule")
    ws6.sheet_view.showGridLines = False
    ws6.merge_cells("A1:F1")
    t6 = ws6["A1"]
    t6.value = "DEBT SCHEDULE — MATURITY PROFILE & INTEREST"
    t6.font = Font(name="Calibri", bold=True, color=WHITE, size=14)
    t6.fill = fill(DARK_BLUE)
    t6.alignment = center()
    ws6.row_dimensions[1].height = 35

    debt = fm.get("debt_schedule", {})
    row = 3

    if debt and not fm.get("parse_error"):
        # Summary
        write_section_title(ws6, row, 1, "Debt Summary", 3)
        row += 1
        for label, key in [
            ("Total Debt FY25 (INR Cr)", "total_debt_fy25_cr"),
            ("Avg Cost of Debt (%)",     "avg_cost_of_debt_pct"),
        ]:
            write_data_row(ws6, row, [label, debt.get(key, "-")], shade=(row % 2 == 0))
            row += 1

        row += 1
        # Maturity profile
        maturity = debt.get("debt_maturity_profile", {})
        if maturity:
            write_section_title(ws6, row, 1, "Maturity Profile (INR Cr)", 3)
            row += 1
            write_header_row(ws6, row, ["Bucket", "Amount (INR Cr)"], 1)
            row += 1
            labels = {"within_1yr": "Within 1 Year", "1_3yr": "1–3 Years", "3_5yr": "3–5 Years", "beyond_5yr": "Beyond 5 Years"}
            for i, (k, v) in enumerate(maturity.items()):
                write_data_row(ws6, row, [labels.get(k, k), v], shade=(i % 2 == 0))
                row += 1

        row += 1
        # Annual repayment & interest schedule
        repay  = debt.get("annual_repayment_cr", {})
        intexp = debt.get("interest_expense_cr", {})
        if repay or intexp:
            years = ["FY25", "FY26", "FY27", "FY28", "FY29"]
            write_section_title(ws6, row, 1, "Annual Schedule (INR Cr)", 6)
            row += 1
            write_header_row(ws6, row, ["Item"] + years, 1)
            row += 1
            if repay:
                write_data_row(ws6, row, ["Annual Repayment"] + [repay.get(y, "-") for y in years], shade=True)
                row += 1
            if intexp:
                write_data_row(ws6, row, ["Interest Expense"] + [intexp.get(y, "-") for y in years])
                row += 1

        row += 1
        # Working Capital
        wc = fm.get("working_capital", {})
        if wc:
            write_section_title(ws6, row, 1, "Working Capital", 6)
            row += 1
            for label, key in [
                ("Debtor Days",   "debtor_days"),
                ("Creditor Days", "creditor_days"),
                ("Inventory Days","inventory_days"),
            ]:
                write_data_row(ws6, row, [label, wc.get(key, "-")], shade=(row % 2 == 0))
                row += 1
            nwc = wc.get("net_working_capital_cr", {})
            if nwc:
                years = ["FY25", "FY26", "FY27", "FY28", "FY29"]
                row += 1
                write_header_row(ws6, row, ["Net Working Capital (Cr)"] + years, 1)
                row += 1
                write_data_row(ws6, row, ["NWC"] + [nwc.get(y, "-") for y in years])
                row += 1
    else:
        ws6.cell(row=3, column=1, value="Run pipeline to populate debt schedule.").font = normal_font()

    for col, w in [(1, 30), (2, 18), (3, 18), (4, 18), (5, 18), (6, 18)]:
        set_col_width(ws6, col, w)

    # ══════════════════════════════════════════════════════════════
    # Sheet 7: CONSISTENCY REPORT
    # ══════════════════════════════════════════════════════════════
    ws7 = wb.create_sheet("Consistency Report")
    ws7.sheet_view.showGridLines = False

    ws7.merge_cells("A1:D1")
    t7 = ws7["A1"]
    t7.value = "CONSISTENCY REPORT — ASSEMBLY AGENT QC"
    t7.font = Font(name="Calibri", bold=True, color=WHITE, size=14)
    t7.fill = fill(DARK_BLUE)
    t7.alignment = center()
    ws7.row_dimensions[1].height = 35

    cr = final_state.get("consistency_report") or {}
    row = 3

    write_section_title(ws7, row, 1, "Overall Status", 3)
    row += 1
    status_val = cr.get("status", "N/A").upper()
    status_color = "00B050" if "PASS" in status_val else "FF0000"
    c = ws7.cell(row=row, column=1, value=f"Status: {status_val}")
    c.font = Font(name="Calibri", bold=True, color=status_color, size=12)
    ws7.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    row += 2

    issues = cr.get("issues", [])
    if issues:
        write_section_title(ws7, row, 1, f"Issues Found ({len(issues)})", 3)
        row += 1
        write_header_row(ws7, row, ["#", "Issue"], 1)
        ws7.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        row += 1
        for i, issue in enumerate(issues):
            txt = issue if isinstance(issue, str) else issue.get("description", str(issue))
            ws7.cell(row=row, column=1, value=i + 1).font = normal_font()
            c = ws7.cell(row=row, column=2, value=txt)
            c.font = normal_font()
            c.alignment = Alignment(wrap_text=True)
            ws7.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
            if i % 2 == 0:
                ws7.cell(row=row, column=1).fill = fill(LIGHT_GREY)
                ws7.cell(row=row, column=2).fill = fill(LIGHT_GREY)
            row += 1

    row += 1
    recs = cr.get("recommendations", [])
    if recs:
        write_section_title(ws7, row, 1, f"Recommendations ({len(recs)})", 3)
        row += 1
        write_header_row(ws7, row, ["#", "Recommendation"], 1)
        ws7.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        row += 1
        for i, rec in enumerate(recs):
            txt = rec if isinstance(rec, str) else str(rec)
            ws7.cell(row=row, column=1, value=i + 1).font = normal_font()
            c = ws7.cell(row=row, column=2, value=txt)
            c.font = normal_font()
            c.alignment = Alignment(wrap_text=True)
            ws7.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
            if i % 2 == 0:
                ws7.cell(row=row, column=1).fill = fill(LIGHT_GREY)
                ws7.cell(row=row, column=2).fill = fill(LIGHT_GREY)
            row += 1

    for col, w in [(1, 6), (2, 55), (3, 30)]:
        set_col_width(ws7, col, w)

    # ── Save workbook ──────────────────────────────────────────
    wb.save(output_path)
    print(f"\n  ✅ Excel saved → {output_path}")


def write_football_field_svg(final_state: dict, svg_path: str):
    """Generate a football field SVG chart from valuation data."""
    import os
    val = final_state.get("valuation") or {}
    ff  = val.get("football_field", {})

    bars = []
    for method, vals in ff.items():
        if isinstance(vals, dict):
            try:
                lo = float(str(vals.get("low_cr", vals.get("low", 0))).replace(",", ""))
                hi = float(str(vals.get("high_cr", vals.get("high", 0))).replace(",", ""))
                if lo > 0 and hi > 0:
                    bars.append((method.replace("_", " ").title(), lo, hi))
            except (ValueError, TypeError):
                pass

    if not bars:
        bars = [("DCF", 80000, 120000), ("SOTP", 60000, 90000),
                ("Trading Comps", 65000, 95000), ("Precedent Tx", 70000, 100000)]

    all_vals  = [v for _, lo, hi in bars for v in (lo, hi)]
    min_val   = min(all_vals) * 0.85
    max_val   = max(all_vals) * 1.10
    val_range = max_val - min_val or 1

    W, H         = 860, 420
    LEFT, RIGHT  = 220, 60
    TOP, BOT     = 70,  60
    bar_area_w   = W - LEFT - RIGHT
    n            = len(bars)
    bar_h        = min(36, (H - TOP - BOT) // max(n, 1) - 10)
    gap          = (H - TOP - BOT - n * bar_h) // (n + 1)
    colours      = ["#1F3864", "#2E75B6", "#70AD47", "#ED7D31", "#FFC000"]

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">',
        f'<rect width="{W}" height="{H}" fill="#F8F9FA" rx="8"/>',
        f'<text x="{W//2}" y="40" text-anchor="middle" font-family="Calibri,Arial" '
        f'font-size="16" font-weight="bold" fill="#1F3864">'
        f'{(final_state.get("deal_context") or {}).get("target_name","Company")} '
        f'— Football Field Valuation (INR Cr EV)</text>',
    ]

    for i, (label, lo, hi) in enumerate(bars):
        y     = TOP + gap + i * (bar_h + gap)
        x_lo  = LEFT + (lo - min_val) / val_range * bar_area_w
        x_hi  = LEFT + (hi - min_val) / val_range * bar_area_w
        bw    = max(x_hi - x_lo, 6)
        col   = colours[i % len(colours)]
        lines += [
            f'<rect x="{x_lo:.1f}" y="{y}" width="{bw:.1f}" height="{bar_h}" '
            f'fill="{col}" opacity="0.88" rx="4"/>',
            f'<text x="{LEFT - 10}" y="{y + bar_h//2 + 5}" text-anchor="end" '
            f'font-family="Calibri,Arial" font-size="12" fill="#333">{label}</text>',
            f'<text x="{x_lo - 5:.1f}" y="{y + bar_h//2 + 5}" text-anchor="end" '
            f'font-family="Calibri,Arial" font-size="10" fill="#555">{lo:,.0f}</text>',
            f'<text x="{x_hi + 5:.1f}" y="{y + bar_h//2 + 5}" text-anchor="start" '
            f'font-family="Calibri,Arial" font-size="10" fill="#555">{hi:,.0f}</text>',
        ]

    lines.append("</svg>")
    os.makedirs(os.path.dirname(svg_path), exist_ok=True)
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  ✅ Football field SVG → {svg_path}")


def write_zip_package(output_dir: str, excel_path: str, svg_path: str, final_state: dict):
    """Package all outputs into analyst_package.zip with a manifest."""
    import zipfile, json, os
    from datetime import datetime

    ctx       = final_state.get("deal_context") or {}
    safe_name = ctx.get("target_name", "Company").replace(" ", "_")
    zip_path  = os.path.join(output_dir, f"{safe_name}_AnalystPackage.zip")

    manifest = {
        "generated_at":   datetime.now().isoformat(),
        "company":        ctx.get("target_name", ""),
        "ticker":         ctx.get("target_ticker", ""),
        "transaction":    ctx.get("transaction_type", ""),
        "files": {
            "excel":         os.path.basename(excel_path),
            "football_field": os.path.basename(svg_path),
            "manifest":      "manifest.json",
        },
        "pipeline_status": {
            "qc_status":  (final_state.get("consistency_report") or {}).get("status", "N/A"),
            "issues":     len((final_state.get("consistency_report") or {}).get("issues", [])),
        }
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(excel_path):
            zf.write(excel_path, os.path.basename(excel_path))
        if os.path.exists(svg_path):
            zf.write(svg_path, os.path.basename(svg_path))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    print(f"  ✅ ZIP package  → {zip_path}")
    return zip_path


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    from datetime import datetime

    final_state, feedback = run_analyst_pipeline()

    output_dir = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    ctx        = final_state.get("deal_context") or {}
    safe_name  = ctx.get("target_name", "Company").replace(" ", "_")

    excel_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.xlsx")
    svg_path   = os.path.join(output_dir, f"{safe_name}_{timestamp}_football_field.svg")

    write_excel(final_state, feedback, excel_path)
    write_football_field_svg(final_state, svg_path)
    zip_path = write_zip_package(output_dir, excel_path, svg_path, final_state)

    cr = final_state.get("consistency_report") or {}
    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  Decision   : {feedback['decision'].upper()}")
    print(f"  QC Status  : {cr.get('status', 'N/A').upper()}")
    print(f"  Excel      : {excel_path}")
    print(f"  SVG Chart  : {svg_path}")
    print(f"  ZIP        : {zip_path}")
    print(f"{'='*60}")
