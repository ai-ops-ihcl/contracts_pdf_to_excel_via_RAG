"""
IHCL Contract Pipeline — FastAPI Application
==============================================
Production API for triggering and monitoring the contract extraction pipeline.

Endpoints:
    GET  /health            → Health check (API + Qdrant)
    POST /pipeline/run      → Trigger pipeline (background)
    POST /pipeline/upload   → Upload PDF + optionally trigger
    GET  /pipeline/status   → Current run status
    GET  /pipeline/history  → Past run summaries
    GET  /pipeline/download → Download latest Excel
    POST /pipeline/reset    → Reset tracker (reprocess all)

Start:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

# ============================================
# Real Module Imports
# ============================================
from app.config import (
    INPUT_PDF_DIR, OUTPUT_EXCEL_DIR, LOG_DIR,
    QDRANT_HOST, QDRANT_PORT, QDRANT_URL,
    QDRANT_COLLECTION, APP_NAME,
)
from app.pipeline.orchestrator import PipelineOrchestrator
from app.utils.tracker import FileTracker

# Ensure directories exist
for d in [INPUT_PDF_DIR, OUTPUT_EXCEL_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================
# App Initialization
# ============================================
app = FastAPI(
    title="IHCL Contract Pipeline API",
    description="Automated extraction of structured attributes from IHCL hotel contract PDFs.",
    version="1.0.0",
    docs_url="/docs",       # Swagger UI
    redoc_url="/redoc",     # ReDoc
)

# ============================================
# Global State — Pipeline Lock & Run History
# ============================================
pipeline_lock = threading.Lock()
current_run: Optional[dict] = None
run_history: list[dict] = []


# ============================================
# HELPER: Run pipeline in background
# ============================================
def _run_pipeline_background(mode: str = "incremental"):
    """Execute pipeline in a background thread with lock protection."""
    global current_run

    if not pipeline_lock.acquire(blocking=False):
        return  # Already running — silently skip

    try:
        # Initialize orchestrator with config module
        import app.config as config
        orchestrator = PipelineOrchestrator(config)

        # Run the pipeline
        result = orchestrator.run(mode=mode)

        # Update current_run with result
        current_run = result

        # Save to history
        run_history.append(current_run.copy())

    except Exception as e:
        current_run = {
            "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "status": "FAILED",
            "mode": mode,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        run_history.append(current_run.copy())
    finally:
        pipeline_lock.release()


# ============================================
# ENDPOINT: Health Check
# ============================================
@app.get("/health", tags=["System"])
def health_check():
    """
    Check API health and Qdrant connectivity.
    """
    qdrant_status = "unknown"
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        client.get_collections()
        qdrant_status = "healthy"
    except Exception as e:
        qdrant_status = f"unhealthy: {str(e)[:50]}"

    # Count files
    input_pdfs = len(list(INPUT_PDF_DIR.glob("*.pdf")))
    output_files = len(list(OUTPUT_EXCEL_DIR.glob("*.xlsx")))

    return {
        "status": "healthy",
        "service": APP_NAME,
        "qdrant": qdrant_status,
        "input_pdfs_pending": input_pdfs,
        "output_excels": output_files,
        "pipeline_running": pipeline_lock.locked(),
        "timestamp": datetime.now().isoformat(),
    }


# ============================================
# ENDPOINT: Trigger Pipeline
# ============================================
@app.post("/pipeline/run", tags=["Pipeline"])
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    mode: str = "incremental",
):
    """
    Trigger the pipeline in background.

    Args:
        mode: "incremental" (only new files) or "full" (reprocess all)
    
    Returns:
        Acknowledgement with status.
    """
    if mode not in ("incremental", "full"):
        raise HTTPException(status_code=400, detail="mode must be 'incremental' or 'full'")

    if pipeline_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Pipeline is already running. Check /pipeline/status for progress.",
        )

    # Count pending files
    pending = len(list(INPUT_PDF_DIR.glob("*.pdf")))
    if pending == 0 and mode == "incremental":
        return {
            "message": "No new PDF files found in input directory.",
            "input_dir": str(INPUT_PDF_DIR),
            "action": "Upload PDFs first via /pipeline/upload",
        }

    background_tasks.add_task(_run_pipeline_background, mode)

    return {
        "message": f"Pipeline triggered in {mode} mode.",
        "pending_files": pending,
        "status_url": "/pipeline/status",
    }


# ============================================
# ENDPOINT: Upload PDF
# ============================================
@app.post("/pipeline/upload", tags=["Pipeline"])
async def upload_pdf(
    file: UploadFile = File(...),
    auto_run: bool = False,
    background_tasks: BackgroundTasks = None,
):
    """
    Upload a contract PDF to the input directory.

    Args:
        file: PDF file to upload
        auto_run: If True, trigger pipeline immediately after upload
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Save file
    dest = INPUT_PDF_DIR / file.filename
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    response = {
        "message": f"Uploaded: {file.filename}",
        "size_bytes": len(content),
        "saved_to": str(dest),
    }

    # Optionally trigger pipeline
    if auto_run and background_tasks:
        if not pipeline_lock.locked():
            background_tasks.add_task(_run_pipeline_background, "incremental")
            response["pipeline"] = "Triggered automatically"
        else:
            response["pipeline"] = "Already running — will process in next run"

    return response


# ============================================
# ENDPOINT: Pipeline Status
# ============================================
@app.get("/pipeline/status", tags=["Pipeline"])
def pipeline_status():
    """
    Get current pipeline run status.
    """
    if current_run and pipeline_lock.locked():
        return {
            "running": True,
            "current_run": current_run,
        }
    elif current_run:
        return {
            "running": False,
            "last_run": current_run,
        }
    else:
        return {
            "running": False,
            "message": "No pipeline runs yet.",
        }


# ============================================
# ENDPOINT: Run History
# ============================================
@app.get("/pipeline/history", tags=["Pipeline"])
def pipeline_history(limit: int = 10):
    """
    Get past pipeline run summaries.
    """
    return {
        "total_runs": len(run_history),
        "runs": run_history[-limit:][::-1],  # Latest first
    }


# ============================================
# ENDPOINT: Download Latest Excel
# ============================================
@app.get("/pipeline/download", tags=["Output"])
def download_latest_excel():
    """
    Download the most recent Excel output file.
    """
    excel_files = sorted(OUTPUT_EXCEL_DIR.glob("*.xlsx"), reverse=True)

    if not excel_files:
        raise HTTPException(status_code=404, detail="No Excel output files found. Run the pipeline first.")

    latest = excel_files[0]
    return FileResponse(
        path=str(latest),
        filename=latest.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ============================================
# ENDPOINT: List Output Files
# ============================================
@app.get("/pipeline/outputs", tags=["Output"])
def list_outputs():
    """
    List all Excel output files.
    """
    excel_files = sorted(OUTPUT_EXCEL_DIR.glob("*.xlsx"), reverse=True)
    return {
        "total": len(excel_files),
        "files": [
            {
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat(),
            }
            for f in excel_files
        ],
    }


# ============================================
# ENDPOINT: Reset Tracker
# ============================================
@app.post("/pipeline/reset", tags=["Admin"])
def reset_tracker():
    """
    Reset the file tracker. Next run will reprocess ALL files.
    ⚠️ Use with caution.
    """
    tracker_path = LOG_DIR / "processed_files.json"
    if tracker_path.exists():
        tracker_path.unlink()
    return {"message": "Tracker reset. Next run will process all files."}


# ============================================
# ROOT
# ============================================
@app.get("/", tags=["System"])
def root():
    return {
        "service": APP_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }