"""
@file import_data.py
@brief FastAPI routes for Phase 10 statement import into LifeLedger.

Endpoints
---------
POST /api/import/parse
    Upload a bank or broker statement file (CSV, OFX, QFX, PDF).
    Returns a ParsedStatementOut JSON object with detected account info,
    current balance, historical balance series, and optional holdings.

POST /api/import/apply
    Apply a previously-parsed statement to the scenario YAML.
    Creates a new account or updates the current_value of an existing one.
    If historical balances are present, stores them in the account's
    historical_values list (if the YAML key exists) or appends notes.

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict

from backend.engine.statement_parser import ParsedStatement, ParsedHolding, parse_statement
from backend.persistence.yaml_serialiser import load_yaml, dump_yaml

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 10 MB


# ─────────────────────────────────────────────────────────────────────────────
# Response / request models
# ─────────────────────────────────────────────────────────────────────────────


class HistoricalBalanceOut(BaseModel):
    """@brief One date-balance point from a parsed statement."""
    date_str: str
    balance: float


class ParsedHoldingOut(BaseModel):
    """@brief One investment holding from a broker statement."""
    name: str
    isin: str
    units: float
    price: float
    value: float
    currency: str


class ParsedStatementOut(BaseModel):
    """
    @brief Full result of parsing a financial statement file.

    @param format            Detected format: 'ofx', 'csv_bank', 'csv_broker', 'pdf', 'unknown'.
    @param institution       Guessed institution name.
    @param account_name      Detected or suggested account name.
    @param suggested_type    Suggested LifeLedger account type.
    @param currency          Currency code.
    @param current_balance   Closing / most recent balance.
    @param statement_date    ISO date of the closing balance.
    @param historical        Ascending sorted monthly balance series.
    @param holdings          Investment holdings (broker statements only).
    @param confidence        Parser confidence 0.0–1.0.
    @param warnings          Parser warning messages.
    """
    model_config = ConfigDict(from_attributes=True)

    format: str
    institution: str
    account_name: str
    suggested_type: str
    currency: str
    current_balance: float
    statement_date: str
    historical: list[HistoricalBalanceOut]
    holdings: list[ParsedHoldingOut]
    confidence: float
    warnings: list[str]


class ApplyStatementRequest(BaseModel):
    """
    @brief Request body for POST /api/import/apply.

    @param parsed           The parsed statement data (returned from /parse).
    @param action           'create' = add new account; 'update' = update existing.
    @param account_type     LifeLedger account type (for 'create' action).
    @param account_id       Existing account ID (for 'update' action).
                            Also used as the new account ID for 'create'.
    @param account_name     Display name for the account.
    @param owner_id         Person ID that owns this account.
    @param import_holdings  Whether to add holdings to the account (broker only).
    @param import_history   Whether to store historical balances in the account.
    @param scenario_path    Path to the scenario YAML. Defaults to base.yaml.
    """
    parsed: ParsedStatementOut
    action: str                         # 'create' | 'update'
    account_type: str = "savings"
    account_id: str = ""
    account_name: str = ""
    owner_id: str = ""
    import_holdings: bool = True
    import_history: bool = True
    scenario_path: Optional[str] = None


class ApplyStatementResponse(BaseModel):
    """@brief Result of applying a statement to the scenario."""
    success: bool
    action: str
    account_id: str
    account_name: str
    message: str
    warnings: list[str] = []


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _base_path(request: Request, override: Optional[str] = None) -> str:
    """
    @brief Return path to the active scenario YAML.

    @param request   FastAPI request for project_root access.
    @param override  Optional explicit path.
    @return          Absolute filesystem path.
    """
    if override:
        return override
    root = getattr(request.app.state, "project_root", ".")
    return os.path.join(root, "data", "scenarios", "base.yaml")


_TYPE_TO_YAML_KEY = {
    # UK account types
    "savings":              "savings_accounts",
    "cash_ISA":             "savings_accounts",
    "ISA":                  "investment_accounts",
    "SIPP":                 "pension_funds",
    "workplace_DC":         "pension_funds",
    "GIA":                  "investment_accounts",
    "general":              "savings_accounts",
    # US account types
    "k401":                 "pension_funds",
    "roth_401k":            "pension_funds",
    "k403b":                "pension_funds",
    "roth_ira":             "investment_accounts",
    "ira":                  "pension_funds",
    "hsa":                  "savings_accounts",
    "plan_529":             "savings_accounts",
    "money_market":         "savings_accounts",
    "taxable_brokerage":    "investment_accounts",
}

_PENSION_TYPES    = {"SIPP", "workplace_DC", "k401", "roth_401k", "k403b", "ira"}
_INVESTMENT_TYPES = {"ISA", "GIA", "roth_ira", "taxable_brokerage"}


def _build_new_account(req: ApplyStatementRequest) -> dict:
    """
    @brief Build a new YAML account dict from the apply request.

    @param req  ApplyStatementRequest with parsed data and user choices.
    @return     Dict ready to append to the appropriate YAML list.
    """
    parsed  = req.parsed
    acct_id = req.account_id or ("acct_" + uuid.uuid4().hex[:8])
    name    = req.account_name or parsed.account_name
    atype   = req.account_type

    history_list = [
        {"date": h.date_str, "value": h.balance}
        for h in parsed.historical
    ] if req.import_history and parsed.historical else []

    # ── Pension account ───────────────────────────────────────────────────────
    if atype in _PENSION_TYPES:
        acc: dict[str, Any] = {
            "id": acct_id,
            "name": name,
            "pension_type": atype,
            "owner_id": req.owner_id or "person1",
            "current_value": round(parsed.current_balance, 2),
            "assumed_growth_rate": 0.07,
            "currency": parsed.currency,
            "drawdown_config": {
                "mode": "pct_swr",
                "rate": 0.04,
                "start_date": None,
                "tax_free_lump_sum_pct": 0.25,
                "lump_sum_taken": False,
            },
            "annuity_config": None,
        }
        if history_list:
            acc["historical_values"] = history_list
        if parsed.institution:
            acc["institution"] = parsed.institution
        return acc

    # ── Investment account (ISA, GIA) ─────────────────────────────────────────
    if atype in _INVESTMENT_TYPES:
        holdings_list = []
        if req.import_holdings and parsed.holdings:
            for h in parsed.holdings:
                holdings_list.append({
                    "id":    "holding_" + uuid.uuid4().hex[:6],
                    "name":  h.name,
                    "instrument_type": "ETF",
                    "assumed_growth_rate": 0.07,
                    "currency": h.currency,
                    "tracking_mode": "units",
                    "units": round(h.units, 6),
                    "price_per_unit": round(h.price, 4),
                    "isin": h.isin,
                })
        acc = {
            "id": acct_id,
            "name": name,
            "account_type": atype,
            "owner_id": req.owner_id or "person1",
            "current_value": round(parsed.current_balance, 2),
            "assumed_growth_rate": 0.07,
            "currency": parsed.currency,
            "holdings": holdings_list,
        }
        if history_list:
            acc["historical_values"] = history_list
        if parsed.institution:
            acc["institution"] = parsed.institution
        return acc

    # ── Savings / general account ─────────────────────────────────────────────
    acc = {
        "id": acct_id,
        "name": name,
        "account_type": atype,
        "owner_id": req.owner_id or "person1",
        "current_value": round(parsed.current_balance, 2),
        "annual_contribution": 0.0,
        "currency": parsed.currency,
        "interest_rate_periods": [
            {
                "start_date": parsed.statement_date[:7] + "-01",
                "end_date": None,
                "rate": 0.035,
            }
        ],
    }
    if history_list:
        acc["historical_values"] = history_list
    if parsed.institution:
        acc["institution"] = parsed.institution
    return acc


def _parsed_to_model(ps: ParsedStatement) -> ParsedStatementOut:
    """@brief Convert engine ParsedStatement to Pydantic output model."""
    return ParsedStatementOut(
        format=ps.format,
        institution=ps.institution,
        account_name=ps.account_name,
        suggested_type=ps.suggested_type,
        currency=ps.currency,
        current_balance=ps.current_balance,
        statement_date=ps.statement_date,
        historical=[HistoricalBalanceOut(date_str=h.date_str, balance=h.balance) for h in ps.historical],
        holdings=[ParsedHoldingOut(name=h.name, isin=h.isin, units=h.units, price=h.price, value=h.value, currency=h.currency) for h in ps.holdings],
        confidence=ps.confidence,
        warnings=ps.warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/import/parse", response_model=ParsedStatementOut)
async def parse_statement_upload(
    request: Request,
    file: UploadFile = File(...),
) -> ParsedStatementOut:
    """
    @brief Upload a bank or broker statement and return parsed account data.

    Accepts CSV, OFX, QFX, and PDF files up to 10 MB. Automatically
    detects format, extracts current balance, historical balance series,
    and investment holdings where available.

    @param file  Multipart file upload.
    @return      ParsedStatementOut with detected account info.
    """
    filename = file.filename or "uploaded_file"
    logger.info("parse_statement_upload: %s (%s)", filename, file.content_type)

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)")
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    try:
        result = parse_statement(raw, filename, file.content_type or "")
    except Exception as exc:
        logger.error("parse_statement_upload error: %s", exc, exc_info=True)
        raise HTTPException(status_code=422, detail={"error": str(exc)})

    return _parsed_to_model(result)


@router.post("/import/apply", response_model=ApplyStatementResponse)
async def apply_statement(
    request: Request,
    body: ApplyStatementRequest,
) -> ApplyStatementResponse:
    """
    @brief Apply parsed statement data to the scenario YAML.

    Creates a new account ('create') or updates an existing account's
    current_value ('update'). For create, also stores historical values
    and holdings when present and enabled.

    @param body  ApplyStatementRequest with parsed data and user choices.
    @return      ApplyStatementResponse with success status and summary.
    """
    warnings: list[str] = []
    scenario_path = _base_path(request, body.scenario_path)

    if not os.path.exists(scenario_path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_path}")

    try:
        raw_yaml = load_yaml(scenario_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load scenario: {exc}")

    scenario_data = raw_yaml.get("scenario", raw_yaml)

    # ── UPDATE existing account ───────────────────────────────────────────────
    if body.action == "update":
        if not body.account_id:
            raise HTTPException(status_code=422, detail="account_id required for update action")

        updated = False
        yaml_key = _TYPE_TO_YAML_KEY.get(body.account_type, "savings_accounts")
        for key in [yaml_key] + list(_TYPE_TO_YAML_KEY.values()):
            items = scenario_data.get(key, [])
            for item in items:
                if item.get("id") == body.account_id:
                    item["current_value"] = round(body.parsed.current_balance, 2)
                    if body.import_history and body.parsed.historical:
                        item["historical_values"] = [
                            {"date": h.date_str, "value": h.balance}
                            for h in body.parsed.historical
                        ]
                    if body.import_holdings and body.parsed.holdings and "holdings" in item:
                        # Merge / replace holdings
                        item["holdings"] = [
                            {
                                "id": "holding_" + uuid.uuid4().hex[:6],
                                "name": h.name, "isin": h.isin,
                                "units": round(h.units, 6),
                                "price_per_unit": round(h.price, 4),
                                "instrument_type": "ETF",
                                "assumed_growth_rate": 0.07,
                                "currency": h.currency,
                                "tracking_mode": "units",
                            }
                            for h in body.parsed.holdings
                        ]
                    updated = True
                    break
            if updated:
                break

        if not updated:
            warnings.append(f"Account '{body.account_id}' not found — creating instead.")
            body.action = "create"

    # ── CREATE new account ────────────────────────────────────────────────────
    if body.action == "create":
        new_account = _build_new_account(body)
        acct_id   = new_account["id"]
        yaml_key  = _TYPE_TO_YAML_KEY.get(body.account_type, "savings_accounts")
        if yaml_key not in scenario_data:
            scenario_data[yaml_key] = []
        scenario_data[yaml_key].append(new_account)

        logger.info("apply_statement CREATE: type=%s id=%s value=%.2f",
                    body.account_type, acct_id, body.parsed.current_balance)
    else:
        acct_id = body.account_id

    # Save YAML
    try:
        if "scenario" in raw_yaml:
            raw_yaml["scenario"] = scenario_data
            dump_yaml(raw_yaml, scenario_path)
        else:
            dump_yaml(scenario_data, scenario_path)
    except Exception as exc:
        logger.error("apply_statement YAML write error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save scenario: {exc}")

    n_history = len(body.parsed.historical)
    n_holdings = len(body.parsed.holdings)
    parts = [f"Balance £{body.parsed.current_balance:,.2f}"]
    if n_history:
        parts.append(f"{n_history} historical data points")
    if n_holdings:
        parts.append(f"{n_holdings} holdings")

    return ApplyStatementResponse(
        success=True,
        action=body.action,
        account_id=acct_id,
        account_name=body.account_name or body.parsed.account_name,
        message=f"{'Created' if body.action == 'create' else 'Updated'}: {', '.join(parts)}",
        warnings=warnings,
    )
