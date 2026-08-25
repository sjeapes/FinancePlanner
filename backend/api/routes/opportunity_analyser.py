"""
@file opportunity_analyser.py (routes)
@brief FastAPI routes for the Phase 10 investment opportunity analyser.

GET /api/analyser/funds
    List the pre-defined fund catalogue (tickers, names, categories).

POST /api/analyser/compare
    Run a DCA comparison across selected funds for a given date range
    and contribution schedule. Returns per-fund portfolio trajectories.
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from backend.engine.opportunity_analyser import (
    analyse_opportunity, FUND_CATALOGUE, FundResult, MonthlySnapshot, OpportunityResult,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class CompareRequest(BaseModel):
    """
    @brief Request body for POST /api/analyser/compare.
    @param tickers               List of Yahoo Finance ticker symbols to compare.
    @param start_date            First investment date (YYYY-MM-DD).
    @param end_date              Last valuation date (YYYY-MM-DD).
    @param initial_lump_sum      One-off investment at start (GBP, default 0).
    @param monthly_contribution  Regular monthly investment (GBP, default 500).
    """
    tickers: list[str] = Field(default=["VWRP.L", "VUSA.L", "IWDA.L"])
    start_date: str = "2018-01-01"
    end_date: str = "2024-12-31"
    initial_lump_sum: float = Field(default=0.0, ge=0)
    monthly_contribution: float = Field(default=500.0, ge=0)


class MonthlySnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date_str: str; units_held: float; price: float
    portfolio_value: float; cumulative_invested: float
    gain: float; gain_pct: float


class FundResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str; name: str; category: str
    total_invested: float; final_value: float; total_gain: float
    total_gain_pct: float; annualised_return: float
    monthly: list[MonthlySnapshotOut]; error: str


class OpportunityResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    start_date: str; end_date: str; initial_lump_sum: float
    monthly_contribution: float; total_invested: float
    funds: list[FundResultOut]; best_fund_ticker: str
    cash_value: float; missed_gain: float; warnings: list[str]


@router.get("/analyser/funds")
def list_funds() -> list[dict]:
    """@brief Return the pre-defined fund catalogue."""
    return FUND_CATALOGUE


@router.post("/analyser/compare", response_model=OpportunityResultOut)
def compare_funds(body: CompareRequest) -> OpportunityResultOut:
    """
    @brief Compare DCA returns across selected ETFs for a date range.
    @param body  CompareRequest with tickers, dates, and contribution schedule.
    @return      OpportunityResultOut with per-fund trajectories and summary.
    """
    if not body.tickers:
        raise HTTPException(status_code=422, detail="At least one ticker required")
    if len(body.tickers) > 6:
        raise HTTPException(status_code=422, detail="Maximum 6 tickers per comparison")
    try:
        result = analyse_opportunity(
            tickers=body.tickers,
            start_date=body.start_date,
            end_date=body.end_date,
            initial_lump_sum=body.initial_lump_sum,
            monthly_contribution=body.monthly_contribution,
        )
        def _snap(s: MonthlySnapshot) -> MonthlySnapshotOut:
            return MonthlySnapshotOut(**vars(s))
        def _fund(f: FundResult) -> FundResultOut:
            return FundResultOut(
                ticker=f.ticker, name=f.name, category=f.category,
                total_invested=f.total_invested, final_value=f.final_value,
                total_gain=f.total_gain, total_gain_pct=f.total_gain_pct,
                annualised_return=f.annualised_return,
                monthly=[_snap(s) for s in f.monthly], error=f.error,
            )
        return OpportunityResultOut(
            start_date=result.start_date, end_date=result.end_date,
            initial_lump_sum=result.initial_lump_sum,
            monthly_contribution=result.monthly_contribution,
            total_invested=result.total_invested,
            funds=[_fund(f) for f in result.funds],
            best_fund_ticker=result.best_fund_ticker,
            cash_value=result.cash_value, missed_gain=result.missed_gain,
            warnings=result.warnings,
        )
    except Exception as exc:
        logger.error("compare_funds: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})
