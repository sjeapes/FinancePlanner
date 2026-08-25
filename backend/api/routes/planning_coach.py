"""
@file planning_coach.py (routes)
@brief FastAPI routes for Phase 12 (partial) planning coach alerts.
"""
import logging, os
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from backend.engine.planning_coach import PlanningCoachEngine
from backend.persistence.yaml_serialiser import load_yaml

logger = logging.getLogger(__name__)
router = APIRouter()

class CoachAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rule_id: str; priority: str; title: str; detail: str
    action: str; amount_gbp: Optional[float]; days_left: Optional[int]
    colour: str; icon: str

class CoachResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    alerts: list[CoachAlertOut]
    total_high: int; total_medium: int; total_low: int
    scenario_year: int; warnings: list[str]

def _load_scenario(request, path):
    root = getattr(request.app.state, "project_root", ".")
    abs_path = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {path}")
    raw = load_yaml(abs_path)
    return raw.get("scenario", raw)

@router.get("/coach/alerts", response_model=CoachResultOut)
def get_coach_alerts(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    current_net_worth: Optional[float] = Query(default=None),
    fire_target: Optional[float] = Query(default=None),
    fire_year_projected: Optional[int] = Query(default=None),
) -> CoachResultOut:
    """@brief Return ranked planning alerts for the active scenario."""
    try:
        sc = _load_scenario(request, scenario_path)
        engine = PlanningCoachEngine()
        result = engine.run(
            scenario=sc,
            current_net_worth=current_net_worth,
            fire_target=fire_target,
            fire_year_projected=fire_year_projected,
        )
        def _a(a): return CoachAlertOut(**vars(a))
        return CoachResultOut(
            alerts=[_a(a) for a in result.alerts],
            total_high=result.total_high,
            total_medium=result.total_medium,
            total_low=result.total_low,
            scenario_year=result.scenario_year,
            warnings=result.warnings,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_coach_alerts: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})
