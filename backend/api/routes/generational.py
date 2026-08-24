"""
@file generational.py
@brief FastAPI routes for Phase 7 generational & cross-jurisdiction planning.

Endpoints:
  GET  /api/generational/offspring        — project all offspring for one career/country
  GET  /api/generational/career-paths     — list all 10 career archetypes with salary curves
  GET  /api/generational/compare          — UK vs US parent path comparison matrix
  GET  /api/generational/university       — university cost breakdown (UK Plan 5 vs US 529)
  GET  /api/generational/family-timeline  — combined parents + offspring wealth 2026–2109
  GET  /api/generational/estate-handoff   — estate tax comparison UK IHT vs US estate tax
  GET  /api/generational/report           — full Phase 7 combined report
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from backend.engine.generational_engine import (
    GenerationalEngine,
    GenerationalResult,
    OffspringProjection,
    OffspringYearSnapshot,
    UniversityCostSummary,
    WealthTransfer,
    load_generational_config,
)
from backend.engine.country_comparison_engine import (
    ComparisonKeyAge,
    CountryComparisonEngine,
    CountryComparisonResult,
    CountryPathResult,
    CountryYearSnapshot,
    build_uk_path_config,
    build_us_path_config,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class OffspringYearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    year: int; age: int; country: str; career_phase: str
    gross_salary: float; income_tax: float; ni_fica: float; net_income: float
    student_loan_repayment: float; healthcare_cost: float
    savings_contributed: float; isa_value: float; pension_value: float
    taxable_value: float; total_net_worth: float
    fire_achieved: bool; loan_balance: float

class UniversityCostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    country: str; duration_years: int; total_tuition: float
    total_living: float; parental_outlay: float; loan_taken: float
    loan_balance_at_graduation: float; projected_loan_repayment_years: float
    projected_loan_write_off: bool

class OffspringProjectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    offspring_id: str; name: str; career_path: str; country: str
    years: list[OffspringYearOut]
    fire_year: Optional[int]; fire_age: Optional[int]
    peak_net_worth: float; peak_net_worth_year: int
    university_cost: UniversityCostOut
    lifetime_tax: float; lifetime_earnings: float

class WealthTransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    transfer_year: int; gross_estate_gbp: float; gross_estate_usd: float
    pension_outside_gbp: float; iht_liability_gbp: float
    us_estate_tax_usd: float; net_to_offspring_gbp: float
    net_to_offspring_usd: float; fx_rate: float; notes: str

class GenerationalResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    country: str; macro_scenario: str
    parent_wealth_by_year: dict[int, float]
    offspring_projections: list[OffspringProjectionOut]
    wealth_transfer: WealthTransferOut
    combined_family_wealth: dict[int, float]
    fire_years: dict[str, Optional[int]]
    investment_tax_drag: float; warnings: list[str]

class CountryYearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    year: int; age_primary: int; country: str
    gross_income: float; income_tax: float; pension_contrib: float
    net_income: float; living_cost: float; housing_cost: float
    healthcare_cost: float; savings: float
    portfolio_value: float; pension_value: float; property_value: float
    total_wealth: float; total_wealth_gbp: float; fire_coverage: float
    state_pension_income: float; phase: str

class CountryPathOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    path_id: str; label: str; country: str
    years: list[CountryYearOut]
    retire_year: int; fire_year: Optional[int]
    wealth_at_retirement: float; wealth_at_death: float
    lifetime_income_tax: float; lifetime_healthcare: float
    total_housing_cost: float; currency: str; fx_rate: float

class ComparisonKeyAgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    year: int; age: int
    uk_wealth_gbp: float; us_wealth_gbp: float; delta_gbp: float
    uk_annual_tax: float; us_annual_tax_gbp: float
    uk_healthcare: float; us_healthcare_gbp: float

class BreakEvenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    break_even_year: Optional[int]
    leading_path_early: str; leading_path_late: str
    uk_wealth_at_bey: float; us_wealth_at_bey: float

class ComparisonResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uk_path: CountryPathOut; us_path: CountryPathOut
    key_ages: list[ComparisonKeyAgeOut]
    break_even: BreakEvenOut
    uk_estate_gbp: float; us_estate_gbp: float
    us_advantage_at_retirement_gbp: float
    lifetime_tax_delta_gbp: float; lifetime_healthcare_delta_gbp: float
    warnings: list[str]

class CareerPathSummaryOut(BaseModel):
    career_id: str; label: str; ceiling: str
    uk_entry: float; uk_peak: float; uk_entry_age: int
    us_entry: float; us_peak: float; us_entry_age: int

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_gen_engine(request: Request) -> GenerationalEngine:
    """@brief Load or cache the GenerationalEngine from app state."""
    if hasattr(request.app.state, "generational_engine"):
        return request.app.state.generational_engine
    root = getattr(request.app.state, "project_root", ".")
    cfg_path = os.path.join(root, "config", "generational", "generational_config.yaml")
    try:
        cfg = load_generational_config(cfg_path)
    except FileNotFoundError:
        logger.warning("generational_config.yaml not found — using empty dict")
        cfg = {"generational": {}}
    engine = GenerationalEngine(cfg)
    request.app.state.generational_engine = engine
    return engine

def _load_cfg(request: Request) -> dict:
    """@brief Load raw generational config dict."""
    if hasattr(request.app.state, "generational_config"):
        return request.app.state.generational_config
    root = getattr(request.app.state, "project_root", ".")
    cfg_path = os.path.join(root, "config", "generational", "generational_config.yaml")
    try:
        cfg = load_generational_config(cfg_path)
    except FileNotFoundError:
        cfg = {"generational": {}}
    request.app.state.generational_config = cfg
    return cfg

def _proj_to_out(proj: OffspringProjection) -> OffspringProjectionOut:
    return OffspringProjectionOut(
        offspring_id=proj.offspring_id, name=proj.name,
        career_path=proj.career_path, country=proj.country,
        years=[OffspringYearOut(**vars(s)) for s in proj.years],
        fire_year=proj.fire_year, fire_age=proj.fire_age,
        peak_net_worth=proj.peak_net_worth,
        peak_net_worth_year=proj.peak_net_worth_year,
        university_cost=UniversityCostOut(**vars(proj.university_cost)),
        lifetime_tax=proj.lifetime_tax, lifetime_earnings=proj.lifetime_earnings,
    )

def _path_to_out(path: CountryPathResult) -> CountryPathOut:
    return CountryPathOut(
        path_id=path.path_id, label=path.label, country=path.country,
        years=[CountryYearOut(**vars(s)) for s in path.years],
        retire_year=path.retire_year, fire_year=path.fire_year,
        wealth_at_retirement=path.wealth_at_retirement,
        wealth_at_death=path.wealth_at_death,
        lifetime_income_tax=path.lifetime_income_tax,
        lifetime_healthcare=path.lifetime_healthcare,
        total_housing_cost=path.total_housing_cost,
        currency=path.currency, fx_rate=path.fx_rate,
    )

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/generational/offspring", response_model=list[OffspringProjectionOut])
def get_offspring_projections(
    request: Request,
    country: str = Query(default="uk", pattern="^(uk|us)$"),
    macro_scenario: str = Query(default="mid", pattern="^(low|mid|high)$"),
    career_path_id: Optional[str] = Query(default=None),
    parent_wealth_gbp: float = Query(default=0.0),
    parent_pension_gbp: float = Query(default=0.0),
    parent_property_gbp: float = Query(default=0.0),
    parent_mortgage_gbp: float = Query(default=0.0),
    parent_death_year: int = Query(default=2070),
    fx_scenario: str = Query(default="mid", pattern="^(low|mid|high)$"),
) -> list[OffspringProjectionOut]:
    """
    @brief Project all configured offspring for a given country path and macro scenario.

    @param country            'uk' | 'us'.
    @param macro_scenario     'low' | 'mid' | 'high'.
    @param career_path_id     Override career path for all offspring.
    @param parent_*           Parent wealth at projection start (used for inheritance).
    @param parent_death_year  Year of estate transfer.
    @param fx_scenario        FX rate scenario 'low' | 'mid' | 'high'.
    @return                   List of OffspringProjectionOut.
    """
    try:
        engine = _load_gen_engine(request)
        result = engine.run(
            country=country, macro_scenario=macro_scenario,
            parent_wealth_gbp=parent_wealth_gbp,
            parent_pension_gbp=parent_pension_gbp,
            parent_property_gbp=parent_property_gbp,
            parent_mortgage_gbp=parent_mortgage_gbp,
            parent_death_year=parent_death_year,
            fx_scenario=fx_scenario,
        )
        return [_proj_to_out(p) for p in result.offspring_projections]
    except Exception as exc:
        logger.error("get_offspring_projections: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/generational/career-paths", response_model=list[CareerPathSummaryOut])
def get_career_paths(request: Request) -> list[CareerPathSummaryOut]:
    """
    @brief List all configured career paths with UK and US salary summaries.

    @return  List of CareerPathSummaryOut.
    """
    try:
        engine = _load_gen_engine(request)
        return [
            CareerPathSummaryOut(
                career_id=cp.career_id, label=cp.label, ceiling=cp.ceiling,
                uk_entry=cp.uk.entry_salary, uk_peak=cp.uk.peak_salary,
                uk_entry_age=cp.uk.entry_age,
                us_entry=cp.us.entry_salary, us_peak=cp.us.peak_salary,
                us_entry_age=cp.us.entry_age,
            )
            for cp in engine._career_paths.values()
        ]
    except Exception as exc:
        logger.error("get_career_paths: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/generational/compare", response_model=ComparisonResultOut)
def get_country_comparison(
    request: Request,
    macro_scenario: str = Query(default="mid", pattern="^(low|mid|high)$"),
    fx_scenario: str = Query(default="mid", pattern="^(low|mid|high)$"),
    birth_year: int = Query(default=1980),
) -> ComparisonResultOut:
    """
    @brief Run UK vs US parallel projection and return the comparison matrix.

    @param macro_scenario  'low' | 'mid' | 'high'.
    @param fx_scenario     FX rate scenario.
    @param birth_year      Primary person's birth year (for age calculation).
    @return                ComparisonResultOut.
    """
    try:
        from backend.engine.generational_engine import GenerationalMacro
        cfg = _load_cfg(request)
        raw_mac = cfg.get("generational", {}).get("country_macro", {})

        def macro(country_key: str) -> GenerationalMacro:
            r = raw_mac.get(country_key, {}).get(macro_scenario, {})
            return GenerationalMacro(
                inflation=float(r.get("inflation", 0.025)),
                equity_real_return=float(r.get("equity_real_return", 0.05)),
                salary_real_growth=float(r.get("salary_real_growth", 0.01)),
                healthcare_annual=float(r.get("healthcare_working", r.get("annual_healthcare_cost", 0))),
                healthcare_aca_bridge=float(r.get("healthcare_aca_bridge", 0)),
                healthcare_medicare=float(r.get("healthcare_medicare", 0)),
                healthcare_late_life=float(r.get("healthcare_late_life", 0)),
            )

        fx_map = cfg.get("generational", {}).get("fx", {}).get("scenarios", {})
        fx = float(fx_map.get(fx_scenario, 1.27))

        uk_cfg = build_uk_path_config(cfg, fx_rate=fx)
        us_cfg = build_us_path_config(cfg, fx_rate=fx)

        comp_engine = CountryComparisonEngine(macro("UK"), macro("US"))
        result = comp_engine.compare(uk_cfg, us_cfg, birth_year_primary=birth_year)

        def _ka_out(k: ComparisonKeyAge) -> ComparisonKeyAgeOut:
            return ComparisonKeyAgeOut(**vars(k))

        return ComparisonResultOut(
            uk_path=_path_to_out(result.uk_path),
            us_path=_path_to_out(result.us_path),
            key_ages=[_ka_out(k) for k in result.key_ages],
            break_even=BreakEvenOut(**vars(result.break_even)),
            uk_estate_gbp=result.uk_estate_gbp,
            us_estate_gbp=result.us_estate_gbp,
            us_advantage_at_retirement_gbp=result.us_advantage_at_retirement_gbp,
            lifetime_tax_delta_gbp=result.lifetime_tax_delta_gbp,
            lifetime_healthcare_delta_gbp=result.lifetime_healthcare_delta_gbp,
            warnings=result.warnings,
        )
    except Exception as exc:
        logger.error("get_country_comparison: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/generational/university", response_model=dict)
def get_university_costs(
    request: Request,
    country: str = Query(default="uk", pattern="^(uk|us)$"),
    offspring_id: Optional[str] = Query(default=None),
) -> dict:
    """
    @brief Return university cost breakdown for UK (Plan 5) or US (529 plan).

    @param country      'uk' | 'us'.
    @param offspring_id  Optional: limit to one offspring.
    @return              Dict with cost breakdown and parental outlay.
    """
    try:
        engine = _load_gen_engine(request)
        cfg = engine._uni_cfg
        if country == "uk":
            from backend.engine.generational_engine import calculate_uk_university_cost
            summary = calculate_uk_university_cost(cfg, duration=3)
        else:
            from backend.engine.generational_engine import calculate_us_university_cost
            summary = calculate_us_university_cost(cfg, duration=4)
        return vars(summary)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/generational/family-timeline", response_model=dict)
def get_family_timeline(
    request: Request,
    country: str = Query(default="uk", pattern="^(uk|us)$"),
    macro_scenario: str = Query(default="mid", pattern="^(low|mid|high)$"),
    parent_wealth_gbp: float = Query(default=0.0),
    parent_pension_gbp: float = Query(default=0.0),
    parent_property_gbp: float = Query(default=0.0),
    parent_death_year: int = Query(default=2070),
) -> dict:
    """
    @brief Return combined family wealth timeline (parents + offspring) year by year.

    @param country          'uk' | 'us'.
    @param macro_scenario   'low' | 'mid' | 'high'.
    @param parent_*         Parent asset values.
    @param parent_death_year  Year of estate handoff.
    @return                 Dict with years, parent_wealth, offspring_wealth, combined.
    """
    try:
        engine = _load_gen_engine(request)
        result = engine.run(
            country=country, macro_scenario=macro_scenario,
            parent_wealth_gbp=parent_wealth_gbp,
            parent_pension_gbp=parent_pension_gbp,
            parent_property_gbp=parent_property_gbp,
            parent_death_year=parent_death_year,
        )
        years = sorted(result.combined_family_wealth.keys())
        return {
            "years": years,
            "combined_family_wealth": [result.combined_family_wealth[y] for y in years],
            "parent_wealth": [result.parent_wealth_by_year.get(y, 0) for y in years],
            "offspring_wealth": [
                sum(
                    s.total_net_worth
                    for p in result.offspring_projections
                    for s in p.years if s.year == y
                )
                for y in years
            ],
            "fire_years": result.fire_years,
            "wealth_transfer": vars(result.wealth_transfer),
            "warnings": result.warnings,
        }
    except Exception as exc:
        logger.error("get_family_timeline: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/generational/estate-handoff", response_model=WealthTransferOut)
def get_estate_handoff(
    request: Request,
    parent_wealth_gbp: float = Query(default=5_500_000.0),
    parent_pension_gbp: float = Query(default=0.0),
    parent_property_gbp: float = Query(default=800_000.0),
    parent_mortgage_gbp: float = Query(default=0.0),
    death_year: int = Query(default=2070),
    has_surviving_partner: bool = Query(default=False),
    fx_scenario: str = Query(default="mid", pattern="^(low|mid|high)$"),
) -> WealthTransferOut:
    """
    @brief Compute estate handoff to offspring under UK IHT and US estate tax.

    @param parent_wealth_gbp    Total portfolio value (GBP).
    @param parent_pension_gbp   SIPP value (may be excluded from estate).
    @param parent_property_gbp  Property value.
    @param parent_mortgage_gbp  Outstanding mortgage balance.
    @param death_year           Calendar year of death.
    @param has_surviving_partner  True = combined NRB applied.
    @param fx_scenario          'low' | 'mid' | 'high'.
    @return                     WealthTransferOut.
    """
    try:
        from backend.engine.generational_engine import calculate_wealth_transfer
        engine = _load_gen_engine(request)
        cfg = _load_cfg(request)
        fx_map = cfg.get("generational", {}).get("fx", {}).get("scenarios", {})
        fx = float(fx_map.get(fx_scenario, 1.27))
        transfer = calculate_wealth_transfer(
            parent_wealth_gbp=parent_wealth_gbp,
            pension_value_gbp=parent_pension_gbp,
            property_value_gbp=parent_property_gbp,
            mortgage_balance_gbp=parent_mortgage_gbp,
            death_year=death_year,
            estate_cfg=engine._estate_cfg,
            fx_rate=fx,
            has_surviving_partner=has_surviving_partner,
        )
        return WealthTransferOut(**vars(transfer))
    except Exception as exc:
        logger.error("get_estate_handoff: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/generational/report", response_model=dict)
def get_generational_report(
    request: Request,
    macro_scenario: str = Query(default="mid", pattern="^(low|mid|high)$"),
    fx_scenario: str = Query(default="mid", pattern="^(low|mid|high)$"),
    birth_year: int = Query(default=1980),
    parent_wealth_gbp: float = Query(default=0.0),
    parent_pension_gbp: float = Query(default=0.0),
    parent_property_gbp: float = Query(default=0.0),
    parent_mortgage_gbp: float = Query(default=0.0),
    parent_death_year: int = Query(default=2070),
) -> dict:
    """
    @brief Full Phase 7 combined report — both country paths + offspring projections.

    @return  Dict with uk_result, us_result, comparison, career_paths, warnings.
    """
    try:
        from backend.engine.generational_engine import GenerationalMacro
        engine = _load_gen_engine(request)
        cfg = _load_cfg(request)
        fx_map = cfg.get("generational", {}).get("fx", {}).get("scenarios", {})
        fx = float(fx_map.get(fx_scenario, 1.27))

        # Run offspring for both country paths
        uk_result = engine.run(
            country="uk", macro_scenario=macro_scenario,
            parent_wealth_gbp=parent_wealth_gbp,
            parent_pension_gbp=parent_pension_gbp,
            parent_property_gbp=parent_property_gbp,
            parent_mortgage_gbp=parent_mortgage_gbp,
            parent_death_year=parent_death_year,
            fx_scenario=fx_scenario,
        )
        us_result = engine.run(
            country="us", macro_scenario=macro_scenario,
            parent_wealth_gbp=parent_wealth_gbp,
            parent_pension_gbp=parent_pension_gbp,
            parent_property_gbp=parent_property_gbp,
            parent_mortgage_gbp=parent_mortgage_gbp,
            parent_death_year=parent_death_year,
            fx_scenario=fx_scenario,
        )

        career_paths = [
            {
                "career_id": cp.career_id, "label": cp.label,
                "uk_entry": cp.uk.entry_salary, "uk_peak": cp.uk.peak_salary,
                "us_entry": cp.us.entry_salary, "us_peak": cp.us.peak_salary,
            }
            for cp in engine._career_paths.values()
        ]

        # Comparison
        raw_mac = cfg.get("generational", {}).get("country_macro", {})
        def macro(country_key: str) -> GenerationalMacro:
            r = raw_mac.get(country_key, {}).get(macro_scenario, {})
            return GenerationalMacro(
                inflation=float(r.get("inflation", 0.025)),
                equity_real_return=float(r.get("equity_real_return", 0.05)),
                salary_real_growth=float(r.get("salary_real_growth", 0.01)),
                healthcare_annual=float(r.get("healthcare_working", 0)),
                healthcare_aca_bridge=float(r.get("healthcare_aca_bridge", 0)),
                healthcare_medicare=float(r.get("healthcare_medicare", 0)),
                healthcare_late_life=float(r.get("healthcare_late_life", 0)),
            )

        uk_cfg = build_uk_path_config(cfg, fx_rate=fx)
        us_cfg = build_us_path_config(cfg, fx_rate=fx)
        comp_engine = CountryComparisonEngine(macro("UK"), macro("US"))
        comparison = comp_engine.compare(uk_cfg, us_cfg, birth_year_primary=birth_year)

        def _proj_summary(proj: OffspringProjection) -> dict:
            return {
                "offspring_id": proj.offspring_id, "name": proj.name,
                "career_path": proj.career_path, "country": proj.country,
                "fire_year": proj.fire_year, "fire_age": proj.fire_age,
                "peak_net_worth": proj.peak_net_worth,
                "lifetime_tax": proj.lifetime_tax,
                "lifetime_earnings": proj.lifetime_earnings,
                "university_cost": vars(proj.university_cost),
                "wealth_at_key_years": {
                    s.year: s.total_net_worth
                    for s in proj.years
                    if s.year % 10 == 0
                },
            }

        return {
            "macro_scenario": macro_scenario,
            "fx_scenario": fx_scenario,
            "fx_rate": fx,
            "uk_offspring": [_proj_summary(p) for p in uk_result.offspring_projections],
            "us_offspring": [_proj_summary(p) for p in us_result.offspring_projections],
            "uk_wealth_transfer": vars(uk_result.wealth_transfer),
            "us_wealth_transfer": vars(us_result.wealth_transfer),
            "comparison_key_ages": [vars(k) for k in comparison.key_ages],
            "break_even_year": comparison.break_even.break_even_year,
            "uk_estate_net_gbp": comparison.uk_estate_gbp,
            "us_estate_net_gbp": comparison.us_estate_gbp,
            "us_advantage_at_retirement_gbp": comparison.us_advantage_at_retirement_gbp,
            "lifetime_tax_delta_gbp": comparison.lifetime_tax_delta_gbp,
            "lifetime_healthcare_delta_gbp": comparison.lifetime_healthcare_delta_gbp,
            "career_paths": career_paths,
            "warnings": uk_result.warnings + us_result.warnings + comparison.warnings,
        }
    except Exception as exc:
        logger.error("get_generational_report: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})
