"""
@file base.py
@brief Abstract base class and shared data types for market data providers.

All concrete provider implementations must inherit from BaseProvider and
implement all abstract methods. PricePoint and SymbolResult are the canonical
data transfer types used throughout the market data module.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


# ── Shared data types ─────────────────────────────────────────────────────────

@dataclass
class PricePoint:
    """
    @brief A single price observation for a given date.
    @param date Date of the price.
    @param price Closing price as a float.
    @param volume Trading volume for the day (None if unavailable).
    """
    date: date
    price: float
    volume: Optional[float] = None


@dataclass
class SymbolResult:
    """
    @brief A symbol search result returned by a provider.
    @param ticker Exchange ticker symbol.
    @param name Full instrument name.
    @param exchange Exchange code (e.g. 'LSE', 'NASDAQ').
    @param currency Trading currency ISO code.
    """
    ticker: str
    name: str
    exchange: str
    currency: str


# ── Abstract base provider ────────────────────────────────────────────────────

class BaseProvider(ABC):
    """
    @brief Abstract base class for all market data providers.

    Concrete implementations must implement fetch_price, fetch_history,
    search_symbol, and the provider_name property.
    """

    @abstractmethod
    def fetch_price(self, symbol: str, price_date: Optional[date] = None) -> Optional[float]:
        """
        @brief Fetch the price for a given symbol on a given date.

        If price_date is None, returns the latest available closing price.

        @param symbol Exchange ticker symbol.
        @param price_date Date for which to fetch the price; None = latest.
        @return Price as float, or None if unavailable.
        """
        ...

    @abstractmethod
    def fetch_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[PricePoint]:
        """
        @brief Fetch historical closing prices for a date range.
        @param symbol Exchange ticker symbol.
        @param start Inclusive start date.
        @param end Inclusive end date.
        @return List of PricePoint objects ordered by date ascending.
        """
        ...

    @abstractmethod
    def search_symbol(self, query: str) -> list[SymbolResult]:
        """
        @brief Search for instruments matching a query string.
        @param query Search term (name, ticker, or ISIN fragment).
        @return List of SymbolResult objects.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        @brief The provider identifier string.
        @return Provider name (e.g. 'yfinance', 'alpha_vantage').
        """
        ...
