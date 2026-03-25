"""
@file symbol_search.py
@brief Symbol search aggregator for LifeLedger market data.

Queries multiple providers in order, deduplicates results by ticker,
and handles ISIN lookups via the OpenFIGI resolver.
"""

import logging
from typing import Optional

from backend.market_data.providers.base import BaseProvider, SymbolResult
from backend.market_data.providers.open_figi import OpenFIGIProvider

logger = logging.getLogger(__name__)


class SymbolSearcher:
    """
    @brief Aggregates symbol search results across multiple market data providers.

    Queries providers in order and deduplicates results by ticker symbol.
    Also supports ISIN lookup via the OpenFIGI resolver.
    """

    def __init__(
        self,
        providers: list[BaseProvider],
        isin_resolver: Optional[OpenFIGIProvider] = None,
    ) -> None:
        """
        @brief Initialise the SymbolSearcher.
        @param providers Ordered list of BaseProvider instances to query.
        @param isin_resolver Optional OpenFIGIProvider for ISIN resolution.
        """
        self._providers = providers
        self._isin_resolver = isin_resolver

    def search(self, query: str) -> list[SymbolResult]:
        """
        @brief Search for instruments matching a query string across all providers.

        Queries providers in order and deduplicates results by ticker. A ticker
        seen from an earlier provider takes precedence over later providers.

        @param query Search string (name, ticker, or partial name).
        @return Deduplicated list of SymbolResult objects.
        """
        try:
            seen_tickers: set[str] = set()
            results: list[SymbolResult] = []

            for provider in self._providers:
                try:
                    provider_results = provider.search_symbol(query)
                    for result in provider_results:
                        ticker_key = result.ticker.upper()
                        if ticker_key and ticker_key not in seen_tickers:
                            seen_tickers.add(ticker_key)
                            results.append(result)
                except Exception as pe:
                    logger.warning(
                        "SymbolSearcher.search: provider %s failed for '%s': %s",
                        provider.provider_name, query, pe,
                    )
                    continue

            logger.debug(
                "SymbolSearcher.search: '%s' → %d results from %d providers",
                query, len(results), len(self._providers),
            )
            return results
        except Exception as exc:
            logger.error("SymbolSearcher.search: error for '%s': %s", query, exc)
            return []

    def lookup_isin(self, isin: str) -> Optional[str]:
        """
        @brief Look up a ticker symbol for a given ISIN using the OpenFIGI resolver.
        @param isin ISIN code string (e.g. 'IE00BK5BQT80').
        @return Ticker symbol string, or None if resolution fails.
        """
        if self._isin_resolver is None:
            logger.warning(
                "SymbolSearcher.lookup_isin: no ISIN resolver configured for %s", isin
            )
            return None

        try:
            ticker = self._isin_resolver.resolve_isin(isin)
            if ticker:
                logger.debug("SymbolSearcher.lookup_isin: %s → %s", isin, ticker)
            else:
                logger.warning(
                    "SymbolSearcher.lookup_isin: no result for ISIN %s", isin
                )
            return ticker
        except Exception as exc:
            logger.error(
                "SymbolSearcher.lookup_isin: error for %s: %s", isin, exc
            )
            return None
