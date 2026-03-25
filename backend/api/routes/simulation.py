"""
@file simulation.py
@brief FastAPI routes for running financial projections and Monte Carlo simulations.

Endpoints:
  POST /api/simulate            — run a deterministic projection for a scenario
  POST /api/simulate/monte-carlo — run Monte Carlo simulation for a scenario
"""

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.engine.calculator import (
    ProjectionEngine,
    TimelineResult,
    run_monte_carlo,
)
from backend.engine.scenario_engine import load_scenario_for_projection
from backend.persistence.yaml_serialiser import load_scenario_from_file

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    """
    @brief Request body for POST /api/simulate.
    @param scenario_path Path to the scenario YAML file, relative to project root.
    @param include_breakdown Whether to include per-account breakdowns in the response.
    """
    model_config = ConfigDict(from_attributes=True)

    scenario_path: str
    include_breakdown: bool = True


class MonteCarloRequest(BaseModel):
    """
    @brief Request body for POST /api/simulate/monte-carlo.
    @param scenario_path Path to the scenario YAML file.
    @param n_simulations Number of Monte Carlo simulation runs.
    @param seed Random seed for reproducibility.
    """
    model_config = ConfigDict(from_attributes=True)

    scenario_path: str
    n_simulations: int = Field(default=1000, ge=1, le=50000)
    seed: int = 42


class AccountSnapshotOut(BaseModel):
    """
    @brief API output model for a single account snapshot.
    @param account_id Account identifier.
    @param name Display name.
    @param account_type Account type string.
    @param value Value at year end.
    @param contributions_in Contributions received this year.
    @param growth_amount Growth/interest earned this year.
    """
    model_config = ConfigDict(from_attributes=True)

    account_id: str
    name: str
    account_type: str
    value: float
    contributions_in: float = 0.0
    growth_amount: float = 0.0


class IncomeSnapshotOut(BaseModel):
    """
    @brief API output model for a single income snapshot.
    @param source_id Income source identifier.
    @param name Display name.
    @param person_id Owner person identifier.
    @param gross Gross income amount.
    @param net_income Net income after tax.
    @param income_tax Income tax payable.
    @param national_insurance NI payable.
    @param effective_rate Combined effective rate.
    @param contributions_routed Total routed to accounts.
    """
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    name: str
    person_id: str
    gross: float
    net_income: float = 0.0
    income_tax: float = 0.0
    national_insurance: float = 0.0
    effective_rate: float = 0.0
    contributions_routed: float = 0.0


class YearSnapshotOut(BaseModel):
    """
    @brief API output model for a single year snapshot.
    @param year Calendar year.
    @param total_net_worth Total net worth.
    @param total_assets Total assets.
    @param total_liabilities Total liabilities.
    @param total_gross_income Total gross income.
    @param total_net_income Total net income.
    @param total_contributions Total contributions.
    @param total_expenses Total expenses.
    @param fire_achieved Whether FIRE target was reached.
    @param fire_coverage Coverage ratio.
    @param ages Dict of person_id -> age.
    @param accounts Per-account snapshots (when include_breakdown=True).
    @param income_sources Per-source income snapshots.
    @param events Life event descriptions.
    """
    model_config = ConfigDict(from_attributes=True)

    year: int
    total_net_worth: float
    total_assets: float
    total_liabilities: float
    total_gross_income: float
    total_net_income: float
    total_contributions: float
    total_expenses: float
    fire_achieved: bool
    fire_coverage: float
    income_coverage: float = 0.0
    ages: dict[str, int] = {}
    accounts: dict[str, AccountSnapshotOut] = {}
    income_sources: list[IncomeSnapshotOut] = []
    events: list[str] = []


class TimelineResponse(BaseModel):
    """
    @brief API response for POST /api/simulate.
    @param scenario_id Scenario identifier.
    @param scenario_name Scenario display name.
    @param fire_year Year FIRE target first achieved; None if never.
    @param years List of year snapshots.
    """
    model_config = ConfigDict(from_attributes=True)

    scenario_id: str
    scenario_name: str
    fire_year: Optional[int]
    years: list[YearSnapshotOut]


class MonteCarloResponse(BaseModel):
    """
    @brief API response for POST /api/simulate/monte-carlo.
    @param scenario_id Scenario identifier.
    @param scenario_name Scenario display name.
    @param n_simulations Number of simulations run.
    @param prob_fire Probability of achieving FIRE.
    @param years List of calendar years.
    @param p10 10th percentile net worth per year.
    @param p25 25th percentile.
    @param p50 Median net worth per year.
    @param p75 75th percentile.
    @param p90 90th percentile.
    """
    model_config = ConfigDict(from_attributes=True)

    scenario_id: str
    scenario_name: str
    n_simulations: int
    prob_fire: float
    years: list[int]
    p10: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p90: list[float]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_account_snapshot(snap_dict: dict[str, Any]) -> dict[str, AccountSnapshotOut]:
    """
    @brief Convert a dict of AccountSnapshot dataclasses to API output models.
    @param snap_dict Dict mapping account_id -> AccountSnapshot dataclass.
    @return Dict mapping account_id -> AccountSnapshotOut.
    """
    result = {}
    for aid, snap in snap_dict.items():
        try:
            result[aid] = AccountSnapshotOut(
                account_id=snap.account_id,
                name=snap.name,
                account_type=snap.account_type,
                value=snap.value,
                contributions_in=snap.contributions_in,
                growth_amount=snap.growth_amount,
            )
        except Exception as exc:
            logger.warning("_build_account_snapshot: bad snap for %s: %s", aid, exc)
    return result


def _build_income_snapshot(income_list: list) -> list[IncomeSnapshotOut]:
    """
    @brief Convert a list of IncomeSnapshot dataclasses to API output models.
    @param income_list List of IncomeSnapshot dataclass instances.
    @return List of IncomeSnapshotOut instances.
    """
    result = []
    for src in income_list:
        try:
            tax = src.tax_result
            result.append(IncomeSnapshotOut(
                source_id=src.source_id,
                name=src.name,
                person_id=src.person_id,
                gross=src.gross,
                net_income=tax.net_income,
                income_tax=tax.income_tax,
                national_insurance=tax.national_insurance,
                effective_rate=tax.effective_rate,
                contributions_routed=src.contributions_routed,
            ))
        except Exception as exc:
            logger.warning("_build_income_snapshot: bad income snap: %s", exc)
    return result


def _timeline_to_response(
    result: TimelineResult,
    include_breakdown: bool,
) -> TimelineResponse:
    """
    @brief Convert a TimelineResult dataclass to a TimelineResponse API model.
    @param result TimelineResult from the projection engine.
    @param include_breakdown Whether to include per-account breakdowns.
    @return TimelineResponse Pydantic model.
    """
    years_out = []
    for snap in result.years:
        accounts = _build_account_snapshot(snap.accounts) if include_breakdown else {}
        income = _build_income_snapshot(snap.income_sources)
        years_out.append(YearSnapshotOut(
            year=snap.year,
            total_net_worth=snap.total_net_worth,
            total_assets=snap.total_assets,
            total_liabilities=snap.total_liabilities,
            total_gross_income=snap.total_gross_income,
            total_net_income=snap.total_net_income,
            total_contributions=snap.total_contributions,
            total_expenses=snap.total_expenses,
            fire_achieved=snap.fire_achieved,
            fire_coverage=snap.fire_coverage,
            income_coverage=snap.income_coverage,
            ages=snap.ages,
            accounts=accounts,
            income_sources=income,
            events=snap.events,
        ))

    return TimelineResponse(
        scenario_id=result.scenario_id,
        scenario_name=result.scenario_name,
        fire_year=result.fire_year,
        years=years_out,
    )


def _resolve_path(request: Request, scenario_path: str) -> str:
    """
    @brief Resolve a scenario path to an absolute path using the app project root.
    @param request FastAPI Request object (used to access app.state).
    @param scenario_path Relative or absolute path from the request body.
    @return Absolute file path string.
    """
    if os.path.isabs(scenario_path):
        return scenario_path
    project_root = getattr(request.app.state, "project_root", ".")
    return os.path.join(project_root, scenario_path)


# ── Route handlers ────────────────────────────────────────────────────────────

@router.post("/simulate", response_model=TimelineResponse)
def simulate(body: SimulateRequest, request: Request) -> TimelineResponse:
    """
    @brief Run a deterministic year-by-year projection for a scenario.

    Loads the scenario from the specified YAML path, runs the projection
    engine, and returns the full timeline including FIRE year and optional
    per-account breakdowns.

    @param body SimulateRequest with scenario_path and include_breakdown.
    @param request FastAPI Request (provides access to app.state).
    @return TimelineResponse with all year snapshots.
    """
    abs_path = _resolve_path(request, body.scenario_path)

    if not os.path.isfile(abs_path):
        logger.warning("simulate: scenario not found at %s", abs_path)
        raise HTTPException(status_code=404, detail=f"Scenario file not found: {body.scenario_path}")

    try:
        project_root = getattr(request.app.state, "project_root", ".")
        scenario = load_scenario_for_projection(abs_path, project_root)
        if scenario is None:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to parse scenario YAML: {body.scenario_path}",
            )

        config = request.app.state.config
        tax_profiles = request.app.state.tax_profiles

        engine = ProjectionEngine(config, tax_profiles)
        result = engine.project(scenario)

        return _timeline_to_response(result, body.include_breakdown)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("simulate: engine error for %s: %s", abs_path, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Engine error", "detail": str(exc)},
        )


@router.post("/simulate/monte-carlo", response_model=MonteCarloResponse)
def simulate_monte_carlo(body: MonteCarloRequest, request: Request) -> MonteCarloResponse:
    """
    @brief Run a Monte Carlo simulation for a scenario.

    Perturbs growth and inflation rates across n_simulations runs and
    returns percentile bands for net worth over the projection timeline.

    @param body MonteCarloRequest with scenario_path, n_simulations, and seed.
    @param request FastAPI Request.
    @return MonteCarloResponse with probability arrays.
    """
    abs_path = _resolve_path(request, body.scenario_path)

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario file not found: {body.scenario_path}")

    try:
        project_root = getattr(request.app.state, "project_root", ".")
        scenario = load_scenario_for_projection(abs_path, project_root)
        if scenario is None:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to parse scenario YAML: {body.scenario_path}",
            )

        config = request.app.state.config
        tax_profiles = request.app.state.tax_profiles

        mc_result = run_monte_carlo(
            scenario=scenario,
            config=config,
            tax_profiles=tax_profiles,
            n_simulations=body.n_simulations,
            seed=body.seed,
        )

        return MonteCarloResponse(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            n_simulations=mc_result.n_simulations,
            prob_fire=mc_result.prob_fire,
            years=mc_result.years,
            p10=mc_result.p10,
            p25=mc_result.p25,
            p50=mc_result.p50,
            p75=mc_result.p75,
            p90=mc_result.p90,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "simulate_monte_carlo: engine error for %s: %s", abs_path, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "Monte Carlo engine error", "detail": str(exc)},
        )
