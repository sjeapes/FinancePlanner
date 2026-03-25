"""
@file cache.py
@brief SQLite price cache wrapper for the LifeLedger market data module.

Wraps the low-level sqlite_cache CRUD helpers with a higher-level interface
specific to the market data domain. Historical prices are immutable — once
a date has been cached, it is never overwritten.
"""

import logging
from datetime import date
from typing import Optional

from backend.persistence.sqlite_cache import (
    get_engine,
    get_prices,
    init_db,
    upsert_price,
)

logger = logging.getLogger(__name__)


class PriceCache:
    """
    @brief High-level SQLite price cache for market data.

    Provides get/set operations for individual prices and bulk history.
    All writes honour the immutability rule: an existing price for a
    symbol+date combination will never be overwritten.
    """

    def __init__(self, db_path: str) -> None:
        """
        @brief Initialise the price cache, creating the database if necessary.
        @param db_path Absolute or relative path to the SQLite database file.
        """
        self._db_path = db_path
        try:
            self._engine = get_engine(db_path)
            init_db(db_path)
            logger.debug("PriceCache: initialised at %s", db_path)
        except Exception as exc:
            logger.error("PriceCache.__init__: failed to initialise at %s: %s", db_path, exc)
            raise

    def get_cached_price(self, symbol: str, price_date: date) -> Optional[float]:
        """
        @brief Retrieve a cached price for a specific symbol and date.
        @param symbol Ticker symbol string.
        @param price_date The date for which to look up the price.
        @return Cached price as float, or None if not in cache.
        """
        try:
            rows = get_prices(self._engine, symbol, price_date, price_date)
            if rows:
                return float(rows[0]["price"])
            return None
        except Exception as exc:
            logger.error(
                "PriceCache.get_cached_price: error for %s on %s: %s",
                symbol, price_date, exc,
            )
            return None

    def cache_price(
        self,
        symbol: str,
        price_date: date,
        price: float,
        provider: str = "unknown",
    ) -> bool:
        """
        @brief Cache a price for a symbol on a specific date.

        If a price already exists for this symbol+date, the request is
        silently ignored (historical prices are immutable).

        @param symbol Ticker symbol string.
        @param price_date Date of the price observation.
        @param price Price value as float.
        @param provider Provider identifier string.
        @return True if the price was newly inserted, False if already cached or on error.
        """
        try:
            return upsert_price(self._engine, symbol, price_date, price, provider)
        except Exception as exc:
            logger.error(
                "PriceCache.cache_price: error for %s on %s: %s",
                symbol, price_date, exc,
            )
            return False

    def get_cached_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> dict[date, float]:
        """
        @brief Retrieve all cached prices for a symbol within a date range.
        @param symbol Ticker symbol string.
        @param start Inclusive start date.
        @param end Inclusive end date.
        @return Dict mapping date -> price for all cached dates in the range.
        """
        try:
            rows = get_prices(self._engine, symbol, start, end)
            result: dict[date, float] = {}
            for row in rows:
                try:
                    row_date = date.fromisoformat(row["date"])
                    result[row_date] = float(row["price"])
                except Exception as re:
                    logger.warning(
                        "PriceCache.get_cached_history: bad row for %s: %s", symbol, re
                    )
                    continue
            logger.debug(
                "PriceCache.get_cached_history: %s %s–%s → %d cached points",
                symbol, start, end, len(result),
            )
            return result
        except Exception as exc:
            logger.error(
                "PriceCache.get_cached_history: error for %s: %s", symbol, exc
            )
            return {}

    def cache_history(
        self,
        symbol: str,
        history: dict[date, float],
        provider: str = "unknown",
    ) -> int:
        """
        @brief Bulk-cache historical prices for a symbol.

        Existing dates are skipped (immutability rule). Only newly inserted
        records are counted.

        @param symbol Ticker symbol string.
        @param history Dict mapping date -> price.
        @param provider Provider identifier string.
        @return Number of newly inserted price records.
        """
        inserted = 0
        try:
            for price_date, price in history.items():
                try:
                    ok = upsert_price(self._engine, symbol, price_date, price, provider)
                    if ok:
                        inserted += 1
                except Exception as ie:
                    logger.warning(
                        "PriceCache.cache_history: error inserting %s on %s: %s",
                        symbol, price_date, ie,
                    )
                    continue
            logger.debug(
                "PriceCache.cache_history: %s — inserted %d / %d records",
                symbol, inserted, len(history),
            )
            return inserted
        except Exception as exc:
            logger.error(
                "PriceCache.cache_history: error for %s: %s", symbol, exc
            )
            return inserted
