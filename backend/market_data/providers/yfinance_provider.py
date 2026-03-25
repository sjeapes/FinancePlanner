"""
@file yfinance_provider.py
@brief yfinance-backed market data provider for LifeLedger.

Uses the unofficial Yahoo Finance API via the yfinance library.
No API key is required.

UK LSE-listed securities use the '.L' suffix convention on Yahoo Finance,
e.g. 'VWRP.L' for the Vanguard FTSE All-World ETF listed on the London
Stock Exchange. US tickers require no suffix (e.g. 'AAPL').
"""

import logging
from datetime import date, timedelta
from typing import Optional

from backend.market_data.providers.base import BaseProvider, PricePoint, SymbolResult

logger = logging.getLogger(__name__)


class YFinanceProvider(BaseProvider):
    """
    @brief Market data provider backed by yfinance (Yahoo Finance).

    Primary provider in the LifeLedger fallback chain. Supports equities,
    ETFs, and mutual funds listed on major exchanges.

    Note on LSE tickers: London Stock Exchange securities must use the '.L'
    suffix on Yahoo Finance (e.g. 'VWRP.L', '0P0000YXUZ.L').
    """

    @property
    def provider_name(self) -> str:
        """
        @brief Return the provider identifier.
        @return String 'yfinance'.
        """
        return "yfinance"

    def fetch_price(self, symbol: str, price_date: Optional[date] = None) -> Optional[float]:
        """
        @brief Fetch the closing price for a symbol on a given date, or latest.

        If price_date is None, returns the most recent available closing price.
        Falls back to the previous trading day if the requested date has no data
        (e.g. weekends, holidays).

        @param symbol Exchange ticker symbol. Use '.L' suffix for LSE tickers.
        @param price_date Date for the price; None returns the latest close.
        @return Closing price as float, or None on any failure.
        """
        try:
            import yfinance as yf

            if price_date is None:
                ticker = yf.Ticker(symbol)
                info = ticker.fast_info
                price = getattr(info, "last_price", None)
                if price is not None and price > 0:
                    logger.debug(
                        "YFinanceProvider.fetch_price: %s latest=%.4f", symbol, price
                    )
                    return float(price)
                # Fallback: download last 5 trading days and take the last close
                hist = yf.download(
                    symbol,
                    period="5d",
                    progress=False,
                    auto_adjust=True,
                )
                if hist is None or hist.empty:
                    logger.warning(
                        "YFinanceProvider.fetch_price: no data for %s", symbol
                    )
                    return None
                close_col = "Close"
                if close_col not in hist.columns:
                    logger.warning(
                        "YFinanceProvider.fetch_price: no Close column for %s", symbol
                    )
                    return None
                last = float(hist[close_col].iloc[-1])
                logger.debug(
                    "YFinanceProvider.fetch_price: %s (fallback) latest=%.4f", symbol, last
                )
                return last
            else:
                # Fetch a narrow window around the requested date
                start = price_date - timedelta(days=5)
                end = price_date + timedelta(days=1)
                hist = yf.download(
                    symbol,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    progress=False,
                    auto_adjust=True,
                )
                if hist is None or hist.empty:
                    logger.warning(
                        "YFinanceProvider.fetch_price: no data for %s on %s",
                        symbol, price_date,
                    )
                    return None
                close_col = "Close"
                if close_col not in hist.columns:
                    return None
                # Take the last available day on or before the requested date
                price_str = price_date.isoformat()
                matching = hist[hist.index.astype(str) <= price_str]
                if matching.empty:
                    return None
                last = float(matching[close_col].iloc[-1])
                logger.debug(
                    "YFinanceProvider.fetch_price: %s on %s = %.4f",
                    symbol, price_date, last,
                )
                return last
        except Exception as exc:
            logger.error(
                "YFinanceProvider.fetch_price: error for %s: %s", symbol, exc
            )
            return None

    def fetch_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[PricePoint]:
        """
        @brief Fetch historical daily closing prices for a symbol.

        Uses yf.download() with auto_adjust=True to apply dividend/split
        adjustments.

        @param symbol Exchange ticker symbol. Use '.L' suffix for LSE tickers.
        @param start Inclusive start date.
        @param end Inclusive end date.
        @return List of PricePoint objects, ordered date ascending. Empty on failure.
        """
        try:
            import yfinance as yf

            end_fetch = end + timedelta(days=1)
            hist = yf.download(
                symbol,
                start=start.isoformat(),
                end=end_fetch.isoformat(),
                progress=False,
                auto_adjust=True,
            )
            if hist is None or hist.empty:
                logger.warning(
                    "YFinanceProvider.fetch_history: no data for %s %s–%s",
                    symbol, start, end,
                )
                return []

            results: list[PricePoint] = []
            for idx, row in hist.iterrows():
                try:
                    row_date = idx.date() if hasattr(idx, "date") else idx
                    close = row.get("Close") if hasattr(row, "get") else row["Close"]
                    volume = row.get("Volume") if hasattr(row, "get") else row.get("Volume")
                    if close is None or (hasattr(close, "__float__") and close != close):
                        continue
                    results.append(
                        PricePoint(
                            date=row_date,
                            price=float(close),
                            volume=float(volume) if volume is not None else None,
                        )
                    )
                except Exception as row_exc:
                    logger.warning(
                        "YFinanceProvider.fetch_history: bad row for %s at %s: %s",
                        symbol, idx, row_exc,
                    )
                    continue

            logger.debug(
                "YFinanceProvider.fetch_history: %s returned %d points",
                symbol, len(results),
            )
            return results
        except Exception as exc:
            logger.error(
                "YFinanceProvider.fetch_history: error for %s: %s", symbol, exc
            )
            return []

    def search_symbol(self, query: str) -> list[SymbolResult]:
        """
        @brief Search for instruments matching a query string via yfinance.

        Attempts yf.Search() first; falls back to yf.Ticker(query).info for
        direct ticker lookups.

        @param query Search string (ticker, name, or partial name).
        @return List of SymbolResult objects. Empty list on failure.
        """
        try:
            import yfinance as yf

            results: list[SymbolResult] = []

            # Try yf.Search if available (yfinance >= 0.2.37)
            try:
                search = yf.Search(query, max_results=10)
                quotes = getattr(search, "quotes", [])
                for q in quotes:
                    try:
                        results.append(
                            SymbolResult(
                                ticker=str(q.get("symbol", "")),
                                name=str(q.get("longname", q.get("shortname", ""))),
                                exchange=str(q.get("exchange", "")),
                                currency=str(q.get("currency", "")),
                            )
                        )
                    except Exception as qe:
                        logger.debug(
                            "YFinanceProvider.search_symbol: skipping quote %s: %s", q, qe
                        )
                if results:
                    return results
            except Exception as se:
                logger.debug(
                    "YFinanceProvider.search_symbol: Search() not available: %s", se
                )

            # Fallback: direct ticker lookup
            try:
                ticker = yf.Ticker(query)
                info = ticker.info or {}
                if info.get("symbol"):
                    results.append(
                        SymbolResult(
                            ticker=str(info.get("symbol", query)),
                            name=str(info.get("longName", info.get("shortName", query))),
                            exchange=str(info.get("exchange", "")),
                            currency=str(info.get("currency", "")),
                        )
                    )
            except Exception as te:
                logger.debug(
                    "YFinanceProvider.search_symbol: ticker fallback failed for %s: %s",
                    query, te,
                )

            logger.debug(
                "YFinanceProvider.search_symbol: '%s' → %d results", query, len(results)
            )
            return results
        except Exception as exc:
            logger.error(
                "YFinanceProvider.search_symbol: error for '%s': %s", query, exc
            )
            return []
