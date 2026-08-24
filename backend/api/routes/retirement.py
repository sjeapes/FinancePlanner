"""
@file retirement.py
@brief FastAPI routes for Phase 4 retirement planning features.

Endpoints:
  GET  /api/retirement/report           — full retirement report (all 5 analyses)
  GET  /api/retirement/income-coverage  — year-by-year income vs expense coverage
  GET  /api/retirement/drawdown-order   — ISA-first vs SIPP-first tax comparison
  GET  /api/retirement/annuity          — annuity vs drawdown comparison per pension
  GET  /api/retirement/state-pension    — NI tracker, top-up cost, deferral options
  GET  /api/retirement/emergency-fund   — liquid cash months-covered analysis
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.engine.retirement_engine import (
    AnnuityOption,
    AnnuityVsDrawdownResult,
    DeferralOption,
    DrawdownOrderResult,
    DrawdownProjection,
    DrawdownYearRow,
    EmergencyFundStatus,
    IncomeCoverageReport,
    IncomeCoverageRow,
    NiTopUpOption,
    RetirementConfig,
    RetirementEngine,
    RetirementReport,
    StatePensionProjection,
    load_retirement_config,
)
from backend.persistence.yaml_serialiser import load_scenario_from_file

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Response models (Pydantic)
# ---------------------------------------------------------------------------


class IncomeSourceOut(BaseModel):
    """@brief API output for one retirement income source in a year."""
    model_config = ConfigDict(from_attributes=True)
    label: str
    source_type: str
    annual_gross: float
    is_taxable: bool
    person_id: str


class IncomeCoverageRowOut(BaseModel):
    """@brief API output for one year of income coverage analysis."""
    model_config = ConfigDict(from_attributes=True)
    year: int
    total_income: float
    total_expenses: float
    coverage_ratio: float
    surplus_deficit: float
    income_breakdown: list[IncomeSourceOut]
    status: str
    months_funded: float


class IncomeCoverageReportOut(BaseModel):
    """@brief API output for the full income coverage report."""
    model_config = ConfigDict(from_attributes=True)
    years: list[IncomeCoverageRowOut]
    first_shortfall_year: Optional[int]
    worst_coverage_year: int
    worst_coverage_ratio: float
    avg_coverage_ratio: float
    total_surplus: float
    total_shortfall: float
    warnings: list[str]


class DrawdownYearRowOut(BaseModel):
    """@brief API output for one year of drawdown strategy comparison."""
    model_config = ConfigDict(from_attributes=True)
    year: int
    income_needed: float
    strategy_a_tax: float
    strategy_b_tax: float
    tax_saving: float


class DrawdownOrderResultOut(BaseModel):
    """@brief API output for drawdown order comparison."""
    model_config = ConfigDict(from_attributes=True)
    strategy_a_id: str
    strategy_a_label: str
    strategy_b_id: str
    strategy_b_label: str
    year_rows: list[DrawdownYearRowOut]
    lifetime_tax_a: float
    lifetime_tax_b: float
    lifetime_tax_saving: float
    recommended_strategy: str
    recommendation_notes: str
    warnings: list[str]


class DrawdownProjectionOut(BaseModel):
    """@brief API output for drawdown projection."""
    model_config = ConfigDict(from_attributes=True)
    swr: float
    fund_at_start: float
    income_yr1: float
    income_at_ages: dict[int, float]
    exhaustion_age: Optional[int]


class AnnuityOptionOut(BaseModel):
    """@brief API output for one annuity option."""
    model_config = ConfigDict(from_attributes=True)
    annuity_type: str
    label: str
    fund_at_conversion: float
    annual_income_yr1: float
    inflation_rate: float
    survivor_fraction: float
    guarantee_years: int
    income_at_ages: dict[int, float]
    break_even_age: Optional[int]


class AnnuityVsDrawdownOut(BaseModel):
    """@brief API output for annuity vs drawdown comparison."""
    model_config = ConfigDict(from_attributes=True)
    pension_id: str
    conversion_age: int
    fund_value: float
    drawdown: DrawdownProjectionOut
    annuity_level: AnnuityOptionOut
    annuity_inflation: AnnuityOptionOut
    annuity_joint: AnnuityOptionOut
    notes: str


class NiTopUpOptionOut(BaseModel):
    """@brief API output for one NI top-up option."""
    model_config = ConfigDict(from_attributes=True)
    tax_year: str
    cost_gbp: float
    weekly_pension_gain: float
    annual_pension_gain: float
    years_to_recoup: float
    roi_10yr_pct: float


class DeferralOptionOut(BaseModel):
    """@brief API output for one state pension deferral option."""
    model_config = ConfigDict(from_attributes=True)
    claim_age: int
    weeks_deferred: int
    annual_bonus_pct: float
    weekly_pension_with_bonus: float
    annual_pension_with_bonus: float
    break_even_years: float


class StatePensionProjectionOut(BaseModel):
    """@brief API output for one person's state pension projection."""
    model_config = ConfigDict(from_attributes=True)
    person_id: str
    person_name: str
    current_ni_years: int
    ni_years_needed: int
    gap_years: int
    projected_start_year: int
    full_weekly_amount: float
    projected_weekly: float
    projected_annual: float
    triple_lock_at_ages: dict[int, float]
    top_up_options: list[NiTopUpOptionOut]
    deferral_options: list[DeferralOptionOut]
    total_top_up_cost: float
    max_pension_if_filled: float
    warnings: list[str]


class EmergencyFundStatusOut(BaseModel):
    """@brief API output for emergency fund status."""
    model_config = ConfigDict(from_attributes=True)
    total_liquid_cash: float
    monthly_expenses: float
    months_covered: float
    target_months: float
    amber_months: float
    status: str
    recommended_top_up: float
    liquid_accounts: dict[str, float]
    warnings: list[str]


class RetirementReportOut(BaseModel):
    """@brief API output for the full retirement report."""
    model_config = ConfigDict(from_attributes=True)
    scenario_id: str
    income_coverage: IncomeCoverageReportOut
    drawdown_comparison: DrawdownOrderResultOut
    annuity_comparisons: list[AnnuityVsDrawdownOut]
    state_pension_projections: list[StatePensionProjectionOut]
    emergency_fund: EmergencyFundStatusOut
    retirement_start_year: int
    notes: str
    warnings: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_engine(request: Request) -> RetirementEngine:
    """
    @brief Load or re-use the RetirementEngine from app state.

    @param request  FastAPI request with app.state.
    @return         RetirementEngine instance.
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


def _load_scenario(request: Request, scenario_path: str):
    """
    @brief Load a scenario from a path relative to project root.

    @param request        FastAPI request.
    @param scenario_path  Relative path to scenario YAML.
    @return               Scenario object.
    @raises HTTPException 404 if not found, 500 on parse error.
    """
    root = getattr(request.app.state, "project_root", ".")
    abs_path = os.path.join(root, scenario_path)
    if not os.path.exists(abs_path):
        raise HTTPException(
            status_code=404,
            detail=f"Scenario file not found: {scenario_path}",
        )
    try:
        scenario = load_scenario_from_file(abs_path)
        if scenario is None:
            raise ValueError("Parser returned None")
        return scenario
    except Exception as exc:
        logger.error("Failed to load scenario '%s': %s", scenario_path, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse scenario: {exc}",
        )


def _cov_row_out(r: IncomeCoverageRow) -> IncomeCoverageRowOut:
    """@brief Convert IncomeCoverageRow to Pydantic output model."""
    return IncomeCoverageRowOut(
        year=r.year,
        total_income=r.total_income,
        total_expenses=r.total_expenses,
        coverage_ratio=r.coverage_ratio,
        surplus_deficit=r.surplus_deficit,
        income_breakdown=[
            IncomeSourceOut(
                label=s.label, source_type=s.source_type,
                annual_gross=s.annual_gross, is_taxable=s.is_taxable,
                person_id=s.person_id,
            )
            for s in r.income_breakdown
        ],
        status=r.status,
        months_funded=r.months_funded,
    )


def _report_to_out(report: RetirementReport) -> RetirementReportOut:
    """@brief Convert RetirementReport dataclass to Pydantic output model."""
    cov = report.income_coverage
    dd = report.drawdown_comparison
    ef = report.emergency_fund

    def _ann_out(a: AnnuityVsDrawdownResult) -> AnnuityVsDrawdownOut:
        def _ao(opt: AnnuityOption) -> AnnuityOptionOut:
            return AnnuityOptionOut(
                annuity_type=opt.annuity_type, label=opt.label,
                fund_at_conversion=opt.fund_at_conversion,
                annual_income_yr1=opt.annual_income_yr1,
                inflation_rate=opt.inflation_rate,
                survivor_fraction=opt.survivor_fraction,
                guarantee_years=opt.guarantee_years,
                income_at_ages=opt.income_at_ages,
                break_even_age=opt.break_even_age,
            )
        return AnnuityVsDrawdownOut(
            pension_id=a.pension_id, conversion_age=a.conversion_age,
            fund_value=a.fund_value,
            drawdown=DrawdownProjectionOut(
                swr=a.drawdown.swr, fund_at_start=a.drawdown.fund_at_start,
                income_yr1=a.drawdown.income_yr1,
                income_at_ages=a.drawdown.income_at_ages,
                exhaustion_age=a.drawdown.exhaustion_age,
            ),
            annuity_level=_ao(a.annuity_level),
            annuity_inflation=_ao(a.annuity_inflation),
            annuity_joint=_ao(a.annuity_joint),
            notes=a.notes,
        )

    def _sp_out(sp: StatePensionProjection) -> StatePensionProjectionOut:
        return StatePensionProjectionOut(
            person_id=sp.person_id, person_name=sp.person_name,
            current_ni_years=sp.current_ni_years,
            ni_years_needed=sp.ni_years_needed, gap_years=sp.gap_years,
            projected_start_year=sp.projected_start_year,
            full_weekly_amount=sp.full_weekly_amount,
            projected_weekly=sp.projected_weekly, projected_annual=sp.projected_annual,
            triple_lock_at_ages=sp.triple_lock_at_ages,
            top_up_options=[NiTopUpOptionOut(**vars(t)) for t in sp.top_up_options],
            deferral_options=[DeferralOptionOut(**vars(d)) for d in sp.deferral_options],
            total_top_up_cost=sp.total_top_up_cost,
            max_pension_if_filled=sp.max_pension_if_filled,
            warnings=sp.warnings,
        )

    return RetirementReportOut(
        scenario_id=report.scenario_id,
        income_coverage=IncomeCoverageReportOut(
            years=[_cov_row_out(r) for r in cov.years],
            first_shortfall_year=cov.first_shortfall_year,
            worst_coverage_year=cov.worst_coverage_year,
            worst_coverage_ratio=cov.worst_coverage_ratio,
            avg_coverage_ratio=cov.avg_coverage_ratio,
            total_surplus=cov.total_surplus, total_shortfall=cov.total_shortfall,
            warnings=cov.warnings,
        ),
        drawdown_comparison=DrawdownOrderResultOut(
            strategy_a_id=dd.strategy_a_id, strategy_a_label=dd.strategy_a_label,
            strategy_b_id=dd.strategy_b_id, strategy_b_label=dd.strategy_b_label,
            year_rows=[DrawdownYearRowOut(**vars(r)) for r in dd.year_rows],
            lifetime_tax_a=dd.lifetime_tax_a, lifetime_tax_b=dd.lifetime_tax_b,
            lifetime_tax_saving=dd.lifetime_tax_saving,
            recommended_strategy=dd.recommended_strategy,
            recommendation_notes=dd.recommendation_notes, warnings=dd.warnings,
        ),
        annuity_comparisons=[_ann_out(a) for a in report.annuity_comparisons],
        state_pension_projections=[_sp_out(sp) for sp in report.state_pension_projections],
        emergency_fund=EmergencyFundStatusOut(
            total_liquid_cash=ef.total_liquid_cash, monthly_expenses=ef.monthly_expenses,
            months_covered=ef.months_covered, target_months=ef.target_months,
            amber_months=ef.amber_months, status=ef.status,
            recommended_top_up=ef.recommended_top_up,
            liquid_accounts=ef.liquid_accounts, warnings=ef.warnings,
        ),
        retirement_start_year=report.retirement_start_year,
        notes=report.notes, warnings=report.warnings,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/retirement/report", response_model=RetirementReportOut)
def get_retirement_report(
    request: Request,
    scenario_path: str = Query(
        default="data/scenarios/base.yaml",
        description="Path to scenario YAML, relative to project root.",
    ),
) -> RetirementReportOut:
    """
    @brief Run all five retirement analyses and return the full report.

    Loads the scenario, runs income coverage, drawdown order comparison,
    annuity comparison, state pension projection, and emergency fund analysis.

    @param request        FastAPI Request.
    @param scenario_path  Relative path to the scenario YAML file.
    @return               RetirementReportOut JSON.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        report = engine.analyse(scenario)
        return _report_to_out(report)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_retirement_report error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/retirement/income-coverage", response_model=IncomeCoverageReportOut)
def get_income_coverage(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    start_year: Optional[int] = Query(default=None, description="Override retirement start year."),
) -> IncomeCoverageReportOut:
    """
    @brief Return year-by-year income vs expense coverage for the retirement phase.

    @param request        FastAPI Request.
    @param scenario_path  Relative path to the scenario YAML.
    @param start_year     Override retirement start year (uses scenario end-dates if None).
    @return               IncomeCoverageReportOut JSON.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        retire_year = start_year or engine._retirement_start_year(scenario)
        coverage = engine._income_coverage(scenario, None, retire_year)
        cov = coverage
        return IncomeCoverageReportOut(
            years=[_cov_row_out(r) for r in cov.years],
            first_shortfall_year=cov.first_shortfall_year,
            worst_coverage_year=cov.worst_coverage_year,
            worst_coverage_ratio=cov.worst_coverage_ratio,
            avg_coverage_ratio=cov.avg_coverage_ratio,
            total_surplus=cov.total_surplus, total_shortfall=cov.total_shortfall,
            warnings=cov.warnings,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_income_coverage error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/retirement/drawdown-order", response_model=DrawdownOrderResultOut)
def get_drawdown_order(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    strategy_a: str = Query(
        default="isa_first",
        description="Primary strategy: isa_first | sipp_first | gia_first | optimised",
    ),
    strategy_b: str = Query(
        default="sipp_first",
        description="Comparison strategy.",
    ),
) -> DrawdownOrderResultOut:
    """
    @brief Compare two drawdown strategies and return the lifetime tax saving.

    @param request        FastAPI Request.
    @param scenario_path  Relative path to the scenario YAML.
    @param strategy_a     Primary drawdown strategy ID.
    @param strategy_b     Comparison drawdown strategy ID.
    @return               DrawdownOrderResultOut JSON.
    """
    valid = {"isa_first", "sipp_first", "gia_first", "optimised"}
    if strategy_a not in valid or strategy_b not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"strategy must be one of: {sorted(valid)}",
        )
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        retire_year = engine._retirement_start_year(scenario)
        result = engine._drawdown_order_comparison(scenario, retire_year, strategy_a, strategy_b)
        dd = result
        return DrawdownOrderResultOut(
            strategy_a_id=dd.strategy_a_id, strategy_a_label=dd.strategy_a_label,
            strategy_b_id=dd.strategy_b_id, strategy_b_label=dd.strategy_b_label,
            year_rows=[DrawdownYearRowOut(**vars(r)) for r in dd.year_rows],
            lifetime_tax_a=dd.lifetime_tax_a, lifetime_tax_b=dd.lifetime_tax_b,
            lifetime_tax_saving=dd.lifetime_tax_saving,
            recommended_strategy=dd.recommended_strategy,
            recommendation_notes=dd.recommendation_notes, warnings=dd.warnings,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_drawdown_order error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/retirement/annuity", response_model=list[AnnuityVsDrawdownOut])
def get_annuity_comparison(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
) -> list[AnnuityVsDrawdownOut]:
    """
    @brief Return annuity vs drawdown comparison for all pension pots.

    @param request        FastAPI Request.
    @param scenario_path  Relative path to the scenario YAML.
    @return               List of AnnuityVsDrawdownOut, one per pension fund.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        retire_year = engine._retirement_start_year(scenario)
        comparisons = engine._annuity_comparisons(scenario, retire_year)

        def _ao(opt: AnnuityOption) -> AnnuityOptionOut:
            return AnnuityOptionOut(
                annuity_type=opt.annuity_type, label=opt.label,
                fund_at_conversion=opt.fund_at_conversion,
                annual_income_yr1=opt.annual_income_yr1,
                inflation_rate=opt.inflation_rate,
                survivor_fraction=opt.survivor_fraction,
                guarantee_years=opt.guarantee_years,
                income_at_ages=opt.income_at_ages,
                break_even_age=opt.break_even_age,
            )

        return [
            AnnuityVsDrawdownOut(
                pension_id=c.pension_id, conversion_age=c.conversion_age,
                fund_value=c.fund_value,
                drawdown=DrawdownProjectionOut(
                    swr=c.drawdown.swr, fund_at_start=c.drawdown.fund_at_start,
                    income_yr1=c.drawdown.income_yr1,
                    income_at_ages=c.drawdown.income_at_ages,
                    exhaustion_age=c.drawdown.exhaustion_age,
                ),
                annuity_level=_ao(c.annuity_level),
                annuity_inflation=_ao(c.annuity_inflation),
                annuity_joint=_ao(c.annuity_joint),
                notes=c.notes,
            )
            for c in comparisons
        ]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_annuity_comparison error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/retirement/state-pension", response_model=list[StatePensionProjectionOut])
def get_state_pension(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
) -> list[StatePensionProjectionOut]:
    """
    @brief Return state pension projections for all people in the scenario.

    @param request        FastAPI Request.
    @param scenario_path  Relative path to the scenario YAML.
    @return               List of StatePensionProjectionOut.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        projections = engine._state_pension_projections(scenario)
        return [
            StatePensionProjectionOut(
                person_id=sp.person_id, person_name=sp.person_name,
                current_ni_years=sp.current_ni_years,
                ni_years_needed=sp.ni_years_needed, gap_years=sp.gap_years,
                projected_start_year=sp.projected_start_year,
                full_weekly_amount=sp.full_weekly_amount,
                projected_weekly=sp.projected_weekly, projected_annual=sp.projected_annual,
                triple_lock_at_ages=sp.triple_lock_at_ages,
                top_up_options=[NiTopUpOptionOut(**vars(t)) for t in sp.top_up_options],
                deferral_options=[DeferralOptionOut(**vars(d)) for d in sp.deferral_options],
                total_top_up_cost=sp.total_top_up_cost,
                max_pension_if_filled=sp.max_pension_if_filled,
                warnings=sp.warnings,
            )
            for sp in projections
        ]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_state_pension error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/retirement/emergency-fund", response_model=EmergencyFundStatusOut)
def get_emergency_fund(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
) -> EmergencyFundStatusOut:
    """
    @brief Return emergency fund status for the scenario.

    @param request        FastAPI Request.
    @param scenario_path  Relative path to the scenario YAML.
    @return               EmergencyFundStatusOut JSON.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        ef = engine._emergency_fund(scenario, None)
        return EmergencyFundStatusOut(
            total_liquid_cash=ef.total_liquid_cash, monthly_expenses=ef.monthly_expenses,
            months_covered=ef.months_covered, target_months=ef.target_months,
            amber_months=ef.amber_months, status=ef.status,
            recommended_top_up=ef.recommended_top_up,
            liquid_accounts=ef.liquid_accounts, warnings=ef.warnings,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_emergency_fund error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})
