"""
api.py
=====================================================
HOW TO RUN LOCALLY
    pip install fastapi uvicorn --break-system-packages
    uvicorn api:app --reload --port 8000

Then test with:
    GET http://localhost:8000/api/rfp/analyze/RFP-2026-001

=====================================================
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from rfp_core import extract_text_headless, analyze_rfp_headless
from rfp_json_formatter import report_to_json

# =====================================================
# CONFIG
# =====================================================

BASE_DIR = Path(__file__).parent
DOCUMENTS_DIR = BASE_DIR / "rfp_documents"   # <rfp_id>/*.pdf lives here
CACHE_DIR = BASE_DIR / "rfp_api_cache"       # cached JSON results per rfp_id
RESULTS_DB = BASE_DIR / "rfp_results.db"       # results saved by the Streamlit app
CACHE_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="AI Proposal Capture System — JSON API",
    description="Given an rfp_id and returns structured JSON.",
    version="1.0.0",
)


# =====================================================
# HELPERS
# =====================================================


def _rfp_folder(rfp_id: str) -> Path:
    return DOCUMENTS_DIR / rfp_id


def _cache_path(rfp_id: str) -> Path:
    return CACHE_DIR / f"{rfp_id}.json"


def _load_cached(rfp_id: str):
    path = _cache_path(rfp_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(rfp_id: str, payload: dict):
    try:
        with open(_cache_path(rfp_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # caching is a nice-to-have, never fail the request over it


def _load_streamlit_result(rfp_id: str):
    """Return an analysis already saved by app.py, if one exists.

    The Streamlit app writes its final structured result to rfp_results.db
    under the RFP ID displayed on screen. Reading it here makes that ID work
    in the JSON API without requiring the uploaded PDFs to be copied into a
    separate rfp_documents folder.
    """
    if not RESULTS_DB.exists():
        return None
    try:
        with sqlite3.connect(RESULTS_DB) as conn:
            row = conn.execute(
                "SELECT payload FROM rfp_results WHERE rfp_id = ?", (rfp_id,)
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        if not isinstance(payload, dict) or "result" not in payload:
            return None
        payload["rfp_id"] = rfp_id
        payload["cached"] = True
        return payload
    except (sqlite3.Error, json.JSONDecodeError, TypeError, KeyError):
        return None


# =====================================================
# MAIN ENDPOINT
# =====================================================


@app.get("/api/rfp/analyze/{rfp_id}")
def analyze_rfp_by_id(rfp_id: str, force_refresh: bool = False):
    """
    Main endpoint for retrieving a structured RFP analysis.

    - rfp_id: the RFP's identifier — must match a folder name under
      ./rfp_documents/{rfp_id}/ containing that RFP's PDF file(s).
    - force_refresh: pass ?force_refresh=true to bypass the cache and
      re-run the full analysis even if a cached result already exists.
    """
    # First serve the exact result already produced in the Streamlit UI.
    # This is the normal path for the RFP ID shown by app.py.
    if not force_refresh:
        saved_result = _load_streamlit_result(rfp_id)
        if saved_result:
            return JSONResponse(content=saved_result)

    # If no Streamlit result exists, the standalone API can still analyze
    # PDFs placed in rfp_documents/<rfp_id>/.
    folder = _rfp_folder(rfp_id)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"No documents found for rfp_id='{rfp_id}'. "
                    f"Expected folder: rfp_documents/{rfp_id}/",
        )

    pdf_paths = sorted(folder.glob("*.pdf"))
    if not pdf_paths:
        raise HTTPException(
            status_code=404,
            detail=f"Folder rfp_documents/{rfp_id}/ exists but contains no PDF files.",
        )

    if not force_refresh:
        cached = _load_cached(rfp_id)
        if cached:
            cached["cached"] = True
            return JSONResponse(content=cached)

    try:
        document_text = extract_text_headless(pdf_paths)
        raw_report = analyze_rfp_headless(document_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    structured = report_to_json(raw_report)

    payload = {
        "rfp_id": rfp_id,
        "source_documents": [p.name for p in pdf_paths],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "result": structured,
    }

    _save_cache(rfp_id, payload)

    return JSONResponse(content=payload)


@app.get("/api/rfp/status/{rfp_id}")
def rfp_status(rfp_id: str):
    """Quick check: does this rfp_id exist, and has it already been analyzed?"""
    folder = _rfp_folder(rfp_id)
    saved_in_app = _load_streamlit_result(rfp_id) is not None
    return {
        "rfp_id": rfp_id,
        "documents_found": folder.exists() and any(folder.glob("*.pdf")),
        "saved_by_streamlit": saved_in_app,
        "already_cached": saved_in_app or _cache_path(rfp_id).exists(),
    }


@app.get("/")
def root():
    return {
        "service": "AI Proposal Capture System — JSON API",
        "usage": "GET /api/rfp/analyze/{rfp_id}",
        "docs": "/docs",
    }