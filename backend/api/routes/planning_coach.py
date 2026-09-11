"""
@file planning_coach.py (routes)
@brief FastAPI routes for Phase 12 (partial) planning coach alerts.
"""
import logging, os
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from backend.engine.planning_coach import PlanningCoachEngine
from backend.engine.retirement_engine import RetirementEngine, RetirementConfig, load_retirement_config
from backend.persistence.yaml_serialiser import load_yaml, load_scenario_from_file

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


def _load_retirement_engine(request: Request) -> RetirementEngine:
    """
    @brief Load or re-use a RetirementEngine, mirroring retirement.py's own
           _load_engine so both modules share the exact same config-loading
           behaviour rather than two copies that could drift.
    """
    if hasattr(request.app.state, "retirement_engine"):
        return request.app.state.retirement_engine
    root = getattr(request.app.state, "project_root", ".")
    cfg_path = os.path.join(root, "config", "retirement", "retirement_config.yaml")
    try:
        cfg = load_retirement_config(cfg_path)
    except FileNotFoundError:
        logger.warning("retirement_config.yaml not found — using defaults.")
        cfg = RetirementConfig()
    engine = RetirementEngine(cfg)
    request.app.state.retirement_engine = engine
    return engine

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

        # Compute the emergency fund status via the same, already-correct
        # RetirementEngine._emergency_fund() that powers the Dashboard's
        # Emergency Fund panel and /api/retirement/emergency-fund, instead
        # of Rule 4 re-deriving its own from the raw scenario dict. That
        # separate derivation only ever scanned savings_accounts (never
        # investment_accounts — ISAs/LISAs are configured as liquid but
        # live there) and matched a fixed set of account_type strings —
        # confirmed live to return £0 for a real scenario whose liquid
        # accounts were all account_type "general" under savings_accounts,
        # which should have matched but something in that parallel path
        # still produced zero. Rather than keep chasing a second
        # implementation, reuse the one already verified correct.
        root = getattr(request.app.state, "project_root", ".")
        abs_path = scenario_path if os.path.isabs(scenario_path) else os.path.join(root, scenario_path)
        emergency_fund_status = None
        if os.path.isfile(abs_path):
            try:
                full_scenario = load_scenario_from_file(abs_path)
                if full_scenario is not None:
                    ret_engine = _load_retirement_engine(request)
                    ef = ret_engine._emergency_fund(full_scenario, None)
                    emergency_fund_status = {
                        "total_liquid_cash": ef.total_liquid_cash,
                        "monthly_expenses": ef.monthly_expenses,
                        "months_covered": ef.months_covered,
                        "target_months": ef.target_months,
                    }
            except Exception as exc:
                logger.warning("get_coach_alerts: emergency fund lookup failed, falling back: %s", exc)

        engine = PlanningCoachEngine()
        result = engine.run(
            scenario=sc,
            current_net_worth=current_net_worth,
            fire_target=fire_target,
            fire_year_projected=fire_year_projected,
            emergency_fund_status=emergency_fund_status,
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
