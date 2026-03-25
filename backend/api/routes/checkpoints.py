"""
@file checkpoints.py
@brief FastAPI routes for checkpoint management.

Checkpoints are stored as YAML files in data/checkpoints/YYYY-MM-DD_audit.yaml.
They record actual net worth snapshots used to anchor the historical boundary
of projections.

Endpoints:
  GET    /api/checkpoints              — list all checkpoint files
  POST   /api/checkpoints              — create a new checkpoint
  GET    /api/checkpoints/{id}         — get a specific checkpoint
  DELETE /api/checkpoints/{id}         — delete a checkpoint
  GET    /api/checkpoints/{id}/divergence?scenario=base — divergence vs projected
"""

import logging
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from backend.engine.calculator import ProjectionEngine
from backend.models.models import Checkpoint
from backend.models.pydantic_models import CheckpointModel
from backend.persistence.yaml_serialiser import (
    dump_yaml,
    load_scenario_from_file,
    load_yaml,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────

class CheckpointListItem(BaseModel):
    """
    @brief Summary item for checkpoint list.
    @param id Checkpoint identifier.
    @param filename YAML file name.
    @param date Checkpoint date.
    @param total_net_worth Total net worth at checkpoint.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    date: date
    total_net_worth: float


class DivergenceResponse(BaseModel):
    """
    @brief Divergence analysis between a checkpoint and projected values.
    @param checkpoint_id Checkpoint identifier.
    @param checkpoint_date Date of the checkpoint.
    @param actual_net_worth Actual net worth at checkpoint date.
    @param projected_net_worth Projected net worth for that year.
    @param divergence_abs Absolute difference (actual - projected).
    @param divergence_pct Percentage difference (divergence / projected * 100).
    @param account_divergences Per-account divergence dict.
    """
    model_config = ConfigDict(from_attributes=True)

    checkpoint_id: str
    checkpoint_date: date
    actual_net_worth: float
    projected_net_worth: float
    divergence_abs: float
    divergence_pct: float
    account_divergences: dict[str, float] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _checkpoints_dir(request: Request) -> str:
    """
    @brief Return the absolute path to the checkpoints directory.
    @param request FastAPI Request with app.state.project_root.
    @return Absolute path string.
    """
    root = getattr(request.app.state, "project_root", ".")
    return os.path.join(root, "data", "checkpoints")


def _checkpoint_filename(checkpoint_id: str) -> str:
    """
    @brief Construct a checkpoint filename from its id.
    @param checkpoint_id Checkpoint identifier (should be a date string like '2024-03-01').
    @return Filename string (e.g. '2024-03-01_audit.yaml').
    """
    return f"{checkpoint_id}_audit.yaml"


def _checkpoint_path(request: Request, checkpoint_id: str) -> str:
    """
    @brief Full absolute path to a checkpoint file.
    @param request FastAPI Request.
    @param checkpoint_id Checkpoint identifier.
    @return Absolute path string.
    """
    return os.path.join(_checkpoints_dir(request), _checkpoint_filename(checkpoint_id))


def _parse_checkpoint(data: dict, filename: str) -> Optional[Checkpoint]:
    """
    @brief Parse a checkpoint YAML dict into a Checkpoint dataclass.
    @param data Raw YAML dict.
    @param filename Source filename for error logging.
    @return Checkpoint dataclass or None on failure.
    """
    try:
        cp_data = data.get("checkpoint", data)
        from backend.persistence.yaml_serialiser import _parse_date, _float

        return Checkpoint(
            id=str(cp_data.get("id", filename.replace("_audit.yaml", ""))),
            date=_parse_date(cp_data.get("date")) or date.today(),
            total_net_worth=_float(cp_data.get("total_net_worth", 0.0)),
            account_values=cp_data.get("account_values", {}),
            notes=str(cp_data.get("notes", "")),
        )
    except Exception as exc:
        logger.error("_parse_checkpoint: error for %s: %s", filename, exc)
        return None


# ── Route handlers ────────────────────────────────────────────────────────────

@router.get("/checkpoints", response_model=list[CheckpointListItem])
def list_checkpoints(request: Request) -> list[CheckpointListItem]:
    """
    @brief List all checkpoint YAML files in data/checkpoints/.
    @param request FastAPI Request.
    @return List of CheckpointListItem summaries, sorted by date descending.
    """
    try:
        cp_dir = _checkpoints_dir(request)
        if not os.path.isdir(cp_dir):
            return []

        results = []
        for filename in sorted(os.listdir(cp_dir), reverse=True):
            if not filename.endswith("_audit.yaml"):
                continue
            path = os.path.join(cp_dir, filename)
            try:
                data = load_yaml(path)
                cp = _parse_checkpoint(data, filename)
                if cp:
                    results.append(CheckpointListItem(
                        id=cp.id,
                        filename=filename,
                        date=cp.date,
                        total_net_worth=cp.total_net_worth,
                    ))
            except Exception as fe:
                logger.warning("list_checkpoints: could not read %s: %s", filename, fe)
                continue

        return results
    except Exception as exc:
        logger.error("list_checkpoints: error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "List error", "detail": str(exc)})


@router.post("/checkpoints", response_model=CheckpointModel, status_code=201)
def create_checkpoint(body: CheckpointModel, request: Request) -> CheckpointModel:
    """
    @brief Create a new checkpoint YAML file.

    The file is saved as data/checkpoints/{id}_audit.yaml.

    @param body CheckpointModel with id, date, total_net_worth, and optional account_values.
    @param request FastAPI Request.
    @return The created CheckpointModel.
    """
    cp_dir = _checkpoints_dir(request)
    path = _checkpoint_path(request, body.id)

    if os.path.exists(path):
        raise HTTPException(
            status_code=409,
            detail=f"Checkpoint '{body.id}' already exists",
        )

    try:
        os.makedirs(cp_dir, exist_ok=True)
        data = {
            "checkpoint": {
                "id": body.id,
                "date": body.date.isoformat(),
                "total_net_worth": body.total_net_worth,
                "account_values": body.account_values,
                "notes": body.notes,
            }
        }
        ok = dump_yaml(data, path)
        if not ok:
            raise HTTPException(
                status_code=500,
                detail={"error": "Write error", "detail": "Could not save checkpoint"},
            )
        logger.info("create_checkpoint: saved %s", path)
        return body
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("create_checkpoint: error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Create error", "detail": str(exc)})


@router.get("/checkpoints/{checkpoint_id}", response_model=CheckpointModel)
def get_checkpoint(checkpoint_id: str, request: Request) -> CheckpointModel:
    """
    @brief Retrieve a specific checkpoint by its id.
    @param checkpoint_id Checkpoint identifier.
    @param request FastAPI Request.
    @return CheckpointModel.
    """
    path = _checkpoint_path(request, checkpoint_id)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Checkpoint not found: {checkpoint_id}")

    try:
        data = load_yaml(path)
        cp = _parse_checkpoint(data, _checkpoint_filename(checkpoint_id))
        if cp is None:
            raise HTTPException(status_code=422, detail=f"Could not parse checkpoint: {checkpoint_id}")
        return CheckpointModel.from_dataclass(cp)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_checkpoint: error for %s: %s", checkpoint_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Load error", "detail": str(exc)})


@router.delete("/checkpoints/{checkpoint_id}", status_code=204)
def delete_checkpoint(checkpoint_id: str, request: Request) -> None:
    """
    @brief Delete a checkpoint YAML file.
    @param checkpoint_id Checkpoint identifier.
    @param request FastAPI Request.
    """
    path = _checkpoint_path(request, checkpoint_id)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Checkpoint not found: {checkpoint_id}")

    try:
        os.remove(path)
        logger.info("delete_checkpoint: removed %s", path)
    except Exception as exc:
        logger.error("delete_checkpoint: error for %s: %s", checkpoint_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Delete error", "detail": str(exc)})


@router.get("/checkpoints/{checkpoint_id}/divergence", response_model=DivergenceResponse)
def checkpoint_divergence(
    checkpoint_id: str,
    request: Request,
    scenario: str = Query(default="base", description="Scenario name to compare against"),
) -> DivergenceResponse:
    """
    @brief Compare a checkpoint's actual values against the projected values for that year.

    Runs the projection engine on the specified scenario and looks up the year
    matching the checkpoint date.

    @param checkpoint_id Checkpoint identifier.
    @param request FastAPI Request.
    @param scenario Scenario name to project (default: 'base').
    @return DivergenceResponse with actual vs projected breakdown.
    """
    path = _checkpoint_path(request, checkpoint_id)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Checkpoint not found: {checkpoint_id}")

    try:
        data = load_yaml(path)
        cp = _parse_checkpoint(data, _checkpoint_filename(checkpoint_id))
        if cp is None:
            raise HTTPException(status_code=422, detail="Could not parse checkpoint")

        # Load and project the scenario
        root = getattr(request.app.state, "project_root", ".")
        sc_path = os.path.join(root, "data", "scenarios", f"{scenario}.yaml")
        if not os.path.isfile(sc_path):
            raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario}")

        sc = load_scenario_from_file(sc_path)
        if sc is None:
            raise HTTPException(status_code=422, detail=f"Could not parse scenario: {scenario}")

        config = request.app.state.config
        tax_profiles = request.app.state.tax_profiles
        engine = ProjectionEngine(config, tax_profiles)
        result = engine.project(sc)

        checkpoint_year = cp.date.year
        year_snap = result.year(checkpoint_year)
        projected_nw = year_snap.total_net_worth if year_snap else 0.0
        actual_nw = cp.total_net_worth

        divergence_abs = actual_nw - projected_nw
        divergence_pct = (divergence_abs / projected_nw * 100) if projected_nw != 0 else 0.0

        # Per-account divergence
        account_divergences: dict[str, float] = {}
        if year_snap:
            for account_id, actual_val in cp.account_values.items():
                snap = year_snap.accounts.get(account_id)
                projected_val = snap.value if snap else 0.0
                account_divergences[account_id] = actual_val - projected_val

        return DivergenceResponse(
            checkpoint_id=cp.id,
            checkpoint_date=cp.date,
            actual_net_worth=actual_nw,
            projected_net_worth=projected_nw,
            divergence_abs=divergence_abs,
            divergence_pct=divergence_pct,
            account_divergences=account_divergences,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "checkpoint_divergence: error for %s: %s", checkpoint_id, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "Divergence calculation error", "detail": str(exc)},
        )
