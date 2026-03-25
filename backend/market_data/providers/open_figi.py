"""
@file open_figi.py
@brief OpenFIGI ISIN/SEDOL-to-ticker resolver for LifeLedger.

OpenFIGI is a public mapping API that converts ISIN and SEDOL identifiers
to exchange ticker symbols. It is not a BaseProvider — it is a resolver
used upstream of the provider chain.

Free tier limits: 250 requests per day without an API key.
Tracking is in-memory per process lifetime; the counter resets on restart
or at midnight UTC.
"""

import logging
from datetime import date
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

_OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
_DAILY_LIMIT = 250


class OpenFIGIProvider:
    """
    @brief ISIN and SEDOL to ticker resolver backed by the OpenFIGI mapping API.

    This class is NOT a BaseProvider — it is used as a pre-resolution step
    before querying price providers. It converts ISIN or SEDOL identifiers
    to exchange ticker symbols that can then be used with yfinance, Alpha
    Vantage, or Finnhub.

    Free tier: 250 requests per day. An optional API key can be configured
    in the SQLite api_keys table under provider='open_figi' to increase limits.
    """

    def __init__(
        self,
        get_api_key_fn: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        """
        @brief Initialise the OpenFIGI provider.
        @param get_api_key_fn Optional callable returning an OpenFIGI API key string.
               Pass None to use the unauthenticated (250/day) tier.
        """
        self._get_api_key = get_api_key_fn
        self._request_count: int = 0
        self._reset_date: Optional[date] = None

    def _check_rate_limit(self) -> bool:
        """
        @brief Check and increment the daily request counter.
        @return True if within the daily limit, False if exhausted.
        """
        today = date.today()
        if self._reset_date != today:
            self._reset_date = today
            self._request_count = 0

        if self._request_count >= _DAILY_LIMIT:
            logger.warning(
                "OpenFIGIProvider: daily limit of %d requests reached", _DAILY_LIMIT
            )
            return False

        self._request_count += 1
        remaining = _DAILY_LIMIT - self._request_count
        if remaining <= 10:
            logger.warning(
                "OpenFIGIProvider: only %d requests remaining today", remaining
            )
        return True

    def _post(self, payload: list[dict]) -> Optional[list]:
        """
        @brief POST a mapping request to the OpenFIGI API.
        @param payload List of mapping request dicts.
        @return List of response dicts, or None on failure.
        """
        if not self._check_rate_limit():
            return None

        headers = {"Content-Type": "application/json"}
        if self._get_api_key:
            try:
                key = self._get_api_key()
                if key:
                    headers["X-OPENFIGI-APIKEY"] = key
            except Exception as exc:
                logger.debug("OpenFIGIProvider._post: key retrieval failed: %s", exc)

        try:
            response = httpx.post(
                _OPENFIGI_URL,
                json=payload,
                headers=headers,
                timeout=15.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "OpenFIGIProvider._post: HTTP %d: %s",
                exc.response.status_code, exc,
            )
            return None
        except Exception as exc:
            logger.error("OpenFIGIProvider._post: %s", exc)
            return None

    def _extract_ticker(self, response_item: dict) -> Optional[str]:
        """
        @brief Extract the best ticker from a single OpenFIGI mapping response item.

        Prefers equities listed on major exchanges (XLON, XNAS, XNYS).

        @param response_item A single item from the OpenFIGI response list.
        @return Ticker string or None if no usable result found.
        """
        try:
            data = response_item.get("data", [])
            if not data:
                return None

            # Preference order: XLON (LSE), XNAS (NASDAQ), XNYS (NYSE), then first
            preferred_mics = ["XLON", "XNAS", "XNYS"]
            for mic in preferred_mics:
                for item in data:
                    if item.get("exchCode") == mic or item.get("primaryMIC") == mic:
                        ticker = item.get("ticker")
                        if ticker:
                            # For LSE tickers, append .L for yfinance compatibility
                            if mic == "XLON" and not ticker.endswith(".L"):
                                ticker = f"{ticker}.L"
                            return str(ticker)

            # Fall through: return the first available ticker
            first = data[0]
            ticker = first.get("ticker")
            if ticker:
                return str(ticker)
            return None
        except Exception as exc:
            logger.error("OpenFIGIProvider._extract_ticker: %s", exc)
            return None

    def resolve_isin(self, isin: str) -> Optional[str]:
        """
        @brief Resolve an ISIN to a ticker symbol using OpenFIGI.

        Posts a single-item mapping request with idType='ID_ISIN'. Returns
        the best matching ticker, preferring LSE, NASDAQ, or NYSE listings.

        @param isin ISIN code string (e.g. 'IE00BK5BQT80').
        @return Ticker symbol string, or None if resolution fails.
        """
        try:
            payload = [{"idType": "ID_ISIN", "idValue": isin}]
            response = self._post(payload)
            if not response or len(response) == 0:
                logger.warning(
                    "OpenFIGIProvider.resolve_isin: no response for ISIN %s", isin
                )
                return None

            ticker = self._extract_ticker(response[0])
            if ticker:
                logger.debug(
                    "OpenFIGIProvider.resolve_isin: %s → %s", isin, ticker
                )
            else:
                logger.warning(
                    "OpenFIGIProvider.resolve_isin: could not extract ticker for %s", isin
                )
            return ticker
        except Exception as exc:
            logger.error(
                "OpenFIGIProvider.resolve_isin: error for ISIN %s: %s", isin, exc
            )
            return None

    def resolve_sedol(self, sedol: str) -> Optional[str]:
        """
        @brief Resolve a SEDOL to a ticker symbol using OpenFIGI.

        Posts a single-item mapping request with idType='ID_SEDOL'.

        @param sedol SEDOL code string (7 characters).
        @return Ticker symbol string, or None if resolution fails.
        """
        try:
            payload = [{"idType": "ID_SEDOL", "idValue": sedol}]
            response = self._post(payload)
            if not response or len(response) == 0:
                logger.warning(
                    "OpenFIGIProvider.resolve_sedol: no response for SEDOL %s", sedol
                )
                return None

            ticker = self._extract_ticker(response[0])
            if ticker:
                logger.debug(
                    "OpenFIGIProvider.resolve_sedol: %s → %s", sedol, ticker
                )
            else:
                logger.warning(
                    "OpenFIGIProvider.resolve_sedol: could not extract ticker for %s", sedol
                )
            return ticker
        except Exception as exc:
            logger.error(
                "OpenFIGIProvider.resolve_sedol: error for SEDOL %s: %s", sedol, exc
            )
            return None
