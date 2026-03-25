"""
@file alpha_vantage.py
@brief Alpha Vantage market data provider for LifeLedger.

Uses httpx for synchronous HTTP calls to the Alpha Vantage REST API.
The API key is fetched from the SQLite api_keys table via a callable
passed at initialisation — it is never stored in YAML or in memory
longer than needed.

Free tier limits: 25 requests per day. Requests in excess of this limit
will fail with a rate-limit warning logged at WARNING level.
"""

import logging
from datetime import date, datetime
from typing import Callable, Optional

import httpx

from backend.market_data.providers.base import BaseProvider, PricePoint, SymbolResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.alphavantage.co/query"
_DAILY_LIMIT = 25


class AlphaVantageProvider(BaseProvider):
    """
    @brief Market data provider backed by Alpha Vantage REST API.

    Secondary provider in the LifeLedger fallback chain. Requires a free
    API key stored in the SQLite api_keys table under provider='alpha_vantage'.

    Rate limit: 25 requests per day on the free tier. The provider tracks
    requests in memory and logs a warning when approaching the limit.
    """

    def __init__(self, get_api_key_fn: Callable[[], Optional[str]]) -> None:
        """
        @brief Initialise the Alpha Vantage provider.
        @param get_api_key_fn Zero-argument callable that returns the API key string,
               or None if no key is configured. This callable typically reads from
               the SQLite api_keys table.
        """
        self._get_api_key = get_api_key_fn
        self._request_count: int = 0
        self._reset_date: Optional[date] = None

    @property
    def provider_name(self) -> str:
        """
        @brief Return the provider identifier.
        @return String 'alpha_vantage'.
        """
        return "alpha_vantage"

    def _get_key(self) -> Optional[str]:
        """
        @brief Retrieve the API key via the injected callable.
        @return API key string or None.
        """
        try:
            return self._get_api_key()
        except Exception as exc:
            logger.error("AlphaVantageProvider._get_key: %s", exc)
            return None

    def _check_rate_limit(self) -> bool:
        """
        @brief Check and increment the daily request counter.

        Resets the counter at the start of each new UTC day.

        @return True if the request is within limits, False if the limit has been reached.
        """
        today = date.today()
        if self._reset_date != today:
            self._reset_date = today
            self._request_count = 0

        if self._request_count >= _DAILY_LIMIT:
            logger.warning(
                "AlphaVantageProvider: daily limit of %d requests reached", _DAILY_LIMIT
            )
            return False

        self._request_count += 1
        remaining = _DAILY_LIMIT - self._request_count
        if remaining <= 5:
            logger.warning(
                "AlphaVantageProvider: only %d requests remaining today", remaining
            )
        return True

    def _get(self, params: dict) -> Optional[dict]:
        """
        @brief Execute a GET request to the Alpha Vantage API.
        @param params Query parameter dict (excluding apikey).
        @return Parsed JSON response dict, or None on failure.
        """
        key = self._get_key()
        if not key:
            logger.warning("AlphaVantageProvider: no API key configured")
            return None
        if not self._check_rate_limit():
            return None

        params = dict(params)
        params["apikey"] = key
        try:
            response = httpx.get(_BASE_URL, params=params, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            if "Note" in data:
                logger.warning(
                    "AlphaVantageProvider: API throttle note: %s", data["Note"]
                )
                return None
            if "Information" in data:
                logger.warning(
                    "AlphaVantageProvider: API info message: %s", data["Information"]
                )
                return None
            return data
        except httpx.HTTPStatusError as exc:
            logger.error(
                "AlphaVantageProvider._get: HTTP %d for %s: %s",
                exc.response.status_code, params.get("symbol", ""), exc,
            )
            return None
        except Exception as exc:
            logger.error("AlphaVantageProvider._get: %s", exc)
            return None

    def fetch_price(self, symbol: str, price_date: Optional[date] = None) -> Optional[float]:
        """
        @brief Fetch the latest or historical close price for a symbol.

        Uses GLOBAL_QUOTE for the latest price, or TIME_SERIES_DAILY for a
        specific date.

        @param symbol Exchange ticker symbol.
        @param price_date Specific date; None returns the latest price.
        @return Closing price as float, or None on failure.
        """
        try:
            if price_date is None:
                data = self._get({"function": "GLOBAL_QUOTE", "symbol": symbol})
                if not data:
                    return None
                quote = data.get("Global Quote", {})
                price_str = quote.get("05. price")
                if not price_str:
                    logger.warning(
                        "AlphaVantageProvider.fetch_price: no price in GLOBAL_QUOTE for %s",
                        symbol,
                    )
                    return None
                price = float(price_str)
                logger.debug(
                    "AlphaVantageProvider.fetch_price: %s latest=%.4f", symbol, price
                )
                return price
            else:
                history = self.fetch_history(symbol, price_date, price_date)
                if history:
                    return history[0].price
                return None
        except Exception as exc:
            logger.error(
                "AlphaVantageProvider.fetch_price: error for %s: %s", symbol, exc
            )
            return None

    def fetch_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[PricePoint]:
        """
        @brief Fetch historical daily closing prices using TIME_SERIES_DAILY.

        Uses outputsize='full' to retrieve up to 20 years of data when the
        range spans more than 100 days, otherwise 'compact' (last 100 days).

        @param symbol Exchange ticker symbol.
        @param start Inclusive start date.
        @param end Inclusive end date.
        @return List of PricePoint objects ordered by date ascending.
        """
        try:
            span_days = (end - start).days
            output_size = "full" if span_days > 100 else "compact"
            data = self._get({
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": output_size,
            })
            if not data:
                return []

            time_series = data.get("Time Series (Daily)", {})
            results: list[PricePoint] = []

            for date_str, values in time_series.items():
                try:
                    row_date = date.fromisoformat(date_str)
                    if not (start <= row_date <= end):
                        continue
                    close = float(values.get("4. close", 0.0))
                    volume_raw = values.get("5. volume")
                    volume = float(volume_raw) if volume_raw else None
                    results.append(PricePoint(date=row_date, price=close, volume=volume))
                except Exception as re:
                    logger.warning(
                        "AlphaVantageProvider.fetch_history: bad row %s for %s: %s",
                        date_str, symbol, re,
                    )
                    continue

            results.sort(key=lambda p: p.date)
            logger.debug(
                "AlphaVantageProvider.fetch_history: %s %s–%s → %d points",
                symbol, start, end, len(results),
            )
            return results
        except Exception as exc:
            logger.error(
                "AlphaVantageProvider.fetch_history: error for %s: %s", symbol, exc
            )
            return []

    def search_symbol(self, query: str) -> list[SymbolResult]:
        """
        @brief Search for instruments using the SYMBOL_SEARCH endpoint.
        @param query Search string (name, ticker, or partial name).
        @return List of SymbolResult objects.
        """
        try:
            data = self._get({"function": "SYMBOL_SEARCH", "keywords": query})
            if not data:
                return []

            matches = data.get("bestMatches", [])
            results: list[SymbolResult] = []
            for m in matches:
                try:
                    results.append(
                        SymbolResult(
                            ticker=str(m.get("1. symbol", "")),
                            name=str(m.get("2. name", "")),
                            exchange=str(m.get("4. region", "")),
                            currency=str(m.get("8. currency", "")),
                        )
                    )
                except Exception as me:
                    logger.warning(
                        "AlphaVantageProvider.search_symbol: bad match %s: %s", m, me
                    )
                    continue

            logger.debug(
                "AlphaVantageProvider.search_symbol: '%s' → %d results", query, len(results)
            )
            return results
        except Exception as exc:
            logger.error(
                "AlphaVantageProvider.search_symbol: error for '%s': %s", query, exc
            )
            return []
