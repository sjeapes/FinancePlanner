"""
@file finnhub_provider.py
@brief Finnhub market data provider for LifeLedger.

Uses httpx for synchronous HTTP calls to the Finnhub REST API.
The API key is fetched from the SQLite api_keys table via a callable
passed at initialisation.

Free tier limits: 60 requests per minute. The provider tracks request
timestamps in a deque and enforces the limit before each call.
"""

import logging
from collections import deque
from datetime import date, datetime, timezone
from typing import Callable, Optional

import httpx

from backend.market_data.providers.base import BaseProvider, PricePoint, SymbolResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"
_RATE_LIMIT_PER_MINUTE = 60


class FinnhubProvider(BaseProvider):
    """
    @brief Market data provider backed by the Finnhub REST API.

    Tertiary provider in the LifeLedger fallback chain. Requires a free
    API key stored in the SQLite api_keys table under provider='finnhub'.

    Rate limit: 60 requests per minute. A deque of request timestamps is
    used to enforce the sliding-window rate limit.
    """

    def __init__(self, get_api_key_fn: Callable[[], Optional[str]]) -> None:
        """
        @brief Initialise the Finnhub provider.
        @param get_api_key_fn Zero-argument callable returning the API key string
               or None if not configured.
        """
        self._get_api_key = get_api_key_fn
        self._request_times: deque = deque()

    @property
    def provider_name(self) -> str:
        """
        @brief Return the provider identifier.
        @return String 'finnhub'.
        """
        return "finnhub"

    def _get_key(self) -> Optional[str]:
        """
        @brief Retrieve the API key via the injected callable.
        @return API key string or None.
        """
        try:
            return self._get_api_key()
        except Exception as exc:
            logger.error("FinnhubProvider._get_key: %s", exc)
            return None

    def _check_rate_limit(self) -> bool:
        """
        @brief Enforce the 60-requests-per-minute rate limit using a sliding window.

        Prunes timestamps older than 60 seconds. Returns False if at or above
        the limit.

        @return True if the request is within limits, False if throttled.
        """
        now = datetime.now(tz=timezone.utc).timestamp()
        cutoff = now - 60.0
        while self._request_times and self._request_times[0] < cutoff:
            self._request_times.popleft()

        if len(self._request_times) >= _RATE_LIMIT_PER_MINUTE:
            logger.warning(
                "FinnhubProvider: rate limit of %d req/min reached",
                _RATE_LIMIT_PER_MINUTE,
            )
            return False

        self._request_times.append(now)
        remaining = _RATE_LIMIT_PER_MINUTE - len(self._request_times)
        if remaining <= 5:
            logger.warning(
                "FinnhubProvider: %d requests remaining in current minute", remaining
            )
        return True

    def _get(self, endpoint: str, params: dict) -> Optional[dict]:
        """
        @brief Execute a GET request to the Finnhub API.
        @param endpoint API endpoint path (e.g. '/quote').
        @param params Query parameters dict (excluding token).
        @return Parsed JSON response dict, or None on failure.
        """
        key = self._get_key()
        if not key:
            logger.warning("FinnhubProvider: no API key configured")
            return None
        if not self._check_rate_limit():
            return None

        params = dict(params)
        params["token"] = key
        url = f"{_BASE_URL}{endpoint}"
        try:
            response = httpx.get(url, params=params, timeout=15.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "FinnhubProvider._get: HTTP %d for %s: %s",
                exc.response.status_code, endpoint, exc,
            )
            return None
        except Exception as exc:
            logger.error("FinnhubProvider._get: %s", exc)
            return None

    def fetch_price(self, symbol: str, price_date: Optional[date] = None) -> Optional[float]:
        """
        @brief Fetch the current or historical price for a symbol.

        Uses the /quote endpoint for the current price. Historical prices are
        fetched via the /stock/candle endpoint using Unix timestamps.

        @param symbol Exchange ticker symbol.
        @param price_date Date for price; None returns the current price.
        @return Closing price as float, or None on failure.
        """
        try:
            if price_date is None:
                data = self._get("/quote", {"symbol": symbol})
                if not data:
                    return None
                price = data.get("c")  # current price
                if price is None or price == 0:
                    logger.warning(
                        "FinnhubProvider.fetch_price: no current price for %s", symbol
                    )
                    return None
                logger.debug(
                    "FinnhubProvider.fetch_price: %s current=%.4f", symbol, price
                )
                return float(price)
            else:
                history = self.fetch_history(symbol, price_date, price_date)
                if history:
                    return history[0].price
                return None
        except Exception as exc:
            logger.error(
                "FinnhubProvider.fetch_price: error for %s: %s", symbol, exc
            )
            return None

    def fetch_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[PricePoint]:
        """
        @brief Fetch daily OHLCV candles for a date range.

        Uses the /stock/candle endpoint with resolution 'D' (daily).

        @param symbol Exchange ticker symbol.
        @param start Inclusive start date.
        @param end Inclusive end date.
        @return List of PricePoint objects ordered by date ascending.
        """
        try:
            start_ts = int(
                datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()
            )
            end_ts = int(
                datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc).timestamp()
            )

            data = self._get("/stock/candle", {
                "symbol": symbol,
                "resolution": "D",
                "from": start_ts,
                "to": end_ts,
            })
            if not data or data.get("s") != "ok":
                logger.warning(
                    "FinnhubProvider.fetch_history: no/bad data for %s %s–%s (status=%s)",
                    symbol, start, end, data.get("s") if data else "none",
                )
                return []

            timestamps = data.get("t", [])
            closes = data.get("c", [])
            volumes = data.get("v", [])
            results: list[PricePoint] = []

            for i, ts in enumerate(timestamps):
                try:
                    row_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                    close = float(closes[i]) if i < len(closes) else 0.0
                    volume = float(volumes[i]) if i < len(volumes) else None
                    results.append(PricePoint(date=row_date, price=close, volume=volume))
                except Exception as re:
                    logger.warning(
                        "FinnhubProvider.fetch_history: bad candle at index %d for %s: %s",
                        i, symbol, re,
                    )
                    continue

            results.sort(key=lambda p: p.date)
            logger.debug(
                "FinnhubProvider.fetch_history: %s %s–%s → %d points",
                symbol, start, end, len(results),
            )
            return results
        except Exception as exc:
            logger.error(
                "FinnhubProvider.fetch_history: error for %s: %s", symbol, exc
            )
            return []

    def search_symbol(self, query: str) -> list[SymbolResult]:
        """
        @brief Search for instruments using the Finnhub /search endpoint.
        @param query Search string (name or ticker).
        @return List of SymbolResult objects.
        """
        try:
            data = self._get("/search", {"q": query})
            if not data:
                return []

            count = data.get("count", 0)
            if count == 0:
                return []

            results: list[SymbolResult] = []
            for item in data.get("result", []):
                try:
                    results.append(
                        SymbolResult(
                            ticker=str(item.get("symbol", "")),
                            name=str(item.get("description", "")),
                            exchange=str(item.get("primaryExchange", "")),
                            currency="",  # Finnhub /search doesn't return currency
                        )
                    )
                except Exception as ie:
                    logger.warning(
                        "FinnhubProvider.search_symbol: bad result %s: %s", item, ie
                    )
                    continue

            logger.debug(
                "FinnhubProvider.search_symbol: '%s' → %d results", query, len(results)
            )
            return results
        except Exception as exc:
            logger.error(
                "FinnhubProvider.search_symbol: error for '%s': %s", query, exc
            )
            return []
