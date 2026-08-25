"""
@file opportunity_analyser.py
@brief Phase 10 investment opportunity analyser for LifeLedger.

Replays a series of historical cash flows (from a bank statement or
manual entry) against real historical ETF prices fetched via yfinance.
Shows the portfolio value today if those flows had been invested rather
than left in cash.

Use-cases
---------
- "If I had invested my £500/month savings into VWRP from 2018, what
  would I have today?"
- Compares multiple funds side-by-side (DCA return, IRR, total gain).
- Accepts either a flat monthly contribution or an imported transaction
  series (list of (date, amount) tuples from the statement parser).

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger("lifeledger.opportunity_analyser")

# ── Pre-defined fund catalogue (London Stock Exchange tickers) ──────────────

FUND_CATALOGUE: list[dict] = [
    {"ticker": "VWRP.L",  "name": "Vanguard FTSE All-World (Acc)",    "category": "Global"},
    {"ticker": "VUSA.L",  "name": "Vanguard S&P 500 ETF",             "category": "US"},
    {"ticker": "CSP1.L",  "name": "iShares Core S&P 500 UCITS",       "category": "US"},
    {"ticker": "IWDA.L",  "name": "iShares MSCI World UCITS",         "category": "Global"},
    {"ticker": "SWRD.L",  "name": "SPDR MSCI World UCITS",            "category": "Global"},
    {"ticker": "VFEM.L",  "name": "Vanguard FTSE Emerging Markets",   "category": "Emerging"},
    {"ticker": "VUKE.L",  "name": "Vanguard FTSE 100 ETF",            "category": "UK"},
    {"ticker": "IUSA.L",  "name": "iShares S&P 500 UCITS (Dist)",     "category": "US"},
    {"ticker": "AGGG.L",  "name": "iShares Core Global Agg Bond",     "category": "Bonds"},
    {"ticker": "IGLT.L",  "name": "iShares UK Gilts UCITS",           "category": "Bonds"},
]


# ── Result dataclasses ──────────────────────────────────────────────────────

@dataclass
class MonthlySnapshot:
    """@brief Portfolio value at end of one month for one fund."""
    date_str: str
    units_held: float
    price: float
    portfolio_value: float
    cumulative_invested: float
    gain: float
    gain_pct: float


@dataclass
class FundResult:
    """
    @brief Full DCA result for one fund over the selected period.

    @param ticker              Fund ticker symbol.
    @param name                Fund display name.
    @param category            Asset class category.
    @param total_invested      Total cash deployed (lump sum + all contributions).
    @param final_value         Portfolio value at end of period.
    @param total_gain          final_value - total_invested.
    @param total_gain_pct      total_gain / total_invested * 100.
    @param annualised_return   CAGR over the period (%).
    @param monthly             Month-by-month snapshots.
    @param error               Non-empty if data could not be fetched.
    """
    ticker: str
    name: str
    category: str
    total_invested: float
    final_value: float
    total_gain: float
    total_gain_pct: float
    annualised_return: float
    monthly: list[MonthlySnapshot]
    error: str = ""


@dataclass
class OpportunityResult:
    """
    @brief Full opportunity analysis comparing multiple funds.

    @param start_date           ISO date of first investment.
    @param end_date             ISO date of last valuation.
    @param initial_lump_sum     One-off initial investment.
    @param monthly_contribution Regular monthly investment.
    @param total_invested       Total cash deployed across all months.
    @param funds                Per-fund results.
    @param best_fund_ticker     Ticker of the fund with highest final value.
    @param cash_value           What the same cash would be worth with no investment.
    @param missed_gain          best final_value minus cash_value.
    @param warnings             Non-fatal warnings.
    """
    start_date: str
    end_date: str
    initial_lump_sum: float
    monthly_contribution: float
    total_invested: float
    funds: list[FundResult]
    best_fund_ticker: str
    cash_value: float
    missed_gain: float
    warnings: list[str] = field(default_factory=list)


# ── Engine ──────────────────────────────────────────────────────────────────

def _cagr(start_val: float, end_val: float, years: float) -> float:
    """@brief Compute CAGR. Returns 0 if inputs are invalid."""
    if start_val <= 0 or end_val <= 0 or years <= 0:
        return 0.0
    try:
        return ((end_val / start_val) ** (1.0 / years) - 1) * 100
    except (ZeroDivisionError, ValueError):
        return 0.0


def _fetch_monthly_prices(ticker: str, start: str, end: str) -> dict[str, float]:
    """
    @brief Fetch monthly closing prices from yfinance.

    @param ticker  Yahoo Finance ticker symbol.
    @param start   ISO date string start.
    @param end     ISO date string end.
    @return        Dict mapping "YYYY-MM" → price (GBP).
    """
    try:
        import yfinance as yf
        data = yf.download(ticker, start=start, end=end,
                           interval="1mo", progress=False, auto_adjust=True)
        if data.empty:
            return {}
        prices: dict[str, float] = {}
        for idx, row in data.iterrows():
            month_key = str(idx)[:7]
            close = row["Close"]
            if hasattr(close, "item"):
                close = close.item()
            if close and close > 0:
                # Convert pence to pounds for London-listed ETFs
                price = float(close)
                if price > 1000:
                    price /= 100.0   # pence → pounds
                prices[month_key] = round(price, 4)
        return prices
    except Exception as exc:
        logger.error("_fetch_monthly_prices %s: %s", ticker, exc)
        return {}


def _dca_simulate(
    prices: dict[str, float],
    initial_lump_sum: float,
    monthly_contribution: float,
    cash_flows: Optional[list[tuple[str, float]]] = None,
) -> tuple[list[MonthlySnapshot], float, float]:
    """
    @brief Simulate DCA strategy over the price series.

    @param prices               Monthly prices (YYYY-MM → price).
    @param initial_lump_sum     One-off investment at start.
    @param monthly_contribution Regular monthly investment (0 if using cash_flows).
    @param cash_flows           Optional explicit (YYYY-MM, amount) list.
    @return                     (snapshots, total_invested, final_value).
    """
    flow_map: dict[str, float] = {}
    if cash_flows:
        for dt, amt in cash_flows:
            key = str(dt)[:7]
            flow_map[key] = flow_map.get(key, 0.0) + amt
    
    months = sorted(prices.keys())
    if not months:
        return [], 0.0, 0.0

    units_held = 0.0
    total_invested = 0.0
    snapshots: list[MonthlySnapshot] = []

    for i, month in enumerate(months):
        price = prices[month]
        
        # Determine investment this month
        if i == 0:
            invest = initial_lump_sum
        else:
            invest = 0.0
        
        if cash_flows:
            invest += flow_map.get(month, 0.0)
        else:
            invest += monthly_contribution
        
        if invest > 0 and price > 0:
            units_bought = invest / price
            units_held   += units_bought
            total_invested += invest

        portfolio_value = units_held * price
        gain = portfolio_value - total_invested
        gain_pct = (gain / total_invested * 100) if total_invested > 0 else 0.0

        snapshots.append(MonthlySnapshot(
            date_str=month + "-01",
            units_held=round(units_held, 6),
            price=round(price, 4),
            portfolio_value=round(portfolio_value, 2),
            cumulative_invested=round(total_invested, 2),
            gain=round(gain, 2),
            gain_pct=round(gain_pct, 2),
        ))

    final_value = snapshots[-1].portfolio_value if snapshots else 0.0
    return snapshots, total_invested, final_value


def analyse_opportunity(
    tickers: list[str],
    start_date: str,
    end_date: str,
    initial_lump_sum: float = 0.0,
    monthly_contribution: float = 500.0,
    cash_flows: Optional[list[tuple[str, float]]] = None,
) -> OpportunityResult:
    """
    @brief Compare DCA investment in multiple funds over a historical period.

    @param tickers              List of Yahoo Finance ticker symbols.
    @param start_date           First investment date (ISO 8601).
    @param end_date             Last valuation date (ISO 8601).
    @param initial_lump_sum     One-off investment at start.
    @param monthly_contribution Monthly investment (ignored if cash_flows given).
    @param cash_flows           Optional explicit (date, amount) pairs.
    @return                     OpportunityResult with per-fund comparison.
    """
    logger.info(
        "analyse_opportunity: tickers=%s start=%s end=%s lump=%.0f monthly=%.0f",
        tickers, start_date, end_date, initial_lump_sum, monthly_contribution,
    )

    warnings: list[str] = []
    results: list[FundResult] = []

    try:
        start_dt = datetime.fromisoformat(start_date).date()
        end_dt   = datetime.fromisoformat(end_date).date()
    except ValueError:
        start_dt = date.today().replace(year=date.today().year - 5, month=1, day=1)
        end_dt   = date.today()

    years = max(0.1, (end_dt - start_dt).days / 365.25)

    # Cash (no investment) reference: flat total_invested
    cash_value = initial_lump_sum + monthly_contribution * 12 * years

    for ticker in tickers:
        fund_meta = next((f for f in FUND_CATALOGUE if f["ticker"] == ticker),
                          {"ticker": ticker, "name": ticker, "category": "Unknown"})
        try:
            prices = _fetch_monthly_prices(ticker, start_date, end_date)
            if not prices:
                results.append(FundResult(
                    ticker=ticker, name=fund_meta["name"], category=fund_meta["category"],
                    total_invested=0, final_value=0, total_gain=0,
                    total_gain_pct=0, annualised_return=0, monthly=[],
                    error=f"No price data available for {ticker}",
                ))
                warnings.append(f"No data for {ticker} — try a later start date.")
                continue

            snapshots, total_invested, final_value = _dca_simulate(
                prices, initial_lump_sum, monthly_contribution, cash_flows,
            )

            gain     = final_value - total_invested
            gain_pct = (gain / total_invested * 100) if total_invested > 0 else 0.0
            cagr     = _cagr(total_invested, final_value, years)

            results.append(FundResult(
                ticker=ticker, name=fund_meta["name"], category=fund_meta["category"],
                total_invested=round(total_invested, 2),
                final_value=round(final_value, 2),
                total_gain=round(gain, 2),
                total_gain_pct=round(gain_pct, 2),
                annualised_return=round(cagr, 2),
                monthly=snapshots,
            ))
            logger.info("  %s: invested=£%.0f final=£%.0f cagr=%.1f%%",
                        ticker, total_invested, final_value, cagr)

        except Exception as exc:
            logger.error("analyse_opportunity %s: %s", ticker, exc, exc_info=True)
            results.append(FundResult(
                ticker=ticker, name=fund_meta["name"], category=fund_meta["category"],
                total_invested=0, final_value=0, total_gain=0,
                total_gain_pct=0, annualised_return=0, monthly=[],
                error=str(exc),
            ))

    best = max((r for r in results if not r.error), key=lambda r: r.final_value, default=None)
    total_invested_ref = best.total_invested if best else cash_value

    return OpportunityResult(
        start_date=str(start_dt),
        end_date=str(end_dt),
        initial_lump_sum=initial_lump_sum,
        monthly_contribution=monthly_contribution,
        total_invested=round(total_invested_ref, 2),
        funds=results,
        best_fund_ticker=best.ticker if best else "",
        cash_value=round(cash_value, 2),
        missed_gain=round((best.final_value if best else 0) - cash_value, 2),
        warnings=warnings,
    )
