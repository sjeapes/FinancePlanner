"""
@file tax_optimiser.py (routes)
@brief FastAPI routes for Phase 8 tax optimisation.

Endpoints
---------
GET /api/tax-optimiser/summary
    Run all three strategies and return the combined summary with total
    lifetime saving and top action list.

GET /api/tax-optimiser/band-fill
    Year-by-year optimal vs naive pension/ISA drawdown schedule.

GET /api/tax-optimiser/ufpls
    UFPLS vs PCLS strategy comparison over the full retirement period.

GET /api/tax-optimiser/cgt-harvest
    Annual CGT harvest schedule for the GIA.

GET /api/tax-optimiser/config
    Return the active optimiser config (for the Settings screen).

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from backend.engine.tax_optimiser import (
    BandFillResult, BandFillYear,
    CGTHarvestResult, CGTHarvestYear,
    TaxOptimiser, TaxOptimiserSummary,
    UFPLSResult, UFPLSYear,
    load_optimiser_config,
)
from backend.persistence.yaml_serialiser import load_yaml

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────────────────────────


class BandFillYearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    year: int; age: int; target_spending: float; other_income: float
    band_space_pa: float; band_space_basic: float
    pension_drawn_opt: float; pension_drawn_naive: float
    isa_drawn_opt: float; isa_drawn_naive: float
    tax_opt: float; tax_naive: float; tax_saved: float
    pension_pot_opt: float; pension_pot_naive: float
    isa_pot_opt: float; isa_pot_naive: float
    action: str


class BandFillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    years: list[BandFillYearOut]
    lifetime_tax_opt: float; lifetime_tax_naive: float; lifetime_tax_saved: float
    isa_exhausted_year_opt: Optional[int]; isa_exhausted_year_naive: Optional[int]
    pension_exhausted_year_opt: Optional[int]; pension_exhausted_year_naive: Optional[int]
    warnings: list[str]


class UFPLSYearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    year: int; age: int; withdrawal_target: float
    ufpls_gross: float; ufpls_tax_free: float; ufpls_taxable: float
    ufpls_tax: float; ufpls_net: float; ufpls_pot: float
    pcls_gross: float; pcls_tax: float; pcls_net: float
    pcls_drawdown_pot: float; pcls_lump_pot: float
    ufpls_total_wealth: float; pcls_total_wealth: float; delta: float


class UFPLSOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pcls_lump_sum: float; starting_pot: float
    years: list[UFPLSYearOut]
    lifetime_tax_ufpls: float; lifetime_tax_pcls: float
    terminal_wealth_ufpls: float; terminal_wealth_pcls: float
    preferred_strategy: str; tax_saving_gbp: float
    warnings: list[str]


class CGTYearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    year: int; gia_value: float; cost_basis: float
    unrealised_gain: float; exempt_remaining: float
    harvest_amount: float; cgt_if_harvested: float
    cgt_if_not_harvested: float; trade_cost: float
    net_saving: float; action: str; recommendation: str


class CGTHarvestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    years: list[CGTYearOut]
    total_cgt_without: float; total_cgt_with: float
    total_lifetime_saving: float; total_trade_costs: float
    net_saving: float; harvest_years: list[int]
    warnings: list[str]


class TaxOptimiserSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    band_fill_saving_gbp: float
    ufpls_saving_gbp: float
    cgt_harvest_saving_gbp: float
    total_saving_gbp: float
    top_actions: list[str]
    band_fill: Optional[BandFillOut]
    ufpls: Optional[UFPLSOut]
    cgt_harvest: Optional[CGTHarvestOut]
    warnings: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _load_optimiser(request: Request) -> TaxOptimiser:
    """@brief Load (or return cached) TaxOptimiser from app state."""
    if hasattr(request.app.state, "tax_optimiser"):
        return request.app.state.tax_optimiser
    root = getattr(request.app.state, "project_root", ".")
    cfg_path = os.path.join(root, "config", "tax", "optimiser_config.yaml")
    try:
        cfg = load_optimiser_config(cfg_path)
    except FileNotFoundError:
        logger.warning("optimiser_config.yaml not found — using defaults")
        cfg = {"tax_optimiser": {}}
    optimiser = TaxOptimiser(cfg)
    request.app.state.tax_optimiser = optimiser
    return optimiser


def _load_scenario(request: Request, scenario_path: str) -> dict:
    """@brief Load scenario YAML dict."""
    root = getattr(request.app.state, "project_root", ".")
    abs_path = (scenario_path if os.path.isabs(scenario_path)
                else os.path.join(root, scenario_path))
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_path}")
    try:
        raw = load_yaml(abs_path)
        return raw.get("scenario", raw)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load scenario: {exc}")


def _bf_to_out(bf: BandFillResult) -> BandFillOut:
    return BandFillOut(
        years=[BandFillYearOut(**{k: v for k, v in vars(y).items()}) for y in bf.years],
        lifetime_tax_opt=bf.lifetime_tax_opt,
        lifetime_tax_naive=bf.lifetime_tax_naive,
        lifetime_tax_saved=bf.lifetime_tax_saved,
        isa_exhausted_year_opt=bf.isa_exhausted_year_opt,
        isa_exhausted_year_naive=bf.isa_exhausted_year_naive,
        pension_exhausted_year_opt=bf.pension_exhausted_year_opt,
        pension_exhausted_year_naive=bf.pension_exhausted_year_naive,
        warnings=bf.warnings,
    )


def _ufpls_to_out(u: UFPLSResult) -> UFPLSOut:
    return UFPLSOut(
        pcls_lump_sum=u.pcls_lump_sum,
        starting_pot=u.starting_pot,
        years=[UFPLSYearOut(**{k: v for k, v in vars(y).items()}) for y in u.years],
        lifetime_tax_ufpls=u.lifetime_tax_ufpls,
        lifetime_tax_pcls=u.lifetime_tax_pcls,
        terminal_wealth_ufpls=u.terminal_wealth_ufpls,
        terminal_wealth_pcls=u.terminal_wealth_pcls,
        preferred_strategy=u.preferred_strategy,
        tax_saving_gbp=u.tax_saving_gbp,
        warnings=u.warnings,
    )


def _cgt_to_out(c: CGTHarvestResult) -> CGTHarvestOut:
    return CGTHarvestOut(
        years=[CGTYearOut(**{k: v for k, v in vars(y).items()}) for y in c.years],
        total_cgt_without=c.total_cgt_without,
        total_cgt_with=c.total_cgt_with,
        total_lifetime_saving=c.total_lifetime_saving,
        total_trade_costs=c.total_trade_costs,
        net_saving=c.net_saving,
        harvest_years=c.harvest_years,
        warnings=c.warnings,
    )


def _summary_to_out(s: TaxOptimiserSummary) -> TaxOptimiserSummaryOut:
    return TaxOptimiserSummaryOut(
        band_fill_saving_gbp=s.band_fill_saving_gbp,
        ufpls_saving_gbp=s.ufpls_saving_gbp,
        cgt_harvest_saving_gbp=s.cgt_harvest_saving_gbp,
        total_saving_gbp=s.total_saving_gbp,
        top_actions=s.top_actions,
        band_fill=_bf_to_out(s.band_fill) if s.band_fill else None,
        ufpls=_ufpls_to_out(s.ufpls) if s.ufpls else None,
        cgt_harvest=_cgt_to_out(s.cgt_harvest) if s.cgt_harvest else None,
        warnings=s.warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/tax-optimiser/summary", response_model=TaxOptimiserSummaryOut)
def get_tax_optimiser_summary(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
) -> TaxOptimiserSummaryOut:
    """
    @brief Run all enabled optimisers and return the combined summary.

    Returns total lifetime tax saving across band-filling, UFPLS/PCLS
    strategy selection, and CGT harvest scheduling.

    @param scenario_path  Relative path to the scenario YAML.
    @return               TaxOptimiserSummaryOut with total saving and actions.
    """
    try:
        optimiser = _load_optimiser(request)
        scenario  = _load_scenario(request, scenario_path)
        result    = optimiser.run(scenario)
        return _summary_to_out(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_tax_optimiser_summary: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/tax-optimiser/band-fill", response_model=BandFillOut)
def get_band_fill(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    target_band: str = Query(default="basic_rate",
                             pattern="^(personal_allowance|basic_rate|higher_rate)$"),
) -> BandFillOut:
    """
    @brief Return the year-by-year band-fill drawdown schedule.

    Computes optimal pension drawdown (filling the target tax band) vs
    naive proportional drawdown, and reports tax saved per year.

    @param scenario_path  Relative path to the scenario YAML.
    @param target_band    'personal_allowance' | 'basic_rate' | 'higher_rate'.
    @return               BandFillOut with per-year actions and cumulative saving.
    """
    try:
        optimiser = _load_optimiser(request)
        scenario  = _load_scenario(request, scenario_path)
        # Override target band from query param
        optimiser._cfg.get("band_filler", {})["target_band"] = target_band
        result = optimiser.run(scenario)
        if result.band_fill is None:
            raise HTTPException(status_code=422, detail="Band-filler returned no result")
        return _bf_to_out(result.band_fill)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_band_fill: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/tax-optimiser/ufpls", response_model=UFPLSOut)
def get_ufpls_comparison(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
) -> UFPLSOut:
    """
    @brief Return the UFPLS vs PCLS year-by-year comparison.

    @param scenario_path  Relative path to the scenario YAML.
    @return               UFPLSOut with per-year data and preferred strategy.
    """
    try:
        optimiser = _load_optimiser(request)
        scenario  = _load_scenario(request, scenario_path)
        result    = optimiser.run(scenario)
        if result.ufpls is None:
            raise HTTPException(status_code=422, detail="UFPLS returned no result")
        return _ufpls_to_out(result.ufpls)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_ufpls_comparison: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/tax-optimiser/cgt-harvest", response_model=CGTHarvestOut)
def get_cgt_harvest(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
) -> CGTHarvestOut:
    """
    @brief Return the annual CGT harvest schedule for the GIA.

    @param scenario_path  Relative path to the scenario YAML.
    @return               CGTHarvestOut with per-year actions and cumulative saving.
    """
    try:
        optimiser = _load_optimiser(request)
        scenario  = _load_scenario(request, scenario_path)
        result    = optimiser.run(scenario)
        if result.cgt_harvest is None:
            raise HTTPException(status_code=422, detail="No GIA found — CGT harvest not applicable")
        return _cgt_to_out(result.cgt_harvest)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_cgt_harvest: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})


@router.get("/tax-optimiser/config")
def get_optimiser_config(request: Request) -> dict:
    """
    @brief Return the active tax optimiser configuration.

    @return  Dict from optimiser_config.yaml (tax_optimiser key).
    """
    try:
        root = getattr(request.app.state, "project_root", ".")
        cfg_path = os.path.join(root, "config", "tax", "optimiser_config.yaml")
        cfg = load_optimiser_config(cfg_path)
        return cfg.get("tax_optimiser", cfg)
    except FileNotFoundError:
        return {"error": "optimiser_config.yaml not found", "enabled": False}
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)})
