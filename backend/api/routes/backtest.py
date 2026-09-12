"""
@file backtest.py
@brief FastAPI routes for Phase 9 historical sequence backtest.
"""
import logging, os
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from backend.engine.historical_backtest import HistoricalBacktestEngine, HISTORICAL_SEQUENCES
from backend.engine.calculator import compute_current_net_worth, convert_to_base_currency
from backend.persistence.yaml_serialiser import load_yaml, load_scenario_from_file

logger = logging.getLogger(__name__)
router = APIRouter()

class BacktestYearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    year: int; age: int; portfolio: float; return_rate: float
    drawdown: float; fire_sustained: bool

class BacktestScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scenario_id: str; label: str; description: str; colour: str
    years: list[BacktestYearOut]
    terminal_value: float; ruin_year: Optional[int]; survived: bool
    min_value: float; min_value_year: int

class BacktestResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    base_label: str; base_years: list[BacktestYearOut]; base_terminal: float
    scenarios: list[BacktestScenarioOut]
    all_survived: bool; worst_scenario_id: str; worst_terminal: float
    warnings: list[str]

def _load_scenario(request, path):
    root = getattr(request.app.state, "project_root", ".")
    abs_path = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {path}")
    raw = load_yaml(abs_path)
    return raw.get("scenario", raw)


def _resolve_scenario_path(request, path):
    root = getattr(request.app.state, "project_root", ".")
    return path if os.path.isabs(path) else os.path.join(root, path)

@router.get("/backtest/run", response_model=BacktestResultOut)
def run_backtest(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    equity_fraction: float = Query(default=0.80, ge=0.0, le=1.0),
) -> BacktestResultOut:
    """@brief Run historical sequence backtest for the given scenario."""
    try:
        sc = _load_scenario(request, scenario_path)
        people = sc.get("people", [])
        primary = people[0] if people else {}
        birth_yr   = int(str(primary.get("date_of_birth", "1980-01-01"))[:4])
        retire_age = int(primary.get("retirement_age", 60))
        life_exp   = int(primary.get("life_expectancy", 87))
        retire_yr  = birth_yr + retire_age
        death_yr   = birth_yr + life_exp

        pensions = sc.get("pension_funds", [])

        # Starting portfolio: use the same currency-aware calculation the
        # Dashboard/FIRE tab/Portfolio Mix already rely on, rather than a
        # separate raw-dict sum. That separate sum should have worked out
        # to well over £600k against this session's real test data
        # (pensions + savings alone, ignoring investments and currency
        # conversion entirely) but was returning exactly £0 in every
        # year of every scenario including the flat-growth base case —
        # immediate "ruin" in year one for every single historical
        # sequence, which is what prompted this investigation. Rather
        # than keep chasing why that specific raw-dict path zeroed out,
        # switched to the one already verified correct and currency-aware
        # this session. Property/mortgages are deliberately excluded —
        # this backtest models a retirement PORTFOLIO surviving drawdown,
        # not net worth including a home you live in.
        abs_path = _resolve_scenario_path(request, scenario_path)
        full_scenario = load_scenario_from_file(abs_path) if os.path.isfile(abs_path) else None
        if full_scenario is not None:
            nw = compute_current_net_worth(full_scenario, request.app.state.config)
            portfolio = nw.total_savings + nw.total_investments + nw.total_pensions
        else:
            portfolio = 0.0
            logger.warning("run_backtest: could not parse scenario as dataclass, portfolio defaulted to 0")

        expenses = sc.get("expense_buckets", [])
        config = request.app.state.config
        annual_spend = sum(
            convert_to_base_currency(float(e.get("annual_amount", 0)), e.get("currency"), config)
            for e in expenses if not e.get("end_date")
        ) or 40_000.0
        growth = float(pensions[0].get("assumed_growth_rate", 0.07)) if pensions else 0.07

        engine = HistoricalBacktestEngine()
        result = engine.run(
            starting_portfolio=portfolio,
            annual_drawdown=annual_spend,
            retirement_year=retire_yr,
            projection_end_year=death_yr,
            birth_year=birth_yr,
            base_growth_rate=growth,
            equity_fraction=equity_fraction,
        )

        def _snap(s): return BacktestYearOut(**vars(s))
        def _scen(s): return BacktestScenarioOut(
            scenario_id=s.scenario_id, label=s.label,
            description=s.description, colour=s.colour,
            years=[_snap(y) for y in s.years],
            terminal_value=s.terminal_value, ruin_year=s.ruin_year,
            survived=s.survived, min_value=s.min_value,
            min_value_year=s.min_value_year,
        )
        return BacktestResultOut(
            base_label=result.base_label,
            base_years=[_snap(y) for y in result.base_years],
            base_terminal=result.base_terminal,
            scenarios=[_scen(s) for s in result.scenarios],
            all_survived=result.all_survived,
            worst_scenario_id=result.worst_scenario_id,
            worst_terminal=result.worst_terminal,
            warnings=result.warnings,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("run_backtest: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})

@router.get("/backtest/sequences")
def list_sequences() -> list[dict]:
    """@brief List available historical sequences."""
    return [
        {"id": k, "label": v["label"], "description": v["description"],
         "colour": v["colour"], "length_years": len(v["returns"])}
        for k, v in HISTORICAL_SEQUENCES.items()
    ]
