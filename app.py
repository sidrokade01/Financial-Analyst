"""
IB Pitch Analyst System — Streamlit App
========================================
Run with:
  streamlit run app.py
"""

import os
import io
import tempfile
from datetime import datetime
from dotenv import load_dotenv

import streamlit as st

load_dotenv()

# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title="IB Pitch Analyst",
    page_icon="🏦",
    layout="wide",
)

st.markdown("""
<style>
  .main-header { font-size: 28px; font-weight: 800; color: #2A2356; }
  .sub-header  { font-size: 13px; color: #888; margin-top: -8px; }
  .section-title { font-size: 13px; font-weight: 700; color: #7C6FCD;
                   text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
  div[data-testid="stDownloadButton"] button {
    background: #1D6F42; color: white; font-weight: 700;
    border-radius: 8px; padding: 10px 24px; font-size: 15px;
    border: none; width: 100%;
  }
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────
st.markdown('<div class="main-header">🏦 IB Pitch Analyst System</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Goldman Sachs India IBD · Powered by Claude AI</div>', unsafe_allow_html=True)
st.divider()

# ── Layout ─────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

with left:
    st.markdown('<div class="section-title">📋 Company Details</div>', unsafe_allow_html=True)

    company = st.text_input("Company Name", placeholder="e.g. Tata Power Company Limited")
    ticker  = st.text_input("Ticker Symbol", placeholder="e.g. TATAPOWER.NS")

    sector = st.selectbox("Sector", [
        "Power / Utilities",
        "Oil & Gas / Conglomerate",
        "Banking & Financial Services",
        "IT Services",
        "FMCG",
        "Telecommunications",
    ])

    geography = st.selectbox("Geography", ["India", "USA", "UK", "Singapore", "UAE"])

    transaction_type = st.selectbox("Transaction Type", [
        ("Buy", "buy-side_advisory"),
        ("Sell", "sell-side_advisory"),
        ("IPO", "ipo"),
        ("Merger", "merger"),
        ("Acquisition", "acquisition"),
    ], format_func=lambda x: x[0])

    st.divider()
    st.markdown('<div class="section-title">🗂️ Business Segments</div>', unsafe_allow_html=True)

    preset_segments = [
        "Thermal Generation", "Renewable Energy", "Distribution",
        "EV Charging", "Solar Manufacturing",
    ]
    selected_segments = st.multiselect(
        "Select segments (choose one or more)",
        options=preset_segments,
        default=["Thermal Generation", "Renewable Energy"],
    )
    custom_seg = st.text_input("Add custom segment (optional)", placeholder="e.g. Green Hydrogen")
    if custom_seg and custom_seg not in selected_segments:
        selected_segments = selected_segments + [custom_seg]

    st.divider()
    st.markdown('<div class="section-title">📄 Upload Company PDF (Optional)</div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Quarterly Results / Annual Report / Investor Presentation",
        type=["pdf"],
        help="Upload a PDF to give Claude real financial data instead of estimates.",
    )

    pdf_text = ""
    if uploaded_file:
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(uploaded_file.read()))
            for page in reader.pages:
                pdf_text += page.extract_text() + "\n"
            pdf_text = pdf_text[:8000]
            st.success(f"✅ PDF loaded — {len(pdf_text):,} characters extracted")
        except Exception as e:
            st.error(f"Could not read PDF: {e}")

    run_clicked = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

# ── Right panel: results ────────────────────────────────────────
with right:
    st.markdown('<div class="section-title">⚙️ Pipeline Output</div>', unsafe_allow_html=True)

    if run_clicked:
        # Validate
        if not company:
            st.error("Please enter a company name.")
            st.stop()
        if not ticker:
            st.error("Please enter a ticker symbol.")
            st.stop()
        if not selected_segments:
            st.error("Please select at least one segment.")
            st.stop()

        # Build inputs
        inputs = {
            "company":          company,
            "ticker":           ticker,
            "sector":           sector,
            "geography":        geography,
            "transaction_type": transaction_type[1],
            "segments":         selected_segments,
            "pdf_text":         pdf_text,
        }

        # Run pipeline
        with st.status("Running analyst pipeline...", expanded=True) as status:
            try:
                st.write("🔄 Starting pipeline...")

                from state import AnalystState
                from runner import SubAgentRunner
                from pipeline import build_analyst_graph
                from human_gate import human_gate

                deal_context = {
                    "target_name":      inputs["company"],
                    "target_ticker":    inputs["ticker"],
                    "sector":           inputs["sector"],
                    "segments":         inputs["segments"],
                    "transaction_type": inputs["transaction_type"],
                    "listed":           True,
                    "geography":        inputs["geography"],
                    "pdf_data":         inputs["pdf_text"],
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

                runner   = SubAgentRunner()
                compiled = build_analyst_graph(runner)

                if compiled:
                    config      = {"configurable": {"thread_id": f"{company}-{datetime.now().isoformat()}"}}
                    final_state = compiled.invoke(initial_state, config)
                else:
                    import agents.data_sourcing     as ds
                    import agents.financial_modeler as fm
                    import agents.benchmarking      as bm
                    import agents.valuation         as val
                    import agents.assembly          as asm

                    state = dict(initial_state)

                    st.write("✅ [1/5] Data Sourcing...")
                    state.update(ds.run(state, runner))

                    st.write("✅ [2/5] Financial Modeler...")
                    state.update(fm.run(state, runner))

                    st.write("✅ [3/5] Benchmarking...")
                    state.update(bm.run(state, runner))

                    st.write("✅ [4/5] Valuation (Opus)...")
                    state.update(val.run(state, runner))

                    st.write("✅ [5/5] Assembly & QC...")
                    state.update(asm.run(state, runner))

                    final_state = state

                feedback = human_gate(
                    final_state.get("analyst_package", {}),
                    final_state.get("consistency_report", {}),
                )

                st.write("📊 Generating Excel report...")

                os.makedirs("outputs", exist_ok=True)
                safe_name  = company.replace(" ", "_").replace("/", "-")
                timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
                json_path  = f"outputs/{safe_name}_{timestamp}.json"

                from main import write_json
                write_json(final_state, feedback, json_path)

                total_cost = runner.get_total_cost()
                status.update(label="✅ Analysis Complete!", state="complete")

                # Store results in session state
                st.session_state["json_path"]  = json_path
                st.session_state["total_cost"] = total_cost
                st.session_state["company"]    = company
                st.session_state["feedback"]   = feedback
                st.session_state["final_state"] = final_state

            except Exception as e:
                status.update(label="❌ Pipeline failed", state="error")
                st.error(f"Error: {e}")
                st.stop()

    # ── Show result if available ────────────────────────────────
    if "json_path" in st.session_state:
        json_path   = st.session_state["json_path"]
        total_cost  = st.session_state["total_cost"]
        company_out = st.session_state["company"]
        feedback    = st.session_state["feedback"]
        final_state = st.session_state["final_state"]

        st.success(f"✅ **{company_out}** — analysis complete!")

        cr = (final_state.get("consistency_report") or {})
        col1, col2, col3 = st.columns(3)
        col1.metric("Decision",   feedback.get("decision", "N/A").upper())
        col2.metric("QC Status",  cr.get("status", "N/A").upper())
        col3.metric("Total Cost", f"${total_cost:.4f}")

        st.divider()

        with open(json_path, "rb") as f:
            st.download_button(
                label="📥 Download JSON Report",
                data=f.read(),
                file_name=os.path.basename(json_path),
                mime="application/json",
                use_container_width=True,
            )
    else:
        st.info("Fill in the company details on the left and click **Run Analysis**.")
