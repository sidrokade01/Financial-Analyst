"""
IB Pitch Analyst System — FastAPI Multi-User Server
====================================================
Run with:
  pip install fastapi uvicorn
  python app.py

Access at: http://localhost:8000
Share IP with team: http://YOUR_IP:8000
"""

import os
import sys
import uuid
import json
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# ─────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────
app = FastAPI(title="IB Pitch Analyst System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# ─────────────────────────────────────────────────────────────
# In-memory job store (per user session)
# ─────────────────────────────────────────────────────────────
jobs: dict = {}  # job_id → job info


# ─────────────────────────────────────────────────────────────
# Request model
# ─────────────────────────────────────────────────────────────
class AnalysisRequest(BaseModel):
    company_name: str
    ticker: str
    sector: str
    geography: str
    transaction_type: str
    segments: list[str]


# ─────────────────────────────────────────────────────────────
# Pipeline runner (runs in background thread)
# ─────────────────────────────────────────────────────────────
def run_pipeline_thread(job_id: str, req: AnalysisRequest):
    """Runs the analyst pipeline in a background thread."""
    try:
        from dotenv import load_dotenv
        load_dotenv()

        from state import AnalystState
        from runner import SubAgentRunner
        from pipeline import build_analyst_graph
        from human_gate import human_gate

        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = []

        def log(msg: str):
            jobs[job_id]["progress"].append(msg)
            print(f"[{job_id[:8]}] {msg}")

        log("🔄 Starting pipeline...")

        deal_context = {
            "target_name":       req.company_name,
            "target_ticker":     req.ticker,
            "sector":            req.sector,
            "segments":          req.segments,
            "transaction_type":  req.transaction_type,
            "listed":            True,
            "geography":         req.geography,
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

        log("✅ [1/5] Data Sourcing — running...")
        if compiled:
            config      = {"configurable": {"thread_id": job_id}}
            final_state = compiled.invoke(initial_state, config)
        else:
            import agents.data_sourcing     as ds
            import agents.financial_modeler as fm
            import agents.benchmarking      as bm
            import agents.valuation         as val
            import agents.assembly          as asm

            state = dict(initial_state)
            state.update(ds.run(state, runner));  log("✅ [1/5] Data Sourcing — done")
            state.update(fm.run(state, runner));  log("✅ [2/5] Financial Model — done")
            state.update(bm.run(state, runner));  log("✅ [3/5] Benchmarking — done")
            state.update(val.run(state, runner)); log("✅ [4/5] Valuation — done")
            state.update(asm.run(state, runner)); log("✅ [5/5] Assembly QC — done")
            final_state = state

        feedback = human_gate(
            final_state.get("analyst_package", {}),
            final_state.get("consistency_report", {}),
        )

        # Write outputs
        log("📊 Writing Excel output...")
        os.makedirs("outputs", exist_ok=True)
        safe_name  = req.company_name.replace(" ", "_").replace("/", "-")
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = f"outputs/{safe_name}_{timestamp}.xlsx"
        svg_path   = f"outputs/{safe_name}_{timestamp}_football_field.svg"

        from main import write_excel, write_football_field_svg, write_zip_package
        write_excel(final_state, feedback, excel_path)
        log("📊 Writing Football Field SVG...")
        write_football_field_svg(final_state, svg_path)
        log("📦 Creating ZIP package...")
        zip_path = write_zip_package("outputs", excel_path, svg_path, final_state)

        total_cost = runner.get_total_cost()
        log(f"💰 Total cost: ${total_cost:.4f}")
        log(f"✅ Done! All outputs ready.")

        jobs[job_id].update({
            "status":     "done",
            "excel_path": excel_path,
            "svg_path":   svg_path,
            "zip_path":   zip_path,
            "cost":       round(total_cost, 4),
            "decision":   feedback.get("decision", "N/A"),
            "qc_status":  (final_state.get("consistency_report") or {}).get("status", "N/A"),
        })

    except Exception as e:
        jobs[job_id]["status"]  = "error"
        jobs[job_id]["error"]   = str(e)
        jobs[job_id]["progress"].append(f"❌ Error: {e}")
        print(f"Pipeline error [{job_id[:8]}]: {e}")


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home():
    html_path = Path("static/index.html")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/api/run")
async def run_analysis(req: AnalysisRequest):
    """Start a new analysis job."""
    if not req.company_name or not req.ticker or not req.segments:
        return {"error": "Company name, ticker and at least one segment are required."}

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id":     job_id,
        "status":     "queued",
        "progress":   [],
        "excel_path": None,
        "cost":       None,
        "company":    req.company_name,
        "created_at": datetime.now().isoformat(),
    }

    thread = threading.Thread(
        target=run_pipeline_thread,
        args=(job_id, req),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Poll job status and progress logs."""
    job = jobs.get(job_id)
    if not job:
        return {"error": "Job not found"}
    return job


@app.get("/api/download/{job_id}")
async def download_excel(job_id: str):
    """Download the Excel file for a completed job."""
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return {"error": "Job not complete"}

    path = job["excel_path"]
    if not path or not os.path.exists(path):
        return {"error": "File not found"}

    filename = os.path.basename(path)
    return FileResponse(
        path=path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@app.get("/api/download/svg/{job_id}")
async def download_svg(job_id: str):
    """Download the Football Field SVG chart for a completed job."""
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return {"error": "Job not complete"}

    path = job.get("svg_path")
    if not path or not os.path.exists(path):
        return {"error": "SVG file not found"}

    filename = os.path.basename(path)
    return FileResponse(
        path=path,
        media_type="image/svg+xml",
        filename=filename,
    )


@app.get("/api/download/zip/{job_id}")
async def download_zip(job_id: str):
    """Download the full ZIP analyst package for a completed job."""
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return {"error": "Job not complete"}

    path = job.get("zip_path")
    if not path or not os.path.exists(path):
        return {"error": "ZIP file not found"}

    filename = os.path.basename(path)
    return FileResponse(
        path=path,
        media_type="application/zip",
        filename=filename,
    )


@app.get("/api/jobs")
async def list_jobs():
    """List all jobs (admin view)."""
    return list(jobs.values())


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  IB Pitch Analyst System — Multi-User Server")
    print("="*60)
    print("  Local  : http://localhost:8000")
    print("  Network: http://YOUR_IP:8000")
    print("="*60 + "\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
