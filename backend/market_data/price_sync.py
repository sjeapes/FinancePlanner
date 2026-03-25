"""
@file price_sync.py
@brief Provider fallback chain orchestrator for LifeLedger market data.

PriceSyncManager coordinates price fetching across multiple providers,
caching results in SQLite. Providers are tried in order; the first
successful result is cached and returned. ISIN resolution is performed
automatically when a symbol contains an ISIN-like pattern.
"""

import logging
from datetime import date
from typing import Optional

from backend.market_data.cache import PriceCache
from backend.market_data.providers.base import BaseProvider, PricePoint
from backend.market_data.providers.open_figi import OpenFIGIProvider

logger = logging.getLogger(__name__)


def _looks_like_isin(value: str) -> bool:
    """
    @brief Heuristic check: does the string look like an ISIN code?
    @param value Input string to check.
    @return True if the string matches the ISIN pattern (2 letters + 10 alphanumeric).
    """
    value = value.strip().upper()
    if len(value) != 12:
        return False
    return value[:2].isalpha() and value[2:].isalnum()


class PriceSyncManager:
    """
    @brief Orchestrates market data fetching across a chain of providers.

    Tries each provider in the supplied order, caches the first successful
    result, and returns it to the caller. If all providers fail, logs a
    staleness warning and returns None.

    ISIN resolution: if the supplied symbol looks like an ISIN, the resolver
    is called first to obtain a ticker before querying providers.
    """

    def __init__(
        self,
        cache: PriceCache,
        providers: list[BaseProvider],
        isin_resolver: Optional[OpenFIGIProvider] = None,
    ) -> None:
        """
        @brief Initialise the PriceSyncManager.
        @param cache PriceCache instance for local SQLite caching.
        @param providers Ordered list of BaseProvider instances. Providers are
               tried in list order; the first successful result is used.
        @param isin_resolver Optional OpenFIGIProvider for ISIN/SEDOL resolution.
        """
        self._cache = cache
        self._providers = providers
        self._isin_resolver = isin_resolver

    def _resolve_symbol(self, symbol_or_isin: str) -> str:
        """
        @brief Resolve an ISIN to a ticker if necessary; otherwise return as-is.
        @param symbol_or_isin Ticker symbol or ISIN string.
        @return Resolved ticker string. Returns the input unchanged if resolution fails.
        """
        if not _looks_like_isin(symbol_or_isin):
            return symbol_or_isin

        if self._isin_resolver is None:
            logger.warning(
                "PriceSyncManager._resolve_symbol: ISIN '%s' provided but no resolver configured",
                symbol_or_isin,
            )
            return symbol_or_isin

        try:
            ticker = self._isin_resolver.resolve_isin(symbol_or_isin)
            if ticker:
                logger.info(
                    "PriceSyncManager._resolve_symbol: ISIN %s → %s",
                    symbol_or_isin, ticker,
                )
                return ticker
            logger.warning(
                "PriceSyncManager._resolve_symbol: ISIN %s could not be resolved",
                symbol_or_isin,
            )
            return symbol_or_isin
        except Exception as exc:
            logger.error(
                "PriceSyncManager._resolve_symbol: error resolving %s: %s",
                symbol_or_isin, exc,
            )
            return symbol_or_isin

    def get_price(
        self,
        symbol: str,
        price_date: Optional[date] = None,
    ) -> Optional[float]:
        """
        @brief Fetch a price for a symbol, checking the cache first.

        Workflow:
        1. Resolve ISIN → ticker if needed.
        2. Check SQLite cache (only for specific dates, not 'latest').
        3. Try each provider in order.
        4. Cache and return the first successful result.
        5. On total failure, log a staleness warning and return None.

        @param symbol Ticker symbol or ISIN string.
        @param price_date Date for price; None = latest price.
        @return Price as float, or None if all providers fail.
        """
        try:
            ticker = self._resolve_symbol(symbol)

            # Check cache for specific date lookups
            if price_date is not None:
                cached = self._cache.get_cached_price(ticker, price_date)
                if cached is not None:
                    logger.debug(
                        "PriceSyncManager.get_price: cache hit %s on %s = %.4f",
                        ticker, price_date, cached,
                    )
                    return cached

            # Try providers in order
            for provider in self._providers:
                try:
                    price = provider.fetch_price(ticker, price_date)
                    if price is not None:
                        # Cache the result for specific date lookups
                        if price_date is not None:
                            self._cache.cache_price(ticker, price_date, price, provider.provider_name)
                        logger.debug(
                            "PriceSyncManager.get_price: %s fetched from %s = %.4f",
                            ticker, provider.provider_name, price,
                        )
                        return price
                    else:
                        logger.debug(
                            "PriceSyncManager.get_price: %s returned None from %s",
                            ticker, provider.provider_name,
                        )
                except Exception as pe:
                    logger.warning(
                        "PriceSyncManager.get_price: provider %s failed for %s: %s",
                        provider.provider_name, ticker, pe,
                    )
                    continue

            logger.warning(
                "PriceSyncManager.get_price: all providers failed for %s%s — data may be stale",
                ticker,
                f" on {price_date}" if price_date else "",
            )
            return None
        except Exception as exc:
            logger.error(
                "PriceSyncManager.get_price: unexpected error for %s: %s", symbol, exc
            )
            return None

    def get_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> dict[date, float]:
        """
        @brief Fetch historical prices, merging cached data with provider data.

        Workflow:
        1. Resolve ISIN → ticker if needed.
        2. Load cached prices from SQLite.
        3. Identify missing dates in the range.
        4. Fetch missing dates from providers in order.
        5. Cache newly fetched prices.
        6. Return the merged result.

        @param symbol Ticker symbol or ISIN string.
        @param start Inclusive start date.
        @param end Inclusive end date.
        @return Dict mapping date -> price for all available dates in the range.
        """
        try:
            ticker = self._resolve_symbol(symbol)

            # Load cached history
            cached = self._cache.get_cached_history(ticker, start, end)

            # Determine how many calendar days are missing
            from datetime import timedelta
            all_dates = set()
            current = start
            while current <= end:
                all_dates.add(current)
                current += timedelta(days=1)
            missing_dates = all_dates - set(cached.keys())

            if not missing_dates:
                logger.debug(
                    "PriceSyncManager.get_history: %s fully cached (%d points)",
                    ticker, len(cached),
                )
                return cached

            logger.debug(
                "PriceSyncManager.get_history: %s — %d cached, %d calendar days missing",
                ticker, len(cached), len(missing_dates),
            )

            # Fetch from providers
            fetched: dict[date, float] = {}
            for provider in self._providers:
                try:
                    points = provider.fetch_history(ticker, start, end)
                    for point in points:
                        if point.date not in cached:
                            fetched[point.date] = point.price
                    if fetched:
                        # Cache new prices
                        self._cache.cache_history(ticker, fetched, provider.provider_name)
                        logger.debug(
                            "PriceSyncManager.get_history: %s fetched %d new points from %s",
                            ticker, len(fetched), provider.provider_name,
                        )
                        break
                except Exception as pe:
                    logger.warning(
                        "PriceSyncManager.get_history: provider %s failed for %s: %s",
                        provider.provider_name, ticker, pe,
                    )
                    continue

            if not fetched:
                logger.warning(
                    "PriceSyncManager.get_history: all providers failed for %s %s–%s",
                    ticker, start, end,
                )

            merged = {**cached, **fetched}
            return merged
        except Exception as exc:
            logger.error(
                "PriceSyncManager.get_history: unexpected error for %s: %s", symbol, exc
            )
            return {}

    def resolve_and_fetch(
        self,
        isin_or_ticker: str,
        price_date: Optional[date] = None,
    ) -> Optional[float]:
        """
        @brief Resolve an ISIN/SEDOL/ticker and fetch the price in a single call.

        Convenience method that combines resolution and price fetching.
        Equivalent to calling get_price() with an ISIN — the resolution
        happens internally.

        @param isin_or_ticker ISIN, SEDOL, or direct ticker symbol.
        @param price_date Date for price; None = latest.
        @return Price as float, or None on failure.
        """
        try:
            return self.get_price(isin_or_ticker, price_date)
        except Exception as exc:
            logger.error(
                "PriceSyncManager.resolve_and_fetch: error for %s: %s",
                isin_or_ticker, exc,
            )
            return None
