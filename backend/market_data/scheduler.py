"""
@file scheduler.py
@brief Market data refresh scheduler for LifeLedger.

Tracks when each SymbolLink was last refreshed and determines whether
a refresh is due based on the symbol's refresh_schedule field.

Supported schedules:
  - on_app_open: refresh every time the application starts
  - daily: refresh at most once per calendar day
  - weekly: refresh at most once per calendar week
  - manual: never auto-refresh; only refresh when explicitly requested
"""

import logging
from datetime import date, datetime
from typing import Optional

from backend.models.models import SymbolLink

logger = logging.getLogger(__name__)

SCHEDULE_ON_APP_OPEN = "on_app_open"
SCHEDULE_DAILY = "daily"
SCHEDULE_WEEKLY = "weekly"
SCHEDULE_MANUAL = "manual"


class RefreshScheduler:
    """
    @brief In-memory tracker for market data refresh scheduling.

    Maintains a dict of symbol -> last refresh timestamp and exposes
    should_refresh() to decide whether a new fetch is needed.
    No external scheduler library is used.
    """

    def __init__(self) -> None:
        """
        @brief Initialise the scheduler with an empty refresh record.
        """
        # symbol -> last refresh datetime
        self._last_refreshed: dict[str, datetime] = {}
        # Track whether the app has just opened (for on_app_open schedule)
        self._app_open_symbols: set[str] = set()

    def mark_app_opened(self) -> None:
        """
        @brief Signal that the application has opened.

        Clears the set of symbols that have been refreshed since open,
        so all on_app_open symbols will be refreshed once.
        """
        self._app_open_symbols.clear()
        logger.debug("RefreshScheduler.mark_app_opened: app open signals cleared")

    def should_refresh(self, symbol_link: SymbolLink) -> bool:
        """
        @brief Determine whether a symbol should be refreshed now.

        Decision logic:
        - manual: always False
        - on_app_open: True if not yet refreshed since app opened
        - daily: True if last refresh was on a previous calendar day
        - weekly: True if last refresh was in a previous calendar week
        - Unknown schedule: defaults to daily behaviour

        @param symbol_link SymbolLink dataclass instance with refresh_schedule field.
        @return True if a refresh should be triggered.
        """
        try:
            if not symbol_link.auto_refresh:
                return False

            schedule = symbol_link.refresh_schedule.lower()
            symbol = symbol_link.symbol

            if schedule == SCHEDULE_MANUAL:
                return False

            last = self._last_refreshed.get(symbol)
            today = date.today()
            now = datetime.utcnow()

            if schedule == SCHEDULE_ON_APP_OPEN:
                if symbol in self._app_open_symbols:
                    return False
                return True

            if last is None:
                return True

            if schedule == SCHEDULE_DAILY:
                return last.date() < today

            if schedule == SCHEDULE_WEEKLY:
                days_since = (now - last).days
                return days_since >= 7

            # Unknown schedule: treat as daily
            logger.warning(
                "RefreshScheduler.should_refresh: unknown schedule '%s' for %s — defaulting to daily",
                schedule, symbol,
            )
            return last.date() < today

        except Exception as exc:
            logger.error(
                "RefreshScheduler.should_refresh: error for %s: %s",
                getattr(symbol_link, "symbol", "unknown"), exc,
            )
            return False

    def mark_refreshed(self, symbol: str) -> None:
        """
        @brief Record that a symbol has just been refreshed.

        Updates the last-refresh timestamp and marks on_app_open symbols
        as already refreshed for this session.

        @param symbol Ticker symbol string.
        """
        try:
            self._last_refreshed[symbol] = datetime.utcnow()
            self._app_open_symbols.add(symbol)
            logger.debug(
                "RefreshScheduler.mark_refreshed: %s refreshed at %s",
                symbol, self._last_refreshed[symbol],
            )
        except Exception as exc:
            logger.error(
                "RefreshScheduler.mark_refreshed: error for %s: %s", symbol, exc
            )

    def last_refresh_time(self, symbol: str) -> Optional[datetime]:
        """
        @brief Return the last refresh datetime for a symbol.
        @param symbol Ticker symbol string.
        @return Datetime of last refresh, or None if never refreshed.
        """
        return self._last_refreshed.get(symbol)

    def pending_symbols(self, symbol_links: list[SymbolLink]) -> list[SymbolLink]:
        """
        @brief Filter a list of SymbolLinks to those that need refreshing.
        @param symbol_links List of SymbolLink dataclass instances.
        @return Subset of symbol_links where should_refresh() returns True.
        """
        try:
            return [sl for sl in symbol_links if self.should_refresh(sl)]
        except Exception as exc:
            logger.error("RefreshScheduler.pending_symbols: error: %s", exc)
            return []
