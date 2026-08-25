"""
@file statement_parser.py
@brief Phase 10 financial statement parser for LifeLedger.

Parses uploaded bank and broker statements to extract current account
balances, holdings, and historical balance series for import into the
scenario YAML.

Supported formats
-----------------
OFX / QFX
    Open Financial Exchange format exported by most UK and US banks.
    UK: Barclays, HSBC, NatWest, Lloyds, Santander, Monzo, Starling,
        Nationwide, Halifax, Chase UK, Revolut.
    US: Chase, Bank of America, Wells Fargo, Citibank, Fidelity,
        Schwab, Vanguard, TD Ameritrade, E*TRADE, Merrill Edge.

CSV — bank statement
    Generic date + balance (or date + amount) format. Handles:
    UK: Monzo, Starling, Barclays, HSBC, NatWest, generic CSV exports.
    US: Chase, Bank of America, Wells Fargo, Citibank standard downloads.

CSV — broker / investment statement
    Holdings format with Description, Units, Price, Value columns.
    UK: Hargreaves Lansdown, Vanguard UK, AJ Bell, Interactive Brokers,
        Freetrade, Fidelity UK.
    US: Fidelity, Schwab, Vanguard US, TD Ameritrade, E*TRADE, Robinhood,
        Interactive Brokers, Merrill Edge.

PDF
    Text extraction via pdfplumber. Falls back gracefully when not installed.

Account types
-------------
UK: general, savings, cash_ISA, ISA (S&S ISA), GIA, SIPP, workplace_DC
US: general, savings, money_market, taxable_brokerage, k401, roth_ira,
    ira, roth_401k, k403b, hsa, plan_529

Currency
--------
Automatically detected from OFX CURDEF, $ vs £ amount prefixes, column
headers, or filename heuristics. Defaults to GBP unless US signals
are detected.

@author  LifeLedger
@version 0.2.0
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger("lifeledger.statement_parser")


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HistoricalBalance:
    """
    @brief One date-balance data point from a statement.

    @param date_str  ISO 8601 date string (YYYY-MM-DD).
    @param balance   Account balance on that date.
    """
    date_str: str
    balance: float


@dataclass
class ParsedHolding:
    """
    @brief One investment holding from a broker statement.

    @param name      Security / fund name.
    @param isin      ISIN code (empty string if unknown).
    @param ticker    Ticker symbol (empty if unknown).
    @param units     Number of units or shares held.
    @param price     Price per unit in native currency.
    @param value     Total value (units × price).
    @param currency  Currency code.
    """
    name: str
    isin: str
    ticker: str
    units: float
    price: float
    value: float
    currency: str


@dataclass
class ParsedStatement:
    """
    @brief Full result of parsing a financial statement file.

    @param format            Detected file format ('ofx', 'csv_bank',
                             'csv_broker', 'pdf', 'unknown').
    @param institution       Guessed institution name (empty if unknown).
    @param jurisdiction      'uk' | 'us' | 'unknown'.
    @param account_name      Account name from statement or filename heuristic.
    @param suggested_type    Suggested LifeLedger account type.
    @param currency          Currency code (GBP or USD).
    @param current_balance   Most recent / closing balance.
    @param statement_date    Date of the closing balance (ISO 8601 string).
    @param historical        Sorted ascending list of (date, balance) points.
    @param holdings          Investment holdings (broker statements only).
    @param confidence        Parser confidence 0.0–1.0.
    @param warnings          List of parser warning messages.
    @param raw_text_preview  First 500 chars of raw content (for debugging).
    """
    format: str
    institution: str
    jurisdiction: str
    account_name: str
    suggested_type: str
    currency: str
    current_balance: float
    statement_date: str
    historical: list[HistoricalBalance]
    holdings: list[ParsedHolding]
    confidence: float
    warnings: list[str]
    raw_text_preview: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Institution keyword tables — UK and US
# ─────────────────────────────────────────────────────────────────────────────

_UK_INSTITUTION_HINTS: list[tuple[list[str], str]] = [
    (["barclays"],                              "Barclays"),
    (["hsbc"],                                  "HSBC"),
    (["natwest", "nat west", "natw"],           "NatWest"),
    (["lloyds"],                                "Lloyds"),
    (["santander"],                             "Santander"),
    (["monzo"],                                 "Monzo"),
    (["starling"],                              "Starling"),
    (["chase"],                                 "Chase UK"),
    (["nationwide"],                            "Nationwide"),
    (["halifax"],                               "Halifax"),
    (["revolut"],                               "Revolut"),
    (["virgin money", "virgin"],                "Virgin Money"),
    (["metro bank", "metrobank"],               "Metro Bank"),
    (["first direct", "firstdirect"],          "First Direct"),
    (["hargreaves", "hl.co.uk", "h.l."],        "Hargreaves Lansdown"),
    (["vanguard"],                              "Vanguard"),
    (["aj bell", "ajbell"],                     "AJ Bell"),
    (["interactive brokers", "ibkr"],           "Interactive Brokers"),
    (["freetrade"],                             "Freetrade"),
    (["fidelity"],                              "Fidelity"),
    (["trading 212", "trading212"],             "Trading 212"),
    (["etoro"],                                 "eToro"),
    (["nest pension", "nest.co.uk"],            "NEST Pension"),
    (["peoples pension", "people's pension"],   "People's Pension"),
    (["standard life"],                         "Standard Life"),
    (["aviva"],                                 "Aviva"),
    (["legal & general", "legal and general"],  "Legal & General"),
    (["royal london"],                          "Royal London"),
    (["scottish widows"],                       "Scottish Widows"),
    (["prudential"],                            "Prudential"),
]

_US_INSTITUTION_HINTS: list[tuple[list[str], str]] = [
    (["jpmorgan", "jp morgan", "chase bank",
      "chase.com"],                             "Chase"),
    (["bank of america", "bankofamerica",
      "bofa", "merrill edge", "merrill lynch"], "Bank of America / Merrill"),
    (["wells fargo", "wellsfargo"],             "Wells Fargo"),
    (["citibank", "citi bank", "citi.com"],     "Citibank"),
    (["us bank", "usbank", "u.s. bank"],        "US Bank"),
    (["discover bank", "discover.com"],         "Discover"),
    (["ally bank", "ally financial"],           "Ally Bank"),
    (["american express", "amex"],              "American Express"),
    (["capital one", "capitalone"],             "Capital One"),
    (["fidelity", "fidelity investments",
      "fidelity.com"],                          "Fidelity"),
    (["charles schwab", "schwab.com",
      "schwab", "tdameritrade", "td ameritrade"], "Schwab / TDA"),
    (["e*trade", "etrade", "e-trade"],          "E*TRADE"),
    (["robinhood"],                             "Robinhood"),
    (["betterment"],                            "Betterment"),
    (["wealthfront"],                           "Wealthfront"),
    (["sofi invest", "sofi"],                   "SoFi"),
    (["m1 finance", "m1finance"],               "M1 Finance"),
    (["public.com", "public invest"],           "Public"),
    (["coinbase"],                              "Coinbase"),
]

# Combined — searched in order; UK first (slight bias)
_ALL_INSTITUTION_HINTS = _UK_INSTITUTION_HINTS + _US_INSTITUTION_HINTS

# ─────────────────────────────────────────────────────────────────────────────
# Account type keyword tables
# ─────────────────────────────────────────────────────────────────────────────

_UK_TYPE_HINTS: list[tuple[list[str], str]] = [
    (["stocks & shares isa", "stocks and shares", "s&s isa",
      "ss isa"],                                "ISA"),
    (["cash isa", "cash individual savings"],   "cash_ISA"),
    (["sipp", "self-invested personal pension",
      "self invested"],                         "SIPP"),
    (["workplace", "employer pension", "dc pension",
      "nest pension", "peoples pension",
      "people's pension", "group personal"],    "workplace_DC"),
    (["gia", "general investment account"],     "GIA"),
    (["savings", "easy access", "fixed rate",
      "notice account"],                        "savings"),
    (["current account", "everyday account",
      "checking"],                              "general"),
]

_US_TYPE_HINTS: list[tuple[list[str], str]] = [
    (["roth 401k", "roth 401(k)",
      "designated roth"],                       "roth_401k"),
    (["401k", "401(k)", "four oh one"],         "k401"),
    (["403b", "403(b)"],                        "k403b"),
    (["roth ira", "roth individual retirement"], "roth_ira"),
    (["traditional ira", "trad ira",
      "ira ", " ira"],                          "ira"),
    (["hsa", "health savings account",
      "health saving"],                         "hsa"),
    (["529", "college savings", "education savings",
      "529 plan"],                              "plan_529"),
    (["money market", "mma ", " mma"],          "money_market"),
    (["brokerage", "taxable", "individual account",
      "non-retirement", "investment account"],  "taxable_brokerage"),
    (["savings account", "savings", "high yield"],
                                                "savings"),
    (["checking", "demand deposit", "checking account"],
                                                "general"),
]

_ALL_TYPE_HINTS = _UK_TYPE_HINTS + _US_TYPE_HINTS


def _guess_institution(text: str) -> tuple[str, str]:
    """
    @brief Guess institution name and jurisdiction from text signals.

    @param text  Combined text (filename + content preview).
    @return      Tuple (institution_name, jurisdiction): ('uk'|'us'|'unknown').
    """
    lower = text.lower()
    # Check US first for unambiguous signals
    for keywords, name in _US_INSTITUTION_HINTS:
        if any(k in lower for k in keywords):
            return name, "us"
    for keywords, name in _UK_INSTITUTION_HINTS:
        if any(k in lower for k in keywords):
            return name, "uk"
    return "", "unknown"


def _guess_account_type(text: str, jurisdiction: str) -> str:
    """
    @brief Guess the LifeLedger account type from text signals.

    @param text          Combined text (filename + content + account type raw).
    @param jurisdiction  'uk' | 'us' | 'unknown'.
    @return              LifeLedger account type string.
    """
    lower = text.lower()
    hints = _UK_TYPE_HINTS + _US_TYPE_HINTS
    for keywords, atype in hints:
        if any(k.strip() in lower for k in keywords):
            return atype
    # Defaults by jurisdiction
    if jurisdiction == "us":
        return "taxable_brokerage"
    return "general"


def _detect_currency(content: str, filename: str, ofx_curdef: str = "") -> str:
    """
    @brief Detect currency from OFX CURDEF, amount prefixes, or filename.

    @param content     Statement text content.
    @param filename    Original filename.
    @param ofx_curdef  CURDEF tag value from OFX (empty string if N/A).
    @return            Currency code: 'GBP' | 'USD' | 'EUR' | 'GBP'.
    """
    # OFX explicitly declares currency
    if ofx_curdef and len(ofx_curdef) == 3:
        return ofx_curdef.strip().upper()

    text_lower = (content[:2000] + " " + filename).lower()

    # US signals
    us_signals = ["$", " usd", "usd ", "united states", "dollar", "401k",
                  "401(k)", "roth ira", " ira ", ".com", "schwab", "fidelity",
                  "social security", "vanguard.com", "chase.com"]
    if any(s in text_lower for s in us_signals):
        # Only override to USD if no strong £ / GBP signals
        gbp_signals = ["£", " gbp", "gbp ", "pence", "sterling"]
        if not any(s in text_lower for s in gbp_signals):
            return "USD"

    return "GBP"


# ─────────────────────────────────────────────────────────────────────────────
# Date parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

_DATE_FORMATS = [
    "%Y%m%d%H%M%S",   # OFX compact with time
    "%Y%m%d",          # OFX compact date only
    "%d/%m/%Y",        # UK DD/MM/YYYY
    "%d-%m-%Y",        # UK with dashes
    "%Y-%m-%d",        # ISO 8601
    "%m/%d/%Y",        # US MM/DD/YYYY
    "%m-%d-%Y",        # US with dashes
    "%d %b %Y",        # "01 Jan 2024"
    "%d %B %Y",        # "01 January 2024"
    "%b %d, %Y",       # "Jan 01, 2024" (US format)
    "%B %d, %Y",       # "January 01, 2024"
]


def _parse_date(raw: str) -> Optional[date]:
    """
    @brief Try multiple date formats and return a date object or None.

    @param raw  Raw date string from the statement.
    @return     Parsed date or None if unparseable.
    """
    if not raw:
        return None
    raw = raw.strip().split(".")[0]   # trim timezone component if present
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _date_to_iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _clean_amount(raw: str) -> Optional[float]:
    """
    @brief Parse a monetary amount string, removing £/$, commas, parentheses.

    Parentheses indicate negative numbers in some accounting formats.
    @param raw  Raw amount string.
    @return     Float or None if unparseable.
    """
    if not raw:
        return None
    raw = raw.strip()
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.replace("(", "").replace(")", "")
    raw = re.sub(r"[£$€,\s]", "", raw)
    try:
        value = float(raw)
        return -value if negative else value
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# OFX / QFX parser
# ─────────────────────────────────────────────────────────────────────────────


def _parse_ofx(content: str, filename: str) -> ParsedStatement:
    """
    @brief Parse OFX or QFX format bank statement.

    Handles both SGML-style (classic OFX 1.x) and XML-style (OFX 2.x / QFX).
    Extracts current balance, statement date, and reconstructs a monthly
    balance series from STMTTRN transaction entries.

    Supports UK and US institutions. Currency detected from CURDEF tag.

    @param content   Full file text content.
    @param filename  Original filename for heuristics.
    @return          ParsedStatement.
    """

    def tag(name: str, text: str) -> Optional[str]:
        patterns = [
            rf"<{name}>\s*([^<\n]+)",
            rf"{name}:([^\n]+)",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    warnings: list[str] = []

    # Current balance
    bal_str = tag("BALAMT", content) or tag("LEDGERBAL", content)
    current = 0.0
    if bal_str:
        v = _clean_amount(bal_str)
        if v is not None:
            current = v
        else:
            warnings.append(f"Could not parse balance: {bal_str!r}")

    # Statement date
    date_raw = tag("DTASOF", content) or tag("DTEND", content) or tag("DTSTART", content)
    stmt_date = _date_to_iso(date.today())
    if date_raw:
        d = _parse_date(date_raw)
        if d:
            stmt_date = _date_to_iso(d)

    # Currency and jurisdiction
    curdef = (tag("CURDEF", content) or "").strip().upper()[:3]
    inst_raw = tag("ORG", content) or tag("FID", content) or ""
    institution, jurisdiction = _guess_institution(inst_raw + " " + filename + " " + content[:1000])
    currency = _detect_currency(content[:2000], filename, curdef)

    # Account type hint
    acct_type_raw = tag("ACCTTYPE", content) or ""
    suggested_type = _guess_account_type(
        content[:2000] + " " + filename + " " + acct_type_raw + " " + inst_raw,
        jurisdiction,
    )

    # Reconstruct historical balance from STMTTRN entries
    trn_pattern = re.compile(
        r"<STMTTRN>.*?<DTPOSTED>\s*(\d+).*?<TRNAMT>\s*([+-]?\d+\.?\d*)",
        re.DOTALL | re.IGNORECASE,
    )
    transactions: list[tuple[date, float]] = []
    for m in trn_pattern.finditer(content):
        d_raw, amt_raw = m.group(1), m.group(2)
        d_obj = _parse_date(d_raw)
        if d_obj:
            try:
                transactions.append((d_obj, float(amt_raw)))
            except ValueError:
                pass

    historical: list[HistoricalBalance] = []
    if transactions:
        transactions.sort(key=lambda x: x[0])
        running = current
        for d_obj, amt in reversed(transactions):
            running -= amt
            historical.append(HistoricalBalance(
                date_str=_date_to_iso(d_obj),
                balance=round(running + amt, 2),
            ))
        historical.reverse()
        monthly: dict[str, float] = {}
        for h in historical:
            monthly[h.date_str[:7]] = h.balance
        historical = [HistoricalBalance(date_str=k + "-01", balance=v)
                      for k, v in sorted(monthly.items())]

    acct_name = (tag("ACCTID", content) or institution or "Imported Account")[:60]

    logger.info(
        "OFX parse: institution=%s jurisdiction=%s currency=%s type=%s "
        "balance=%.2f txns=%d",
        institution, jurisdiction, currency, suggested_type, current, len(transactions),
    )

    return ParsedStatement(
        format="ofx",
        institution=institution,
        jurisdiction=jurisdiction,
        account_name=acct_name,
        suggested_type=suggested_type,
        currency=currency,
        current_balance=current,
        statement_date=stmt_date,
        historical=historical,
        holdings=[],
        confidence=0.90 if transactions else 0.70,
        warnings=warnings,
        raw_text_preview=content[:500],
    )


# ─────────────────────────────────────────────────────────────────────────────
# CSV bank statement parser
# ─────────────────────────────────────────────────────────────────────────────


# Possible date column names (case-insensitive)
_DATE_COL_NAMES = {
    "date", "transaction date", "posted date", "posting date", "trans date",
    "transaction", "datetime", "value date", "settlement date",
    "date of transaction",
}

# Possible balance column names
_BALANCE_COL_NAMES = {
    "balance", "running balance", "account balance", "closing balance",
    "available balance", "ledger balance", "balance (gbp)", "balance (usd)",
}

# Possible amount column names
_AMOUNT_COL_NAMES = {
    "amount", "credit", "debit", "transaction amount", "value",
    "net amount", "withdrawal", "deposit", "in/out", "money in",
    "money out", "credit (gbp)", "debit (gbp)", "credit (usd)", "debit (usd)",
    "amount (gbp)", "amount (usd)",
}


def _parse_csv_bank(content: str, filename: str) -> ParsedStatement:
    """
    @brief Parse a generic bank CSV statement (UK or US).

    Handles Monzo, Starling, Chase UK, Barclays, HSBC, NatWest, and US
    bank CSV exports (Chase, Bank of America, Wells Fargo, Citibank).

    @param content   Full CSV text.
    @param filename  Original filename for heuristics.
    @return          ParsedStatement.
    """
    warnings: list[str] = []
    institution, jurisdiction = _guess_institution(filename + " " + content[:600])
    currency = _detect_currency(content[:2000], filename)

    try:
        reader = csv.DictReader(io.StringIO(content))
        headers_raw = reader.fieldnames or []
    except Exception:
        return ParsedStatement(
            format="csv_bank", institution=institution, jurisdiction=jurisdiction,
            account_name=institution or "Imported Account", suggested_type="general",
            currency=currency, current_balance=0.0,
            statement_date=_date_to_iso(date.today()),
            historical=[], holdings=[], confidence=0.1,
            warnings=["CSV parse failed — invalid file structure"],
        )

    headers = {h.lower().strip() for h in headers_raw}
    headers_list = [h.lower().strip() for h in headers_raw]

    date_col    = next((h for h in headers_list if h in _DATE_COL_NAMES),    None)
    balance_col = next((h for h in headers_list if h in _BALANCE_COL_NAMES), None)
    amount_col  = next((h for h in headers_list if h in _AMOUNT_COL_NAMES),  None)

    if not date_col:
        warnings.append("Could not detect date column.")
    if not balance_col and not amount_col:
        warnings.append("Could not detect balance or amount column.")

    rows: list[tuple[date, float]] = []
    for row in reader:
        keys = {k.lower().strip(): v.strip() for k, v in row.items() if k}
        raw_date = keys.get(date_col or "", "")
        raw_bal  = keys.get(balance_col, "") if balance_col else ""
        raw_amt  = keys.get(amount_col,  "") if amount_col  else ""

        d_obj = _parse_date(raw_date) if raw_date else None
        if not d_obj:
            continue

        bal = _clean_amount(raw_bal)
        if bal is None:
            bal = _clean_amount(raw_amt)
        if d_obj and bal is not None:
            rows.append((d_obj, bal))

    rows.sort(key=lambda x: x[0])
    current   = rows[-1][1] if rows else 0.0
    stmt_date = _date_to_iso(rows[-1][0]) if rows else _date_to_iso(date.today())

    monthly: dict[str, float] = {}
    for d_obj, bal in rows:
        monthly[_date_to_iso(d_obj)[:7]] = bal
    historical = [HistoricalBalance(date_str=k + "-01", balance=v)
                  for k, v in sorted(monthly.items())]

    suggested_type = _guess_account_type(
        filename + " " + content[:600], jurisdiction,
    )

    logger.info(
        "CSV bank parse: institution=%s jurisdiction=%s currency=%s rows=%d balance=%.2f",
        institution, jurisdiction, currency, len(rows), current,
    )

    return ParsedStatement(
        format="csv_bank",
        institution=institution,
        jurisdiction=jurisdiction,
        account_name=institution or "Imported Bank Account",
        suggested_type=suggested_type,
        currency=currency,
        current_balance=current,
        statement_date=stmt_date,
        historical=historical,
        holdings=[],
        confidence=0.80 if rows else 0.25,
        warnings=warnings,
        raw_text_preview=content[:500],
    )


# ─────────────────────────────────────────────────────────────────────────────
# CSV broker / investment statement parser
# ─────────────────────────────────────────────────────────────────────────────

# Each broker has subtly different column layouts.
# We try a general detection first, then specific overrides.

# UK broker column name patterns
_BROKER_UK_COLUMNS = {
    "name":  {"security", "description", "stock", "fund", "name", "holding",
              "instrument", "asset", "security description"},
    "units": {"units", "quantity", "shares", "number of units", "holding units"},
    "price": {"price", "unit cost", "unit price", "price (p)", "price per unit",
              "latest price"},
    "value": {"value", "market value", "total value", "current value",
              "value (£)", "value(£)", "total (£)"},
    "isin":  {"isin", "isin code"},
    "ticker":{"symbol", "ticker", "sedol"},
}

# US broker column name patterns (Fidelity, Schwab, Vanguard US, E*TRADE)
_BROKER_US_COLUMNS = {
    "name":  {"security description", "security name", "description",
              "symbol description", "investment name", "fund name",
              "security", "name"},
    "units": {"quantity", "shares", "quantity owned", "current shares",
              "number of shares", "units"},
    "price": {"price", "current price", "price/share", "price per share",
              "last price", "closing price"},
    "value": {"current value", "market value", "total value",
              "value ($)", "value(usd)", "amount", "total"},
    "ticker":{"symbol", "ticker", "ticker symbol"},
    "isin":  {"isin"},
}


def _find_col(headers: list[str], patterns: set[str]) -> Optional[str]:
    """@brief Find the first header name matching a set of patterns."""
    for h in headers:
        if h in patterns:
            return h
    return None


def _parse_csv_broker(content: str, filename: str) -> ParsedStatement:
    """
    @brief Parse a broker or investment platform CSV statement (UK or US).

    Detects holdings-format CSVs. UK brokers (Hargreaves Lansdown, Vanguard
    UK, AJ Bell, Freetrade) and US brokers (Fidelity, Schwab, Vanguard US,
    TD Ameritrade, E*TRADE, Robinhood).

    Price columns in pence (HL format) are automatically converted to pounds.

    @param content   Full CSV text.
    @param filename  Original filename for heuristics.
    @return          ParsedStatement.
    """
    warnings: list[str] = []
    institution, jurisdiction = _guess_institution(filename + " " + content[:600])
    currency = _detect_currency(content[:2000], filename)

    try:
        reader = csv.DictReader(io.StringIO(content))
        headers_raw = reader.fieldnames or []
    except Exception:
        return ParsedStatement(
            format="csv_broker", institution=institution, jurisdiction=jurisdiction,
            account_name=institution or "Imported Investment Account",
            suggested_type="taxable_brokerage" if jurisdiction == "us" else "ISA",
            currency=currency, current_balance=0.0,
            statement_date=_date_to_iso(date.today()),
            historical=[], holdings=[], confidence=0.1,
            warnings=["CSV parse failed"],
        )

    headers = [h.lower().strip() for h in headers_raw]

    # Pick column set based on jurisdiction hint
    if jurisdiction == "us":
        col_patterns = _BROKER_US_COLUMNS
    else:
        col_patterns = {**_BROKER_UK_COLUMNS, **_BROKER_US_COLUMNS}  # try both

    name_col   = _find_col(headers, col_patterns["name"])
    units_col  = _find_col(headers, col_patterns["units"])
    price_col  = _find_col(headers, col_patterns["price"])
    value_col  = _find_col(headers, col_patterns["value"])
    isin_col   = _find_col(headers, col_patterns.get("isin", set()))
    ticker_col = _find_col(headers, col_patterns.get("ticker", set()))

    # Detect if price is in pence (common in UK HL exports)
    price_in_pence = price_col and "p)" in price_col

    holdings: list[ParsedHolding] = []
    total_value = 0.0

    for row in reader:
        keys = {k.lower().strip(): (v or "").strip() for k, v in row.items() if k}

        name = keys.get(name_col or "", "").strip()
        if not name or name.lower() in {
            "total", "cash", "", "grand total", "subtotal",
            "money market", "total portfolio value",
        }:
            # Catch explicit total rows
            if name.lower() in {"total", "grand total", "total portfolio value"} and value_col:
                v = _clean_amount(keys.get(value_col, ""))
                if v:
                    total_value = v
            continue

        raw_units = keys.get(units_col or "", "")
        raw_price = keys.get(price_col or "", "")
        raw_value = keys.get(value_col or "", "")
        isin      = keys.get(isin_col   or "", "").strip()
        ticker    = keys.get(ticker_col or "", "").strip()

        units = _clean_amount(re.sub(r"[,\s]", "", raw_units)) or 0.0
        price_raw = _clean_amount(re.sub(r"[p£$€,\s]", "", raw_price)) or 0.0
        if price_in_pence and price_raw > 0:
            price_raw /= 100.0   # pence → pounds
        value = _clean_amount(re.sub(r"[£$€,\s]", "", raw_value)) or (units * price_raw)

        if value > 0:
            holdings.append(ParsedHolding(
                name=name, isin=isin, ticker=ticker,
                units=round(units, 6), price=round(price_raw, 4),
                value=round(value, 2), currency=currency,
            ))
            total_value += value

    if total_value == 0.0:
        total_value = sum(h.value for h in holdings)

    suggested_type = _guess_account_type(
        filename + " " + content[:600], jurisdiction,
    )
    if suggested_type in {"general", "savings"} and jurisdiction == "us":
        suggested_type = "taxable_brokerage"
    elif suggested_type in {"general", "savings"}:
        suggested_type = "ISA"

    logger.info(
        "CSV broker parse: institution=%s jurisdiction=%s currency=%s "
        "holdings=%d total=%.2f",
        institution, jurisdiction, currency, len(holdings), total_value,
    )

    return ParsedStatement(
        format="csv_broker",
        institution=institution,
        jurisdiction=jurisdiction,
        account_name=institution or "Imported Investment Account",
        suggested_type=suggested_type,
        currency=currency,
        current_balance=total_value,
        statement_date=_date_to_iso(date.today()),
        historical=[],
        holdings=holdings,
        confidence=0.85 if holdings else 0.30,
        warnings=warnings,
        raw_text_preview=content[:500],
    )


# ─────────────────────────────────────────────────────────────────────────────
# PDF parser
# ─────────────────────────────────────────────────────────────────────────────


def _parse_pdf(raw_bytes: bytes, filename: str) -> ParsedStatement:
    """
    @brief Extract text from a PDF and parse balance information.

    Uses pdfplumber. Works with UK and US pension/broker/bank statements.
    Detects institution and account type from extracted text.

    @param raw_bytes  Raw PDF bytes.
    @param filename   Original filename for heuristics.
    @return           ParsedStatement.
    """
    warnings: list[str] = []
    text = ""

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            for page in pdf.pages[:8]:
                text += (page.extract_text() or "") + "\n"
    except ImportError:
        warnings.append(
            "pdfplumber is not installed — PDF text extraction unavailable. "
            "Install with: pip install pdfplumber>=0.11"
        )
        institution, jurisdiction = _guess_institution(filename)
        return ParsedStatement(
            format="pdf", institution=institution, jurisdiction=jurisdiction,
            account_name=filename.replace(".pdf", ""),
            suggested_type="general", currency="GBP",
            current_balance=0.0, statement_date=_date_to_iso(date.today()),
            historical=[], holdings=[], confidence=0.0, warnings=warnings,
        )
    except Exception as exc:
        warnings.append(f"PDF read error: {exc}")
        institution, jurisdiction = _guess_institution(filename)
        return ParsedStatement(
            format="pdf", institution=institution, jurisdiction=jurisdiction,
            account_name=filename, suggested_type="general", currency="GBP",
            current_balance=0.0, statement_date=_date_to_iso(date.today()),
            historical=[], holdings=[], confidence=0.0, warnings=warnings,
        )

    institution, jurisdiction = _guess_institution(filename + " " + text[:1500])
    currency = _detect_currency(text[:3000], filename)
    suggested_type = _guess_account_type(
        filename + " " + text[:3000], jurisdiction,
    )

    curr_sym = "\\$" if currency == "USD" else "£"

    # Balance extraction patterns (ordered by specificity)
    balance_patterns = [
        # Labelled totals
        r"(?:total (?:portfolio |account )?value|portfolio value|account value|"
        r"market value|closing balance|account balance|current value|"
        r"balance as (?:at|of))[^\d£$]{0,30}[£$]?\s*([\d,]+\.?\d{0,2})",
        # US: "Estimated Value" or "Total Account Value"
        r"(?:estimated value|total account value|total assets|"
        r"portfolio total)[^\d$]{0,30}\$?\s*([\d,]+\.?\d{0,2})",
        # UK: largest £/$ figure near "total" on a line
        r"(?:total)[^\n]{0,40}[£$]([\d,]+\.?\d{0,2})",
    ]

    current = 0.0
    for pat in balance_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            v = _clean_amount(m.group(1))
            if v and v > 0:
                current = v
                break

    # Fallback: largest currency-symbol amount
    if current == 0.0:
        all_amounts = re.findall(rf"[{curr_sym}£]([\d,]+\.?\d{{0,2}})", text)
        parsed = [_clean_amount(a) for a in all_amounts]
        parsed = [v for v in parsed if v and v > 0]
        if parsed:
            current = max(parsed)

    logger.info(
        "PDF parse: institution=%s jurisdiction=%s currency=%s balance=%.2f",
        institution, jurisdiction, currency, current,
    )

    return ParsedStatement(
        format="pdf",
        institution=institution,
        jurisdiction=jurisdiction,
        account_name=institution or filename.replace(".pdf", ""),
        suggested_type=suggested_type,
        currency=currency,
        current_balance=current,
        statement_date=_date_to_iso(date.today()),
        historical=[],
        holdings=[],
        confidence=0.60 if current > 0 else 0.20,
        warnings=warnings,
        raw_text_preview=text[:500],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Format detection
# ─────────────────────────────────────────────────────────────────────────────


def _is_ofx(content: str) -> bool:
    return bool(re.search(
        r"OFXHEADER|<OFX>|<STMTRS>|<INVSTMTRS>|<BANKMSGSRSV1>",
        content[:3000], re.IGNORECASE,
    ))


def _is_broker_csv(content: str) -> bool:
    lower = content[:1500].lower()
    broker_signals = {
        "units", "quantity", "shares", "isin", "unit cost", "unit price",
        "holding", "instrument", "security description", "symbol description",
        "fund name", "ticker",
    }
    return any(s in lower for s in broker_signals)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


def parse_statement(
    raw_bytes: bytes,
    filename: str,
    content_type: str = "",
) -> ParsedStatement:
    """
    @brief Parse a financial statement file and return structured data.

    Detects format (OFX/QFX, CSV bank, CSV broker, PDF) and delegates
    to the appropriate parser. Supports both UK and US institutions,
    account types, and currencies.

    @param raw_bytes     Raw file bytes.
    @param filename      Original filename (used for format detection and
                         institution/jurisdiction heuristics).
    @param content_type  MIME type hint (optional).
    @return              ParsedStatement with current value, historical
                         series, and optional holdings.
    """
    logger.info("parse_statement: filename=%s size=%d bytes", filename, len(raw_bytes))

    fname_lower = filename.lower()

    # PDF detection
    if fname_lower.endswith(".pdf") or content_type == "application/pdf":
        return _parse_pdf(raw_bytes, filename)

    # Decode to text
    try:
        content = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        content = raw_bytes.decode("latin-1", errors="replace")

    # OFX / QFX
    if fname_lower.endswith((".ofx", ".qfx")) or _is_ofx(content):
        return _parse_ofx(content, filename)

    # CSV
    if fname_lower.endswith(".csv") or "," in content[:500]:
        if _is_broker_csv(content):
            return _parse_csv_broker(content, filename)
        return _parse_csv_bank(content, filename)

    # Unknown — attempt generic CSV
    logger.warning("parse_statement: unknown format for %s — attempting generic CSV", filename)
    result = _parse_csv_bank(content, filename)
    result.format = "unknown"
    result.confidence = max(0.1, result.confidence - 0.3)
    result.warnings.append(f"Unknown file format — parsed as generic CSV.")
    return result
