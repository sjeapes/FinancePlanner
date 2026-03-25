"""
@file market_data.py
@brief FastAPI routes for market data operations.

Endpoints:
  GET  /api/market-data/search?q=query          — symbol search
  GET  /api/market-data/price/{symbol}          — latest price
  GET  /api/market-data/price/{symbol}/history  — price history
  POST /api/market-data/refresh                 — refresh all SymbolLinks
  POST /api/market-data/api-key                 — store provider API key
"""

import logging
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.market_data.providers.base import SymbolResult

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────

class SymbolResultOut(BaseModel):
    """
    @brief API output model for a symbol search result.
    @param ticker Ticker symbol.
    @param name Instrument name.
    @param exchange Exchange code.
    @param currency Trading currency.
    """
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str
    exchange: str
    currency: str


class PriceResponse(BaseModel):
    """
    @brief API response for a single price lookup.
    @param symbol Ticker symbol.
    @param price Current or requested-date price.
    @param price_date Date of the price.
    @param provider Provider that supplied the price.
    @param from_cache Whether the price came from the SQLite cache.
    """
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    price: Optional[float] = None
    price_date: Optional[date] = None
    provider: str = ""
    from_cache: bool = False


class PriceHistoryItem(BaseModel):
    """
    @brief A single price history entry.
    @param date Date.
    @param price Closing price.
    """
    model_config = ConfigDict(from_attributes=True)

    date: date
    price: float


class PriceHistoryResponse(BaseModel):
    """
    @brief API response for historical price data.
    @param symbol Ticker symbol.
    @param history List of date/price pairs.
    @param from_cache Number of points from cache.
    @param from_provider Number of points newly fetched.
    """
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    history: list[PriceHistoryItem]
    from_cache: int = 0
    from_provider: int = 0


class RefreshRequest(BaseModel):
    """
    @brief Request body for POST /api/market-data/refresh.
    @param scenario_path Optional path to a scenario YAML; defaults to base scenario.
    """
    model_config = ConfigDict(from_attributes=True)

    scenario_path: str = "data/scenarios/base.yaml"


class RefreshResponse(BaseModel):
    """
    @brief Response for POST /api/market-data/refresh.
    @param refreshed List of successfully refreshed symbols.
    @param failed List of symbols that could not be refreshed.
    @param skipped List of symbols skipped (schedule not due).
    """
    model_config = ConfigDict(from_attributes=True)

    refreshed: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []


class ApiKeyRequest(BaseModel):
    """
    @brief Request body for POST /api/market-data/api-key.
    @param provider Provider identifier (e.g. 'alpha_vantage', 'finnhub').
    @param key Raw API key string.
    """
    model_config = ConfigDict(from_attributes=True)

    provider: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_price_sync(request: Request):
    """
    @brief Retrieve the PriceSyncManager from app state.
    @param request FastAPI Request.
    @return PriceSyncManager or None.
    """
    return getattr(request.app.state, "price_sync", None)


def _get_searcher(request: Request):
    """
    @brief Retrieve the SymbolSearcher from app state.
    @param request FastAPI Request.
    @return SymbolSearcher or None.
    """
    return getattr(request.app.state, "symbol_searcher", None)


def _get_scheduler(request: Request):
    """
    @brief Retrieve the RefreshScheduler from app state.
    @param request FastAPI Request.
    @return RefreshScheduler or None.
    """
    return getattr(request.app.state, "refresh_scheduler", None)


# ── Route handlers ────────────────────────────────────────────────────────────

@router.get("/market-data/search", response_model=list[SymbolResultOut])
def search_symbols(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query string"),
) -> list[SymbolResultOut]:
    """
    @brief Search for instruments across all configured providers.
    @param request FastAPI Request.
    @param q Search query string.
    @return List of SymbolResultOut objects.
    """
    searcher = _get_searcher(request)
    if searcher is None:
        raise HTTPException(
            status_code=503,
            detail="Symbol searcher not initialised. Check provider configuration.",
        )

    try:
        results = searcher.search(q)
        return [
            SymbolResultOut(
                ticker=r.ticker,
                name=r.name,
                exchange=r.exchange,
                currency=r.currency,
            )
            for r in results
        ]
    except Exception as exc:
        logger.error("search_symbols: error for '%s': %s", q, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Search error", "detail": str(exc)},
        )


@router.get("/market-data/price/{symbol}", response_model=PriceResponse)
def get_price(symbol: str, request: Request) -> PriceResponse:
    """
    @brief Fetch the latest price for a symbol.
    @param symbol Ticker symbol (URL-encoded if needed).
    @param request FastAPI Request.
    @return PriceResponse with latest price.
    """
    price_sync = _get_price_sync(request)
    if price_sync is None:
        raise HTTPException(
            status_code=503,
            detail="Price sync not initialised. Check provider configuration.",
        )

    try:
        price = price_sync.get_price(symbol)
        return PriceResponse(
            symbol=symbol,
            price=price,
            price_date=date.today(),
        )
    except Exception as exc:
        logger.error("get_price: error for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Price fetch error", "detail": str(exc)},
        )


@router.get("/market-data/price/{symbol}/history", response_model=PriceHistoryResponse)
def get_price_history(
    symbol: str,
    request: Request,
    start: Optional[date] = Query(default=None, description="Start date (ISO format)"),
    end: Optional[date] = Query(default=None, description="End date (ISO format)"),
) -> PriceHistoryResponse:
    """
    @brief Fetch historical prices for a symbol within an optional date range.
    @param symbol Ticker symbol.
    @param request FastAPI Request.
    @param start Inclusive start date; defaults to one year ago.
    @param end Inclusive end date; defaults to today.
    @return PriceHistoryResponse with sorted price history.
    """
    price_sync = _get_price_sync(request)
    if price_sync is None:
        raise HTTPException(
            status_code=503,
            detail="Price sync not initialised.",
        )

    from datetime import timedelta
    today = date.today()
    if end is None:
        end = today
    if start is None:
        start = today - timedelta(days=365)

    if start > end:
        raise HTTPException(
            status_code=422,
            detail=f"start ({start}) must be before end ({end})",
        )

    try:
        history_dict = price_sync.get_history(symbol, start, end)
        history_list = [
            PriceHistoryItem(date=d, price=p)
            for d, p in sorted(history_dict.items())
        ]
        return PriceHistoryResponse(
            symbol=symbol,
            history=history_list,
        )
    except Exception as exc:
        logger.error(
            "get_price_history: error for %s: %s", symbol, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "History fetch error", "detail": str(exc)},
        )


@router.post("/market-data/refresh", response_model=RefreshResponse)
def refresh_market_data(body: RefreshRequest, request: Request) -> RefreshResponse:
    """
    @brief Trigger a refresh of all SymbolLinks in the specified scenario.

    Iterates all SymbolLink-attached holdings and fetches updated prices
    for those that are due according to their refresh schedule.

    @param body RefreshRequest with optional scenario_path.
    @param request FastAPI Request.
    @return RefreshResponse with refreshed/failed/skipped symbol lists.
    """
    price_sync = _get_price_sync(request)
    scheduler = _get_scheduler(request)

    if price_sync is None:
        raise HTTPException(status_code=503, detail="Price sync not initialised.")

    root = getattr(request.app.state, "project_root", ".")
    abs_path = os.path.join(root, body.scenario_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(
            status_code=404,
            detail=f"Scenario not found: {body.scenario_path}",
        )

    try:
        from backend.persistence.yaml_serialiser import load_scenario_from_file

        scenario = load_scenario_from_file(abs_path)
        if scenario is None:
            raise HTTPException(status_code=422, detail="Could not parse scenario")

        # Collect all SymbolLinks from investment holdings
        symbol_links = []
        for acc in scenario.investment_accounts:
            for holding in acc.holdings:
                if holding.symbol_link and holding.symbol_link.symbol:
                    symbol_links.append(holding.symbol_link)

        refreshed = []
        failed = []
        skipped = []

        for sl in symbol_links:
            if scheduler and not scheduler.should_refresh(sl):
                skipped.append(sl.symbol)
                continue

            price = price_sync.get_price(sl.symbol)
            if price is not None:
                refreshed.append(sl.symbol)
                if scheduler:
                    scheduler.mark_refreshed(sl.symbol)
            else:
                failed.append(sl.symbol)

        logger.info(
            "refresh_market_data: refreshed=%d failed=%d skipped=%d",
            len(refreshed), len(failed), len(skipped),
        )
        return RefreshResponse(refreshed=refreshed, failed=failed, skipped=skipped)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("refresh_market_data: error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Refresh error", "detail": str(exc)},
        )


@router.post("/market-data/api-key", status_code=200)
def store_api_key(body: ApiKeyRequest, request: Request) -> dict:
    """
    @brief Store a provider API key in the SQLite api_keys table.

    The key is base64-encoded before storage and never written to YAML.

    @param body ApiKeyRequest with provider name and raw key string.
    @param request FastAPI Request.
    @return Confirmation dict.
    """
    engine = getattr(request.app.state, "db_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Database not initialised.",
        )

    try:
        from backend.persistence.sqlite_cache import set_api_key

        ok = set_api_key(engine, body.provider, body.key)
        if not ok:
            raise HTTPException(
                status_code=500,
                detail={"error": "Storage error", "detail": "Could not store API key"},
            )
        logger.info("store_api_key: stored key for provider '%s'", body.provider)
        return {"status": "ok", "provider": body.provider}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("store_api_key: error for '%s': %s", body.provider, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Storage error", "detail": str(exc)},
        )
