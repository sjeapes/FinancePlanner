"""
@file reports.py
@brief FastAPI routes for Phase 6 PDF report generation.

Endpoints:
  POST /api/reports/generate   — generate a PDF report (async background task)
  GET  /api/reports/status     — check report generation status
  GET  /api/reports/download   — download a generated report
  GET  /api/reports/presets    — list available report presets
  GET  /api/reports/sections   — list available sections
  GET  /api/reports/charts     — list available chart types
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.reports.report_engine import (
    ALL_CHARTS, ALL_SECTIONS, PRESETS,
    ReportConfig, ReportEngine, ReportResult, load_report_config,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory job store (production: use SQLite or Redis)
_JOBS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ReportRequest(BaseModel):
    """
    @brief Request body for POST /api/reports/generate.

    @param title           Report title.
    @param subtitle        Optional subtitle.
    @param prepared_for    Client name on cover page.
    @param scenario_path   Relative path to scenario YAML.
    @param preset          'quick' | 'full_annual' | 'ifa_pack'.
    @param sections        Optional explicit section list (overrides preset).
    @param charts          Optional explicit chart list (overrides preset).
    @param include_monte_carlo  True to include MC fan chart.
    @param mc_simulations  Number of MC simulations.
    @param paper_size      'A4' | 'letter'.
    @param watermark       None | 'CONFIDENTIAL' | 'DRAFT'.
    @param upload_to_drive True to upload to Google Drive.
    @param date_range_start  First year for charts.
    @param date_range_end    Last year for charts.
    """
    model_config = ConfigDict(from_attributes=True)

    title: str = "LifeLedger Financial Plan"
    subtitle: str = ""
    prepared_for: str = ""
    prepared_by: str = "LifeLedger"
    scenario_path: str = "data/scenarios/base.yaml"
    preset: str = Field(default="full_annual", pattern="^(quick|full_annual|ifa_pack)$")
    sections: list[str] = []
    charts: list[str] = []
    include_monte_carlo: bool = True
    mc_simulations: int = Field(default=500, ge=50, le=10000)
    paper_size: str = Field(default="A4", pattern="^(A4|letter)$")
    watermark: Optional[str] = None
    upload_to_drive: bool = False
    date_range_start: int = 2025
    date_range_end: int = 2075


class ReportJobResponse(BaseModel):
    """
    @brief Response for POST /api/reports/generate.

    @param job_id   UUID for the background job.
    @param status   'queued' | 'running' | 'complete' | 'failed'.
    @param message  Human-readable status message.
    """
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: str
    message: str


class ReportStatusResponse(BaseModel):
    """
    @brief Response for GET /api/reports/status/{job_id}.

    @param job_id          Job UUID.
    @param status          Current status.
    @param output_path     Path to generated PDF (set when complete).
    @param file_size_kb    PDF file size in kB.
    @param page_count      Number of pages.
    @param sections_built  Sections included.
    @param charts_built    Charts included.
    @param build_seconds   Build time.
    @param error           Error message if failed.
    @param download_url    API download URL.
    """
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: str
    output_path: Optional[str] = None
    file_size_kb: Optional[float] = None
    page_count: Optional[int] = None
    sections_built: list[str] = []
    charts_built: list[str] = []
    build_seconds: Optional[float] = None
    error: Optional[str] = None
    download_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


def _run_report(job_id: str, config: ReportConfig, project_root: str) -> None:
    """
    @brief Background task: build the PDF report and update job state.

    @param job_id       Unique job identifier.
    @param config       ReportConfig.
    @param project_root Absolute project root path.
    """
    _JOBS[job_id]["status"] = "running"
    _JOBS[job_id]["started_at"] = datetime.utcnow().isoformat()

    try:
        engine = ReportEngine(project_root=project_root)
        result = engine.build(config)
        _JOBS[job_id].update({
            "status":         "complete",
            "output_path":    result.output_path,
            "file_size_kb":   result.file_size_kb,
            "page_count":     result.page_count,
            "sections_built": result.sections_built,
            "charts_built":   result.charts_built,
            "build_seconds":  result.build_seconds,
            "warnings":       result.warnings,
        })
        logger.info("Report job %s complete: %s", job_id, result.output_path)
    except ImportError as exc:
        logger.error("Report job %s: reportlab not installed: %s", job_id, exc)
        _JOBS[job_id]["status"] = "failed"
        _JOBS[job_id]["error"]  = (
            "reportlab is not installed. Run: pip install reportlab>=4.1"
        )
    except Exception as exc:
        logger.error("Report job %s failed: %s", job_id, exc, exc_info=True)
        _JOBS[job_id]["status"] = "failed"
        _JOBS[job_id]["error"]  = str(exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/reports/generate", response_model=ReportJobResponse)
def generate_report(
    body: ReportRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> ReportJobResponse:
    """
    @brief Queue a PDF report generation job.

    The report is built asynchronously in a background task.
    Poll /api/reports/status/{job_id} to check progress.

    @param body              ReportRequest with report settings.
    @param background_tasks  FastAPI BackgroundTasks.
    @param request           FastAPI Request (for project_root).
    @return                  ReportJobResponse with job_id.
    """
    job_id = str(uuid.uuid4())
    root = getattr(request.app.state, "project_root", ".")

    config = ReportConfig(
        title=body.title,
        subtitle=body.subtitle,
        prepared_for=body.prepared_for,
        prepared_by=body.prepared_by,
        scenario_path=body.scenario_path,
        preset=body.preset,
        sections=body.sections,
        charts=body.charts,
        include_monte_carlo=body.include_monte_carlo,
        mc_simulations=body.mc_simulations,
        paper_size=body.paper_size,
        watermark=body.watermark,
        upload_to_drive=body.upload_to_drive,
        date_range_start=body.date_range_start,
        date_range_end=body.date_range_end,
    )

    _JOBS[job_id] = {
        "status":     "queued",
        "queued_at":  datetime.utcnow().isoformat(),
        "preset":     body.preset,
    }

    background_tasks.add_task(_run_report, job_id, config, root)
    logger.info("Report job %s queued: preset=%s", job_id, body.preset)

    return ReportJobResponse(
        job_id=job_id,
        status="queued",
        message=f"Report generation queued (preset: {body.preset}). "
                f"Poll /api/reports/status/{job_id} for progress.",
    )


@router.get("/reports/status/{job_id}", response_model=ReportStatusResponse)
def get_report_status(job_id: str, request: Request) -> ReportStatusResponse:
    """
    @brief Check the status of a report generation job.

    @param job_id   UUID returned by POST /api/reports/generate.
    @param request  FastAPI Request.
    @return         ReportStatusResponse with current status and metadata.
    @raises HTTPException 404 if job_id is not found.
    """
    if job_id not in _JOBS:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    j = _JOBS[job_id]
    download_url = None
    if j.get("status") == "complete" and j.get("output_path"):
        download_url = f"/api/reports/download/{job_id}"

    return ReportStatusResponse(
        job_id=job_id,
        status=j.get("status", "unknown"),
        output_path=j.get("output_path"),
        file_size_kb=j.get("file_size_kb"),
        page_count=j.get("page_count"),
        sections_built=j.get("sections_built", []),
        charts_built=j.get("charts_built", []),
        build_seconds=j.get("build_seconds"),
        error=j.get("error"),
        download_url=download_url,
    )


@router.get("/reports/download/{job_id}")
def download_report(job_id: str, request: Request):
    """
    @brief Download the generated PDF for a completed job.

    @param job_id   UUID of a completed report job.
    @param request  FastAPI Request.
    @return         FileResponse streaming the PDF.
    @raises HTTPException 404 if job not found or not complete.
    """
    if job_id not in _JOBS:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    j = _JOBS[job_id]
    if j.get("status") != "complete":
        raise HTTPException(
            status_code=409,
            detail=f"Report is not complete yet (status: {j.get('status')}).",
        )
    path = j.get("output_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report file not found on disk.")
    filename = os.path.basename(path)
    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/presets")
def list_presets() -> dict:
    """
    @brief List all available report presets and their default settings.

    @return  Dict mapping preset_id -> {sections, charts, include_monte_carlo}.
    """
    return {
        k: {
            "sections":            v["sections"],
            "charts":              v["charts"],
            "include_monte_carlo": v.get("include_monte_carlo", False),
            "estimated_pages": {
                "quick": "~4 pages",
                "full_annual": "~18 pages",
                "ifa_pack": "~28 pages",
            }.get(k, "varies"),
        }
        for k, v in PRESETS.items()
    }


@router.get("/reports/sections")
def list_sections() -> list[dict]:
    """
    @brief List all available report section identifiers with descriptions.

    @return  List of {id, label, description} dicts.
    """
    descriptions = {
        "cover_page":          "Cover page with title, date, and client details",
        "executive_summary":   "Net worth snapshot, FIRE status, key metrics table",
        "account_snapshots":   "Table of all accounts with current values and growth",
        "income_breakdown":    "Income sources with tax treatment and end dates",
        "future_assumptions":  "Inflation, growth rates, tax bands, and projection parameters",
        "projection_graphs":   "Embedded matplotlib charts (see /reports/charts for types)",
        "scenario_comparison": "Net worth at key ages across scenarios",
        "retirement_coverage": "Income vs expenses table for retirement years",
        "estate_summary":      "IHT liability, NRB/RNRB, gift tracker, reduction strategies",
    }
    return [
        {"id": s, "label": s.replace("_", " ").title(), "description": descriptions.get(s, "")}
        for s in ALL_SECTIONS
    ]


@router.get("/reports/charts")
def list_charts() -> list[dict]:
    """
    @brief List all available chart types with descriptions.

    @return  List of {id, label, description} dicts.
    """
    descriptions = {
        "net_worth_timeline":    "Stacked area chart of net worth components over time",
        "income_sources":        "Stacked bar chart of gross income by source",
        "monte_carlo_fan":       "P10–P90 confidence bands from Monte Carlo simulation",
        "account_growth":        "Individual account value lines over time",
        "expense_coverage":      "Retirement income vs expenses (surplus/shortfall fill)",
        "portfolio_mix":         "Doughnut chart of current portfolio allocation",
        "pension_projection":    "Pension fund values over the full lifecycle",
        "mortgage_amortisation": "Outstanding mortgage balance over time",
        "estate_waterfall":      "IHT waterfall: gross estate → deductions → net to beneficiaries",
        "healthcare_costs":      "Year-by-year healthcare cost projection by age phase",
        "macro_scenarios":       "Low / Mid / High deterministic scenario fan chart",
    }
    return [
        {"id": c, "label": c.replace("_", " ").title(), "description": descriptions.get(c, "")}
        for c in ALL_CHARTS
    ]
