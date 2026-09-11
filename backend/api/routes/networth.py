"""
@file networth.py
@brief FastAPI route exposing today's actual net worth — raw account
       balances as entered, with zero growth/income/contributions simulated.

Why this exists as its own endpoint rather than reusing the projection
timeline's year==start snapshot: that snapshot has a full year of growth,
income, contributions, and mortgage amortisation applied to it (it needs to,
to be a meaningful *projected* year) — which silently adds a phantom extra
year of compounding on top of balances the user already entered as current.
See backend.engine.calculator.compute_current_net_worth for the calculation
itself; this module only wraps it as an API response.

Endpoints:
  GET /api/networth/current?scenario_path=... — today's real net worth.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from backend.engine.calculator import compute_current_net_worth
from backend.engine.scenario_engine import load_scenario_for_projection

logger = logging.getLogger(__name__)
router = APIRouter()


class BreakdownItem(BaseModel):
    """@brief One account's contribution to today's net worth breakdown."""
    name: str
    category: str
    value: float
    is_primary_residence: bool = False


class CurrentNetWorthResponse(BaseModel):
    """
    @brief Today's actual net worth, computed directly from entered balances.
    @param total_savings      Sum of savings account balances.
    @param total_investments  Sum of investment account balances.
    @param total_pensions     Sum of pension fund balances.
    @param total_property     Sum of ALL property values, including the primary residence.
    @param primary_residence_value Sum of property values identified as a primary
                               residence — a subset of total_property, not additional to it.
    @param total_mortgages    Sum of outstanding mortgage balances (a liability).
    @param total_assets       savings + investments + pensions + property.
    @param total_liabilities  total_mortgages.
    @param total_net_worth    total_assets - total_liabilities. Includes the primary
                               residence — use this for general net worth displays.
    @param total_net_worth_investable total_net_worth with the primary residence and
                               its mortgage backed out — use this for FIRE-style figures.
    @param breakdown          Per-account breakdown for pie/allocation charts.
    """
    model_config = ConfigDict(from_attributes=True)

    total_savings: float
    total_investments: float
    total_pensions: float
    total_property: float
    primary_residence_value: float
    total_mortgages: float
    total_assets: float
    total_liabilities: float
    total_net_worth: float
    total_net_worth_investable: float
    breakdown: dict[str, BreakdownItem]


def _resolve_path(request: Request, scenario_path: str) -> str:
    """@brief Resolve a scenario path to an absolute path using the app project root."""
    if os.path.isabs(scenario_path):
        return scenario_path
    project_root = getattr(request.app.state, "project_root", ".")
    return os.path.join(project_root, scenario_path)


@router.get("/networth/current", response_model=CurrentNetWorthResponse)
def get_current_net_worth(scenario_path: str, request: Request) -> CurrentNetWorthResponse:
    """
    @brief Return today's actual net worth for a scenario — no simulation applied.

    @param scenario_path Path to the scenario YAML, relative to project root.
    @param request       FastAPI request.
    @return              CurrentNetWorthResponse.
    """
    abs_path = _resolve_path(request, scenario_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario file not found: {scenario_path}")

    try:
        project_root = getattr(request.app.state, "project_root", ".")
        scenario = load_scenario_for_projection(abs_path, project_root)
        if scenario is None:
            raise HTTPException(status_code=422, detail=f"Failed to parse scenario YAML: {scenario_path}")

        result = compute_current_net_worth(scenario, request.app.state.config)
        return CurrentNetWorthResponse(
            total_savings=result.total_savings,
            total_investments=result.total_investments,
            total_pensions=result.total_pensions,
            total_property=result.total_property,
            primary_residence_value=result.primary_residence_value,
            total_mortgages=result.total_mortgages,
            total_assets=result.total_assets,
            total_liabilities=result.total_liabilities,
            total_net_worth=result.total_net_worth,
            total_net_worth_investable=result.total_net_worth_investable,
            breakdown=result.breakdown,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_current_net_worth: failed for %s: %s", abs_path, exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Engine error", "detail": str(exc)})
