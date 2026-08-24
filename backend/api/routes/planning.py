"""
@file planning.py
@brief FastAPI routes for Phase 5 Advanced Planning features.

Endpoints:
  GET  /api/planning/report        — full Phase 5 report (all four analyses)
  GET  /api/planning/survivor      — survivor simulation for one partner
  GET  /api/planning/estate        — estate / IHT calculation
  GET  /api/planning/healthcare    — healthcare cost projection
  GET  /api/planning/rebalancing   — portfolio rebalancing alerts
"""

import logging
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from backend.engine.advanced_planning import (
    AdvancedPlanningEngine,
    AdvancedPlanningReport,
    EstateResult,
    GiftRecord,
    HealthcareResult,
    HealthcareYearRow,
    HoldingClassification,
    MortgageAffordability,
    PlanningConfig,
    RebalanceAlert,
    RebalanceResult,
    SurvivorIncomeImpact,
    SurvivorResult,
    load_planning_config,
)
from backend.persistence.yaml_serialiser import load_scenario_from_file

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SurvivorIncomeImpactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source_id: str
    label: str
    annual_gross: float
    tax_treatment: str


class MortgageAffordabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    monthly_payment: float
    survivor_net_monthly: float
    affordability_ratio: float
    is_affordable: bool
    monthly_shortfall: float
    outstanding_balance: float


class SurvivorResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    deceased_person_id: str
    death_year: int
    income_lost: list[SurvivorIncomeImpactOut]
    total_income_lost: float
    survivor_gross_income: float
    survivor_pension_income: float
    expense_reduction: float
    mortgage_affordability: Optional[MortgageAffordabilityOut]
    recommended_life_cover: float
    life_cover_breakdown: dict[str, float]
    key_risks: list[str]
    recommendations: list[str]
    warnings: list[str]


class GiftRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    gift_date: date
    amount: float
    recipient: str
    years_elapsed: float
    is_outside_estate: bool
    taper_relief_pct: float
    effective_iht_rate: float
    iht_at_risk: float
    years_to_exempt: float
    notes: str


class EstateResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    calculation_year: int
    gross_estate: float
    pension_outside_estate: float
    gifts_outside_estate: float
    net_estate: float
    nrb_available: float
    rnrb_available: float
    total_allowances: float
    taxable_estate: float
    iht_liability: float
    net_to_beneficiaries: float
    effective_iht_rate: float
    gift_tracker: list[GiftRecordOut]
    gift_iht_at_risk: float
    annual_gift_allowance_remaining: float
    iht_reduction_opportunities: list[dict]
    us_estate_tax: float
    warnings: list[str]


class HealthcareYearRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    year: int
    person_id: str
    age: int
    phase_label: str
    annual_cost: float
    cumulative: float
    jurisdiction: str


class HealthcareResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rows: list[HealthcareYearRowOut]
    total_lifetime_cost: float
    peak_year_cost: float
    peak_year: int
    by_person: dict[str, float]
    care_home_cost: float
    nhs_vs_private_saving: float
    warnings: list[str]


class HoldingClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    holding_id: str
    holding_name: str
    value: float
    asset_class: str
    instrument_type: str


class RebalanceAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    account_id: str
    account_name: str
    total_value: float
    current_allocation: dict[str, float]
    target_allocation: dict[str, float]
    drift: dict[str, float]
    max_drift: float
    status: str
    trades_needed: dict[str, float]
    holdings: list[HoldingClassificationOut]
    glide_adjusted: bool
    warnings: list[str]


class RebalanceResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    alerts: list[RebalanceAlertOut]
    global_allocation: dict[str, float]
    global_target: dict[str, float]
    global_drift: dict[str, float]
    accounts_needing_action: list[str]
    total_portfolio_value: float
    warnings: list[str]


class AdvancedPlanningReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scenario_id: str
    survivor_james: Optional[SurvivorResultOut]
    survivor_sarah: Optional[SurvivorResultOut]
    estate: EstateResultOut
    healthcare: HealthcareResultOut
    rebalancing: RebalanceResultOut
    warnings: list[str]


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _survivor_out(r: SurvivorResult) -> SurvivorResultOut:
    """@brief Convert SurvivorResult dataclass to Pydantic output."""
    return SurvivorResultOut(
        deceased_person_id=r.deceased_person_id,
        death_year=r.death_year,
        income_lost=[SurvivorIncomeImpactOut(**vars(i)) for i in r.income_lost],
        total_income_lost=r.total_income_lost,
        survivor_gross_income=r.survivor_gross_income,
        survivor_pension_income=r.survivor_pension_income,
        expense_reduction=r.expense_reduction,
        mortgage_affordability=(
            MortgageAffordabilityOut(**vars(r.mortgage_affordability))
            if r.mortgage_affordability else None
        ),
        recommended_life_cover=r.recommended_life_cover,
        life_cover_breakdown=r.life_cover_breakdown,
        key_risks=r.key_risks,
        recommendations=r.recommendations,
        warnings=r.warnings,
    )


def _estate_out(r: EstateResult) -> EstateResultOut:
    """@brief Convert EstateResult dataclass to Pydantic output."""
    return EstateResultOut(
        calculation_year=r.calculation_year,
        gross_estate=r.gross_estate,
        pension_outside_estate=r.pension_outside_estate,
        gifts_outside_estate=r.gifts_outside_estate,
        net_estate=r.net_estate,
        nrb_available=r.nrb_available,
        rnrb_available=r.rnrb_available,
        total_allowances=r.total_allowances,
        taxable_estate=r.taxable_estate,
        iht_liability=r.iht_liability,
        net_to_beneficiaries=r.net_to_beneficiaries,
        effective_iht_rate=r.effective_iht_rate,
        gift_tracker=[GiftRecordOut(**vars(g)) for g in r.gift_tracker],
        gift_iht_at_risk=r.gift_iht_at_risk,
        annual_gift_allowance_remaining=r.annual_gift_allowance_remaining,
        iht_reduction_opportunities=r.iht_reduction_opportunities,
        us_estate_tax=r.us_estate_tax,
        warnings=r.warnings,
    )


def _hc_out(r: HealthcareResult) -> HealthcareResultOut:
    """@brief Convert HealthcareResult dataclass to Pydantic output."""
    return HealthcareResultOut(
        rows=[HealthcareYearRowOut(**vars(row)) for row in r.rows],
        total_lifetime_cost=r.total_lifetime_cost,
        peak_year_cost=r.peak_year_cost,
        peak_year=r.peak_year,
        by_person=r.by_person,
        care_home_cost=r.care_home_cost,
        nhs_vs_private_saving=r.nhs_vs_private_saving,
        warnings=r.warnings,
    )


def _rb_out(r: RebalanceResult) -> RebalanceResultOut:
    """@brief Convert RebalanceResult dataclass to Pydantic output."""
    def _alert_out(a: RebalanceAlert) -> RebalanceAlertOut:
        return RebalanceAlertOut(
            account_id=a.account_id, account_name=a.account_name,
            total_value=a.total_value,
            current_allocation=a.current_allocation,
            target_allocation=a.target_allocation,
            drift=a.drift, max_drift=a.max_drift, status=a.status,
            trades_needed=a.trades_needed,
            holdings=[HoldingClassificationOut(**vars(h)) for h in a.holdings],
            glide_adjusted=a.glide_adjusted, warnings=a.warnings,
        )
    return RebalanceResultOut(
        alerts=[_alert_out(a) for a in r.alerts],
        global_allocation=r.global_allocation,
        global_target=r.global_target,
        global_drift=r.global_drift,
        accounts_needing_action=r.accounts_needing_action,
        total_portfolio_value=r.total_portfolio_value,
        warnings=r.warnings,
    )


def _report_out(r: AdvancedPlanningReport) -> AdvancedPlanningReportOut:
    """@brief Convert AdvancedPlanningReport to Pydantic output."""
    return AdvancedPlanningReportOut(
        scenario_id=r.scenario_id,
        survivor_james=_survivor_out(r.survivor_james) if r.survivor_james else None,
        survivor_sarah=_survivor_out(r.survivor_sarah) if r.survivor_sarah else None,
        estate=_estate_out(r.estate),
        healthcare=_hc_out(r.healthcare),
        rebalancing=_rb_out(r.rebalancing),
        warnings=r.warnings,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_engine(request: Request) -> AdvancedPlanningEngine:
    """
    @brief Load or re-use the AdvancedPlanningEngine from app state.

    @param request  FastAPI request.
    @return         AdvancedPlanningEngine.
    """
    if hasattr(request.app.state, "planning_engine"):
        return request.app.state.planning_engine
    root = getattr(request.app.state, "project_root", ".")
    cfg_path = os.path.join(root, "config", "planning", "planning_config.yaml")
    try:
        cfg = load_planning_config(cfg_path)
    except FileNotFoundError:
        logger.warning("planning_config.yaml not found — using defaults.")
        cfg = PlanningConfig()
    engine = AdvancedPlanningEngine(cfg)
    request.app.state.planning_engine = engine
    return engine


def _load_scenario(request: Request, scenario_path: str):
    """
    @brief Load a scenario from a path relative to project root.

    @param request        FastAPI request.
    @param scenario_path  Relative path.
    @return               Scenario object.
    @raises HTTPException 404 / 500.
    """
    root = getattr(request.app.state, "project_root", ".")
    abs_path = os.path.join(root, scenario_path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_path}")
    try:
        sc = load_scenario_from_file(abs_path)
        if sc is None:
            raise ValueError("Parser returned None")
        return sc
    except Exception as exc:
        logger.error("Failed to load scenario '%s': %s", scenario_path, exc)
        raise HTTPException(status_code=500, detail=f"Failed to parse scenario: {exc}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/planning/report", response_model=AdvancedPlanningReportOut)
def get_planning_report(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    projection_year: Optional[int] = Query(default=None),
    projection_end_year: Optional[int] = Query(default=None),
) -> AdvancedPlanningReportOut:
    """
    @brief Run all four Phase 5 analyses and return the combined report.

    @param request              FastAPI Request.
    @param scenario_path        Relative path to scenario YAML.
    @param projection_year      Estate calculation year (default: current year).
    @param projection_end_year  Healthcare projection end year (default: +40yr).
    @return                     AdvancedPlanningReportOut JSON.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        report = engine.full_report(scenario, projection_year, projection_end_year)
        return _report_out(report)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_planning_report error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/planning/survivor", response_model=SurvivorResultOut)
def get_survivor(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    deceased_person_id: str = Query(default="james", description="ID of the person who dies."),
    death_year: int = Query(default=2060, description="Calendar year of death."),
) -> SurvivorResultOut:
    """
    @brief Model the financial impact of one partner's death.

    @param request             FastAPI Request.
    @param scenario_path       Relative path to scenario YAML.
    @param deceased_person_id  Person ID of the deceased partner.
    @param death_year          Year of death.
    @return                    SurvivorResultOut JSON.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        result = engine._survivor.simulate(scenario, deceased_person_id, death_year)
        return _survivor_out(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_survivor error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/planning/estate", response_model=EstateResultOut)
def get_estate(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    projection_year: Optional[int] = Query(default=None),
    has_surviving_partner: bool = Query(default=True),
    owns_residence: bool = Query(default=True),
) -> EstateResultOut:
    """
    @brief Calculate estate value and IHT liability.

    @param request               FastAPI Request.
    @param scenario_path         Relative path to scenario YAML.
    @param projection_year       Year for the calculation.
    @param has_surviving_partner True if NRB can be transferred from deceased spouse.
    @param owns_residence        True if main residence passes to direct descendants.
    @return                      EstateResultOut JSON.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        result = engine._estate.calculate(
            scenario, projection_year, has_surviving_partner, owns_residence
        )
        return _estate_out(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_estate error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/planning/healthcare", response_model=HealthcareResultOut)
def get_healthcare(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    start_year: Optional[int] = Query(default=None),
    end_year: Optional[int] = Query(default=None),
) -> HealthcareResultOut:
    """
    @brief Project healthcare costs year by year.

    @param request        FastAPI Request.
    @param scenario_path  Relative path to scenario YAML.
    @param start_year     First projection year (default: current year).
    @param end_year       Last projection year (default: start_year + 40).
    @return               HealthcareResultOut JSON.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        yr = start_year or date.today().year
        end = end_year or (yr + 40)
        result = engine._healthcare.project(scenario, yr, end)
        return _hc_out(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_healthcare error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/planning/rebalancing", response_model=RebalanceResultOut)
def get_rebalancing(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    owner_age: int = Query(default=45, description="Primary holder's age for glide-path."),
) -> RebalanceResultOut:
    """
    @brief Analyse portfolio drift and return rebalancing recommendations.

    @param request        FastAPI Request.
    @param scenario_path  Relative path to scenario YAML.
    @param owner_age      Primary holder's current age.
    @return               RebalanceResultOut JSON.
    """
    try:
        engine = _load_engine(request)
        scenario = _load_scenario(request, scenario_path)
        result = engine._rebalance.analyse(scenario, owner_age)
        return _rb_out(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_rebalancing error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})
