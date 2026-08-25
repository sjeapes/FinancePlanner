"""
@file insights.py (routes)
@brief FastAPI routes for Phase 12 MC insights and annual review.

GET /api/insights/mc
    Generate prioritised insights from Monte Carlo results without re-running.

POST /api/insights/snapshot
    Save current simulation state as a review baseline.

GET /api/insights/snapshots
    List saved review snapshots for a scenario.

POST /api/insights/review
    Generate an annual review narrative comparing current state to a snapshot.
"""
import logging, os
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from backend.engine.insight_engine import (
    generate_mc_insights, save_review_snapshot, load_review_snapshots,
    generate_annual_review, MCInsight,
)
from backend.persistence.yaml_serialiser import load_yaml

logger = logging.getLogger(__name__)
router = APIRouter()


class MCInsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    category:str; priority:str; title:str; detail:str
    action:str; impact:str; colour:str; icon:str

class MCInsightResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scenario_path:str; prob_fire:float; n_simulations:int
    insights:list[MCInsightOut]; overall_health:str; summary:str; warnings:list[str]

class SnapshotRequest(BaseModel):
    scenario_path:str="data/scenarios/base.yaml"
    net_worth:float=0; fire_year:Optional[int]=None
    pension_value:float=0; isa_value:float=0; savings_value:float=0
    annual_spending:float=0; prob_fire:float=0

class ReviewRequest(BaseModel):
    scenario_path:str="data/scenarios/base.yaml"
    baseline_id:str
    net_worth:float=0; fire_year:Optional[int]=None
    pension_value:float=0; isa_value:float=0; savings_value:float=0
    annual_spending:float=0; prob_fire:float=0

class ReviewMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    label:str; current:float; previous:float; delta:float
    delta_pct:float; unit:str; better:bool

class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    review_date:str; baseline_date:str; period_label:str
    metrics:list[ReviewMetricOut]; narrative:str; headline:str
    fire_delta_months:int; warnings:list[str]

def _db(request: Request) -> str:
    root = getattr(request.app.state, "project_root", ".")
    db = os.environ.get("LIFELEDGER_DB", os.path.join(root, "data", "lifeledger.db"))
    return db

def _load_sc(request: Request, path: str) -> dict:
    root = getattr(request.app.state, "project_root", ".")
    abs_path = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {path}")
    raw = load_yaml(abs_path)
    return raw.get("scenario", raw)

@router.get("/insights/mc", response_model=MCInsightResultOut)
def get_mc_insights(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    prob_fire: float = Query(default=0.85),
    n_simulations: int = Query(default=1000),
    fire_year: Optional[int] = Query(default=None),
    current_nw: Optional[float] = Query(default=None),
    fire_target_nw: Optional[float] = Query(default=None),
    annual_spending: Optional[float] = Query(default=None),
    years_to_fire: Optional[int] = Query(default=None),
    equity_fraction: float = Query(default=0.70),
) -> MCInsightResultOut:
    """@brief Generate MC insights from existing simulation results."""
    try:
        sc = _load_sc(request, scenario_path)
        result = generate_mc_insights(
            prob_fire=prob_fire, n_simulations=n_simulations, scenario=sc,
            fire_year=fire_year, current_nw=current_nw,
            fire_target_nw=fire_target_nw, annual_spending=annual_spending,
            years_to_fire=years_to_fire, equity_fraction=equity_fraction,
            scenario_path=scenario_path,
        )
        def _i(i: MCInsight) -> MCInsightOut:
            return MCInsightOut(category=i.category, priority=i.priority,
                               title=i.title, detail=i.detail, action=i.action,
                               impact=i.impact, colour=i.colour, icon=i.icon)
        return MCInsightResultOut(
            scenario_path=result.scenario_path, prob_fire=result.prob_fire,
            n_simulations=result.n_simulations, insights=[_i(i) for i in result.insights],
            overall_health=result.overall_health, summary=result.summary,
            warnings=result.warnings,
        )
    except HTTPException: raise
    except Exception as exc:
        logger.error("get_mc_insights: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})

@router.post("/insights/snapshot")
def save_snapshot(request: Request, body: SnapshotRequest) -> dict:
    """@brief Save a review baseline snapshot."""
    try:
        snap_id = save_review_snapshot(
            db_file=_db(request), scenario_path=body.scenario_path,
            net_worth=body.net_worth, fire_year=body.fire_year,
            pension_value=body.pension_value, isa_value=body.isa_value,
            savings_value=body.savings_value, annual_spending=body.annual_spending,
            prob_fire=body.prob_fire,
        )
        return {"success": True, "snapshot_id": snap_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)})

@router.get("/insights/snapshots")
def list_snapshots(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
) -> list[dict]:
    """@brief List saved review snapshots for a scenario."""
    try:
        return load_review_snapshots(_db(request), scenario_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)})

@router.post("/insights/review", response_model=ReviewOut)
def generate_review(request: Request, body: ReviewRequest) -> ReviewOut:
    """@brief Generate an annual review comparing current state to a baseline."""
    try:
        snapshots = load_review_snapshots(_db(request), body.scenario_path)
        baseline  = next((s for s in snapshots if s["id"] == body.baseline_id), None)
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline snapshot not found")
        result = generate_annual_review(
            current_nw=body.net_worth, current_fire_year=body.fire_year,
            current_pension=body.pension_value, current_isa=body.isa_value,
            current_savings=body.savings_value, current_spending=body.annual_spending,
            current_prob_fire=body.prob_fire, baseline_snapshot=baseline,
        )
        return ReviewOut(
            review_date=result.review_date, baseline_date=result.baseline_date,
            period_label=result.period_label,
            metrics=[ReviewMetricOut(**vars(m)) for m in result.metrics],
            narrative=result.narrative, headline=result.headline,
            fire_delta_months=result.fire_delta_months, warnings=result.warnings,
        )
    except HTTPException: raise
    except Exception as exc:
        logger.error("generate_review: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})
