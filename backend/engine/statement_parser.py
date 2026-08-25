"""
@file statement_parser.py
@brief Phase 10 financial statement parser for LifeLedger.

Parses uploaded bank and broker statements to extract current account
balances, holdings, and historical balance series for import into the
scenario YAML.

Supported formats
-----------------
OFX / QFX
    Open Financial Exchange format exported by most UK banks
    (Barclays, HSBC, NatWest, Lloyds, Santander).
    Extracts current balance, statement date, and reconstructs a
    historical balance series from STMTTRN entries.

CSV — bank statement
    Generic two-column (date + balance) or multi-column (date, amount,
    balance) format. Covers Monzo, Starling, Chase UK, and generic
    bank CSV exports.

CSV — broker / investment statement
    Holdings format with Description, Units, Price, Value columns.
    Covers Hargreaves Lansdown, Vanguard, AJ Bell, Interactive Brokers,
    Freetrade exports.

PDF
    Text extraction via pdfplumber (if installed). Falls back to a
    confidence=low result when pdfplumber is not available.

Output
------
ParsedStatement — current value, historical balance series, optional
holdings list, detected account type, institution guess, and
confidence score.

@author  LifeLedger
@version 0.1.0
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
    @param units     Number of units or shares held.
    @param price     Price per unit in native currency.
    @param value     Total value (units × price).
    @param currency  Currency code.
    """
    name: str
    isin: str
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
    @param account_name      Account name from statement or filename heuristic.
    @param suggested_type    Suggested LifeLedger account type:
                             'general', 'cash_ISA', 'ISA', 'SIPP',
                             'workplace_DC', 'savings', 'GIA'.
    @param currency          Currency code (default 'GBP').
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
# Institution keyword hints
# ─────────────────────────────────────────────────────────────────────────────

_INSTITUTION_HINTS: list[tuple[list[str], str]] = [
    (["barclays"],                      "Barclays"),
    (["hsbc"],                          "HSBC"),
    (["natwest", "nat west"],           "NatWest"),
    (["lloyds"],                        "Lloyds"),
    (["santander"],                     "Santander"),
    (["monzo"],                         "Monzo"),
    (["starling"],                      "Starling"),
    (["chase"],                         "Chase UK"),
    (["nationwide"],                    "Nationwide"),
    (["halifax"],                       "Halifax"),
    (["hargreaves", "hl.co.uk", "hl "],  "Hargreaves Lansdown"),
    (["vanguard"],                      "Vanguard"),
    (["aj bell", "ajbell"],             "AJ Bell"),
    (["interactive brokers", "ibkr"],   "Interactive Brokers"),
    (["freetrade"],                     "Freetrade"),
    (["fidelity"],                      "Fidelity"),
    (["nest"],                          "NEST Pension"),
    (["peoples pension", "people's pension"], "People's Pension"),
    (["standard life"],                 "Standard Life"),
    (["aviva"],                         "Aviva"),
    (["legal & general", "legal and general"], "Legal & General"),
]

_ACCOUNT_TYPE_HINTS: list[tuple[list[str], str]] = [
    (["isa", "stocks & shares isa", "stocks and shares"],  "ISA"),
    (["cash isa", "cash individual savings"],              "cash_ISA"),
    (["sipp", "self-invested personal pension"],           "SIPP"),
    (["workplace", "employer", "nest", "dc pension",
      "peoples pension", "people's pension"],              "workplace_DC"),
    (["savings", "easy access", "fixed rate"],             "savings"),
    (["gia", "general investment", "taxable"],             "GIA"),
    (["current", "checking", "everyday"],                  "general"),
]


def _guess_institution(text: str) -> str:
    lower = text.lower()
    for keywords, name in _INSTITUTION_HINTS:
        if any(k in lower for k in keywords):
            return name
    return ""


def _guess_account_type(text: str, institution: str) -> str:
    lower = (text + " " + institution).lower()
    for keywords, atype in _ACCOUNT_TYPE_HINTS:
        if any(k in lower for k in keywords):
            return atype
    return "general"


# ─────────────────────────────────────────────────────────────────────────────
# Date parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

_DATE_FORMATS = [
    "%Y%m%d%H%M%S",   # OFX compact
    "%Y%m%d",          # OFX short
    "%d/%m/%Y",        # UK CSV
    "%d-%m-%Y",
    "%Y-%m-%d",        # ISO
    "%m/%d/%Y",        # US CSV
    "%d %b %Y",        # "01 Jan 2024"
    "%d %B %Y",        # "01 January 2024"
]


def _parse_date(raw: str) -> Optional[date]:
    """
    @brief Try multiple date formats and return a date object or None.

    @param raw  Raw date string from the statement.
    @return     Parsed date or None if unparseable.
    """
    raw = raw.strip().split(".")[0]   # trim timezone component
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw[:len(fmt.replace("%Y","0000").replace("%m","00").replace("%d","00").replace("%H","00").replace("%M","00").replace("%S","00").replace("%b","Jan").replace("%B","January"))], fmt).date()
        except ValueError:
            pass
    # Brute-force
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _date_to_iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────────────────────
# OFX / QFX parser
# ─────────────────────────────────────────────────────────────────────────────


def _parse_ofx(content: str, filename: str) -> ParsedStatement:
    """
    @brief Parse OFX or QFX format bank statement.

    Handles both SGML-style (classic OFX) and XML-style (OFX 2.x / QFX).
    Extracts current balance, statement date, and reconstructs a monthly
    balance series from transaction entries.

    @param content   Full file text content.
    @param filename  Original filename for heuristics.
    @return          ParsedStatement.
    """

    def tag(name: str, text: str) -> Optional[str]:
        """Extract first occurrence of <TAG>value or TAG:value."""
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
    bal_str  = tag("BALAMT", content) or tag("LEDGERBAL", content)
    current  = 0.0
    if bal_str:
        try:
            current = float(bal_str)
        except ValueError:
            warnings.append(f"Could not parse balance: {bal_str!r}")

    # Statement date
    date_str = tag("DTASOF", content) or tag("DTEND", content) or tag("DTSTART", content)
    stmt_date = _date_to_iso(date.today())
    if date_str:
        d = _parse_date(date_str)
        if d:
            stmt_date = _date_to_iso(d)

    # Currency
    currency = (tag("CURDEF", content) or "GBP").strip().upper()[:3]

    # Account type hint
    acct_type_raw = tag("ACCTTYPE", content) or ""

    # Institution from FI/ORG
    institution_raw = tag("ORG", content) or tag("FID", content) or ""
    institution = _guess_institution(institution_raw + " " + filename + " " + content[:500])

    # Reconstruct historical balance from transactions
    # Each STMTTRN has DTPOSTED and TRNAMT; sum from 0 to get running balance
    trn_pattern = re.compile(
        r"<STMTTRN>.*?<DTPOSTED>\s*(\d+).*?<TRNAMT>\s*([+-]?\d+\.?\d*)",
        re.DOTALL | re.IGNORECASE,
    )
    transactions: list[tuple[date, float]] = []
    for m in trn_pattern.finditer(content):
        d_raw, amt_raw = m.group(1), m.group(2)
        d = _parse_date(d_raw)
        if d:
            try:
                transactions.append((d, float(amt_raw)))
            except ValueError:
                pass

    # Sort and build running balance backwards from current
    historical: list[HistoricalBalance] = []
    if transactions:
        transactions.sort(key=lambda x: x[0])
        running = current
        # Walk backwards from most recent to oldest
        for d, amt in reversed(transactions):
            running -= amt
            historical.append(HistoricalBalance(date_str=_date_to_iso(d), balance=round(running + amt, 2)))
        historical.reverse()
        # Deduplicate by keeping the last balance per month
        monthly: dict[str, float] = {}
        for h in historical:
            month_key = h.date_str[:7]
            monthly[month_key] = h.balance
        historical = [HistoricalBalance(date_str=k + "-01", balance=v)
                      for k, v in sorted(monthly.items())]

    acct_name = (
        tag("ACCTID", content)
        or _guess_institution(filename)
        or "Imported Account"
    )
    acct_name = acct_name[:60]

    suggested_type = _guess_account_type(
        content[:2000] + " " + filename + " " + acct_type_raw,
        institution,
    )

    logger.info(
        "OFX parse: institution=%s type=%s balance=%.2f date=%s txns=%d",
        institution, suggested_type, current, stmt_date, len(transactions),
    )

    return ParsedStatement(
        format="ofx",
        institution=institution,
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


def _parse_csv_bank(content: str, filename: str) -> ParsedStatement:
    """
    @brief Parse a generic bank CSV statement.

    Detects columns by header names and extracts date + balance pairs.
    Handles Monzo, Starling, Barclays, and generic bank exports.

    @param content   Full CSV text.
    @param filename  Original filename for heuristics.
    @return          ParsedStatement.
    """
    warnings: list[str] = []
    reader = csv.DictReader(io.StringIO(content))
    headers = [h.lower().strip() for h in (reader.fieldnames or [])]

    # Find date and balance columns
    date_col    = next((h for h in headers if h in {"date", "transaction date", "posted date", "transaction", "datetime"}), None)
    balance_col = next((h for h in headers if "balance" in h), None)
    amount_col  = next((h for h in headers if h in {"amount", "credit", "debit", "transaction amount", "value"}), None)

    if not date_col:
        warnings.append("Could not detect date column.")
    if not balance_col and not amount_col:
        warnings.append("Could not detect balance or amount column.")

    rows: list[tuple[date, float]] = []
    for row in reader:
        keys = {k.lower().strip(): v for k, v in row.items()}
        raw_date = keys.get(date_col or "", "")
        raw_bal  = keys.get(balance_col or "", "") if balance_col else ""
        raw_amt  = keys.get(amount_col or "", "") if amount_col else ""

        d = _parse_date(raw_date) if raw_date else None
        if not d:
            continue

        try:
            bal = float(re.sub(r"[£$€,\s]", "", raw_bal)) if raw_bal else None
        except ValueError:
            bal = None

        if bal is None and raw_amt:
            try:
                bal = float(re.sub(r"[£$€,\s]", "", raw_amt))
            except ValueError:
                bal = None

        if d and bal is not None:
            rows.append((d, bal))

    rows.sort(key=lambda x: x[0])
    current  = rows[-1][1] if rows else 0.0
    stmt_date = _date_to_iso(rows[-1][0]) if rows else _date_to_iso(date.today())

    # Monthly deduplicated historical series
    monthly: dict[str, float] = {}
    for d, bal in rows:
        monthly[_date_to_iso(d)[:7]] = bal
    historical = [HistoricalBalance(date_str=k + "-01", balance=v)
                  for k, v in sorted(monthly.items())]

    institution = _guess_institution(filename + " " + content[:400])
    suggested_type = _guess_account_type(filename + " " + content[:400], institution)

    logger.info(
        "CSV bank parse: institution=%s rows=%d balance=%.2f",
        institution, len(rows), current,
    )

    return ParsedStatement(
        format="csv_bank",
        institution=institution,
        account_name=institution or "Imported Bank Account",
        suggested_type=suggested_type,
        currency="GBP",
        current_balance=current,
        statement_date=stmt_date,
        historical=historical,
        holdings=[],
        confidence=0.80 if rows else 0.30,
        warnings=warnings,
        raw_text_preview=content[:500],
    )


# ─────────────────────────────────────────────────────────────────────────────
# CSV broker / investment statement parser
# ─────────────────────────────────────────────────────────────────────────────


def _parse_csv_broker(content: str, filename: str) -> ParsedStatement:
    """
    @brief Parse a broker or investment platform CSV statement.

    Detects holdings-format CSVs with Description, Units, Price, Value columns.
    Covers Hargreaves Lansdown, Vanguard, AJ Bell, Interactive Brokers exports.

    @param content   Full CSV text.
    @param filename  Original filename for heuristics.
    @return          ParsedStatement.
    """
    warnings: list[str] = []
    reader = csv.DictReader(io.StringIO(content))
    headers = [h.lower().strip() for h in (reader.fieldnames or [])]

    # Column detection
    name_col  = next((h for h in headers if h in {"security", "description", "stock", "fund", "name", "holding", "instrument"}), None)
    units_col = next((h for h in headers if h in {"units", "quantity", "shares", "holding units", "number of units"}), None)
    price_col = next((h for h in headers if h in {"price", "unit cost", "unit price", "price (p)", "price per unit"}), None)
    value_col = next((h for h in headers if "value" in h or "worth" in h or "market" in h), None)
    isin_col  = next((h for h in headers if "isin" in h), None)

    holdings: list[ParsedHolding] = []
    total_value = 0.0

    for row in reader:
        keys = {k.lower().strip(): v.strip() for k, v in row.items()}

        name  = keys.get(name_col or "", "").strip()
        if not name or name.lower() in {"total", "cash", "", "grand total"}:
            # Try to extract a "total" row for the portfolio value
            if "total" in name.lower() and value_col:
                raw_v = keys.get(value_col, "")
                try:
                    total_value = float(re.sub(r"[£$€,\s]", "", raw_v))
                except ValueError:
                    pass
            continue

        raw_units = keys.get(units_col or "", "0")
        raw_price = keys.get(price_col or "", "0")
        raw_value = keys.get(value_col or "", "0")
        isin      = keys.get(isin_col or "", "")

        try:
            units = float(re.sub(r"[,\s]", "", raw_units)) if raw_units else 0.0
        except ValueError:
            units = 0.0
        try:
            # Price may be in pence (p) — normalise
            raw_p = re.sub(r"[£$€,\sp]", "", raw_price)
            price = float(raw_p) if raw_p else 0.0
            if price_col and "p)" in (price_col or ""):
                price = price / 100.0   # pence → pounds
        except ValueError:
            price = 0.0
        try:
            value = float(re.sub(r"[£$€,\s]", "", raw_value)) if raw_value else units * price
        except ValueError:
            value = units * price

        if value > 0:
            holdings.append(ParsedHolding(
                name=name, isin=isin, units=units, price=price,
                value=round(value, 2), currency="GBP",
            ))
            total_value += value

    # If no explicit total was found, sum holdings
    if total_value == 0.0:
        total_value = sum(h.value for h in holdings)

    institution = _guess_institution(filename + " " + content[:400])
    suggested_type = _guess_account_type(filename + " " + content[:400], institution)
    if suggested_type == "general":
        suggested_type = "ISA"  # default for broker statements

    logger.info(
        "CSV broker parse: institution=%s holdings=%d total=%.2f",
        institution, len(holdings), total_value,
    )

    return ParsedStatement(
        format="csv_broker",
        institution=institution,
        account_name=institution or "Imported Investment Account",
        suggested_type=suggested_type,
        currency="GBP",
        current_balance=total_value,
        statement_date=_date_to_iso(date.today()),
        historical=[],
        holdings=holdings,
        confidence=0.85 if holdings else 0.35,
        warnings=warnings,
        raw_text_preview=content[:500],
    )


# ─────────────────────────────────────────────────────────────────────────────
# PDF parser
# ─────────────────────────────────────────────────────────────────────────────


def _parse_pdf(raw_bytes: bytes, filename: str) -> ParsedStatement:
    """
    @brief Extract text from a PDF and parse balance information.

    Uses pdfplumber if available. Falls back to a low-confidence stub
    result if pdfplumber is not installed.

    @param raw_bytes  Raw PDF bytes.
    @param filename   Original filename for heuristics.
    @return           ParsedStatement.
    """
    warnings: list[str] = []
    text = ""

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            for page in pdf.pages[:6]:   # first 6 pages usually sufficient
                text += (page.extract_text() or "") + "\n"
    except ImportError:
        warnings.append(
            "pdfplumber is not installed — PDF text extraction unavailable. "
            "Install with: pip install pdfplumber"
        )
        return ParsedStatement(
            format="pdf",
            institution=_guess_institution(filename),
            account_name=filename.replace(".pdf", ""),
            suggested_type="general",
            currency="GBP",
            current_balance=0.0,
            statement_date=_date_to_iso(date.today()),
            historical=[],
            holdings=[],
            confidence=0.0,
            warnings=warnings,
        )
    except Exception as exc:
        warnings.append(f"PDF read error: {exc}")
        return ParsedStatement(
            format="pdf",
            institution="",
            account_name=filename,
            suggested_type="general",
            currency="GBP",
            current_balance=0.0,
            statement_date=_date_to_iso(date.today()),
            historical=[],
            holdings=[],
            confidence=0.0,
            warnings=warnings,
        )

    institution = _guess_institution(filename + " " + text[:1000])
    suggested_type = _guess_account_type(filename + " " + text[:2000], institution)

    # Heuristic balance extraction: look for largest currency figure near keywords
    # "total value", "portfolio value", "closing balance", "account balance"
    balance_patterns = [
        r"(?:total value|portfolio value|closing balance|account balance|"
        r"market value|current value|balance)[^\d]{0,20}([\d,]+\.?\d*)",
    ]
    current = 0.0
    for p in balance_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            try:
                current = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass

    # Fallback: find the largest number that looks like a reasonable balance
    if current == 0.0:
        all_amounts = re.findall(r"(?:£|GBP)\s*([\d,]+\.?\d{0,2})", text)
        parsed_amounts = []
        for a in all_amounts:
            try:
                parsed_amounts.append(float(a.replace(",", "")))
            except ValueError:
                pass
        if parsed_amounts:
            current = max(parsed_amounts)

    logger.info("PDF parse: institution=%s type=%s balance=%.2f", institution, suggested_type, current)

    return ParsedStatement(
        format="pdf",
        institution=institution,
        account_name=institution or filename.replace(".pdf", ""),
        suggested_type=suggested_type,
        currency="GBP",
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
    return bool(re.search(r"OFXHEADER|<OFX>|<STMTRS>|<INVSTMTRS>", content[:2000], re.IGNORECASE))


def _is_broker_csv(content: str) -> bool:
    lower = content[:1000].lower()
    broker_signals = {"units", "quantity", "shares", "isin", "unit cost", "holding", "instrument"}
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

    Detects the file format automatically (OFX/QFX, CSV bank, CSV broker,
    PDF) and delegates to the appropriate parser.

    @param raw_bytes     Raw file bytes.
    @param filename      Original filename (used for format detection and
                         institution heuristics).
    @param content_type  MIME type hint (optional; filename extension takes
                         precedence).
    @return              ParsedStatement with current value, historical
                         series, and optional holdings.
    """
    logger.info("parse_statement: filename=%s size=%d bytes", filename, len(raw_bytes))

    fname_lower = filename.lower()

    # PDF detection
    if fname_lower.endswith(".pdf") or content_type == "application/pdf":
        return _parse_pdf(raw_bytes, filename)

    # Decode to text (try UTF-8, fall back to latin-1 which is OFX default)
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
        else:
            return _parse_csv_bank(content, filename)

    # Unknown — try bank CSV anyway
    logger.warning("parse_statement: unknown format for %s — attempting generic CSV", filename)
    result = _parse_csv_bank(content, filename)
    result.format = "unknown"
    result.confidence = max(0.1, result.confidence - 0.3)
    result.warnings.append(f"Unknown file format for '{filename}' — parsed as generic CSV.")
    return result
