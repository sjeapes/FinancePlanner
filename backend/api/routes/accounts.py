"""
@file accounts.py
@brief FastAPI routes for account CRUD operations.

All accounts are read from and written to the base scenario YAML file.
Account types supported: savings, investment, pension, property,
income, person, mortgage, expense, life_event.

Endpoints:
  GET    /api/accounts                    — list all accounts from base scenario
  GET    /api/accounts/{type}/{id}        — get single account
  PUT    /api/accounts/{type}/{id}        — update account in scenario YAML
  POST   /api/accounts/{type}             — add account to scenario
  DELETE /api/accounts/{type}/{id}        — remove account from scenario
"""

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from backend.models.pydantic_models import (
    InvestmentAccountModel,
    PensionFundModel,
    PropertyAssetModel,
    SavingsAccountModel,
)
from backend.persistence.yaml_serialiser import (
    dump_yaml,
    load_scenario_from_file,
    load_yaml,
)

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_TYPES = {
    "savings",
    "investment",
    "pension",
    "property",
    "income",
    "person",
    "mortgage",
    "expense",
    "life_event",
}

# Mapping from type string to YAML key
_TYPE_TO_YAML_KEY = {
    "savings": "savings_accounts",
    "investment": "investment_accounts",
    "pension": "pension_funds",
    "property": "properties",
    "income": "income_sources",
    "person": "people",
    "mortgage": "mortgages",
    "expense": "expense_buckets",
    "life_event": "life_events",
}

# Only types that have Pydantic models — new raw types are NOT in this map
_TYPE_TO_MODEL = {
    "savings": SavingsAccountModel,
    "investment": InvestmentAccountModel,
    "pension": PensionFundModel,
    "property": PropertyAssetModel,
}

# Types that return raw dicts (no Pydantic model wrapping)
_RAW_TYPES = {"income", "person", "mortgage", "expense", "life_event"}


# ── Response models ───────────────────────────────────────────────────────────

class AccountListResponse(BaseModel):
    """
    @brief Response for GET /api/accounts listing all account types.
    @param savings List of savings account models.
    @param investment List of investment account models.
    @param pension List of pension fund models.
    @param property List of property asset models.
    @param income List of income source dicts.
    @param people List of person dicts.
    @param mortgages List of mortgage dicts.
    @param expenses List of expense bucket dicts.
    @param life_events List of life event dicts.
    """
    model_config = ConfigDict(from_attributes=True)

    savings: list[SavingsAccountModel] = []
    investment: list[InvestmentAccountModel] = []
    pension: list[PensionFundModel] = []
    property: list[PropertyAssetModel] = []
    income: list[dict] = []
    people: list[dict] = []
    mortgages: list[dict] = []
    expenses: list[dict] = []
    life_events: list[dict] = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_scenario_path(request: Request) -> str:
    """
    @brief Return the absolute path to the base scenario YAML.
    @param request FastAPI Request with app.state.project_root.
    @return Absolute path string.
    """
    root = getattr(request.app.state, "project_root", ".")
    return os.path.join(root, "data", "scenarios", "base.yaml")


def _validate_type(account_type: str) -> None:
    """
    @brief Raise HTTPException if the account type is not valid.
    @param account_type Type string to validate.
    """
    if account_type not in VALID_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid account type '{account_type}'. Must be one of: {', '.join(VALID_TYPES)}",
        )


def _load_base_raw(request: Request) -> dict:
    """
    @brief Load the raw YAML dict for the base scenario.
    @param request FastAPI Request.
    @return Raw YAML dict.
    """
    path = _base_scenario_path(request)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Base scenario not found")
    data = load_yaml(path)
    if not data:
        raise HTTPException(status_code=500, detail="Could not load base scenario")
    return data


def _save_base_raw(request: Request, data: dict) -> None:
    """
    @brief Save a raw YAML dict back to the base scenario file.
    @param request FastAPI Request.
    @param data Raw dict to write.
    """
    path = _base_scenario_path(request)
    ok = dump_yaml(data, path)
    if not ok:
        raise HTTPException(
            status_code=500,
            detail={"error": "Write error", "detail": "Could not save base scenario"},
        )


def _find_account_index(accounts_list: list, account_id: str) -> Optional[int]:
    """
    @brief Find the index of an account in a list by its id field.
    @param accounts_list List of account dicts from YAML.
    @param account_id The id value to search for.
    @return Index in the list, or None if not found.
    """
    for i, item in enumerate(accounts_list):
        if str(item.get("id", "")) == account_id:
            return i
    return None


# ── Route handlers ────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(request: Request) -> AccountListResponse:
    """
    @brief List all accounts from the base scenario, grouped by type.
    @param request FastAPI Request.
    @return AccountListResponse with all account types populated.
    """
    try:
        scenario = load_scenario_from_file(_base_scenario_path(request))
        if scenario is None:
            raise HTTPException(status_code=500, detail="Could not load base scenario")

        # Load raw YAML for the new raw types that don't have Pydantic models
        raw_data = _load_base_raw(request)

        return AccountListResponse(
            savings=[SavingsAccountModel.from_dataclass(a) for a in scenario.savings_accounts],
            investment=[InvestmentAccountModel.from_dataclass(a) for a in scenario.investment_accounts],
            pension=[PensionFundModel.from_dataclass(p) for p in scenario.pension_funds],
            property=[PropertyAssetModel.from_dataclass(p) for p in scenario.properties],
            income=raw_data.get("income_sources", []) or [],
            people=raw_data.get("people", []) or [],
            mortgages=raw_data.get("mortgages", []) or [],
            expenses=raw_data.get("expense_buckets", []) or [],
            life_events=raw_data.get("life_events", []) or [],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("list_accounts: error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Load error", "detail": str(exc)})


@router.get("/accounts/{account_type}/{account_id}")
def get_account(
    account_type: str,
    account_id: str,
    request: Request,
) -> Any:
    """
    @brief Get a single account by type and id.
    @param account_type One of the supported account type strings.
    @param account_id Account identifier string.
    @param request FastAPI Request.
    @return Pydantic model for modelled types, or raw dict for raw types.
    """
    _validate_type(account_type)
    try:
        if account_type in _RAW_TYPES:
            # Return raw dict from YAML
            data = _load_base_raw(request)
            yaml_key = _TYPE_TO_YAML_KEY[account_type]
            accounts_list = data.get(yaml_key, []) or []
            idx = _find_account_index(accounts_list, account_id)
            if idx is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Account '{account_id}' not found in {account_type}",
                )
            return accounts_list[idx]

        # Modelled types: use Pydantic model
        scenario = load_scenario_from_file(_base_scenario_path(request))
        if scenario is None:
            raise HTTPException(status_code=500, detail="Could not load base scenario")

        model_class = _TYPE_TO_MODEL[account_type]
        yaml_key = _TYPE_TO_YAML_KEY[account_type]
        account_list = getattr(scenario, yaml_key, [])

        account = next((a for a in account_list if a.id == account_id), None)
        if account is None:
            raise HTTPException(
                status_code=404,
                detail=f"Account '{account_id}' not found in {account_type}",
            )
        return model_class.from_dataclass(account)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "get_account: error for %s/%s: %s", account_type, account_id, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail={"error": "Load error", "detail": str(exc)})


@router.post("/accounts/{account_type}", status_code=201)
def add_account(
    account_type: str,
    request: Request,
    body: dict = Body(...),
) -> dict:
    """
    @brief Add a new account to the base scenario YAML.
    @param account_type One of the supported account type strings.
    @param body Dict of account fields (must include 'id').
    @param request FastAPI Request.
    @return The newly added account dict.
    """
    _validate_type(account_type)
    yaml_key = _TYPE_TO_YAML_KEY[account_type]

    if "id" not in body or not body["id"]:
        raise HTTPException(status_code=422, detail="Account must have an 'id' field")

    try:
        data = _load_base_raw(request)
        accounts_list = data.get(yaml_key, []) or []

        # Check for duplicate id
        if _find_account_index(accounts_list, str(body["id"])) is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Account '{body['id']}' already exists in {account_type}",
            )

        accounts_list.append(body)
        data[yaml_key] = accounts_list
        _save_base_raw(request, data)
        logger.info("add_account: added %s/%s", account_type, body["id"])
        return body
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "add_account: error for %s: %s", account_type, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail={"error": "Create error", "detail": str(exc)})


@router.put("/accounts/{account_type}/{account_id}")
def update_account(
    account_type: str,
    account_id: str,
    request: Request,
    body: dict = Body(...),
) -> dict:
    """
    @brief Update an existing account in the base scenario YAML.
    @param account_type One of the supported account type strings.
    @param account_id Account identifier string.
    @param body Updated account fields dict.
    @param request FastAPI Request.
    @return Updated account dict.
    """
    _validate_type(account_type)
    yaml_key = _TYPE_TO_YAML_KEY[account_type]

    try:
        data = _load_base_raw(request)
        accounts_list = data.get(yaml_key, []) or []

        idx = _find_account_index(accounts_list, account_id)
        if idx is None:
            raise HTTPException(
                status_code=404,
                detail=f"Account '{account_id}' not found in {account_type}",
            )

        # Preserve the id in case body omits it
        body["id"] = account_id
        accounts_list[idx] = body
        data[yaml_key] = accounts_list
        _save_base_raw(request, data)
        logger.info("update_account: updated %s/%s", account_type, account_id)
        return body
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "update_account: error for %s/%s: %s", account_type, account_id, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail={"error": "Update error", "detail": str(exc)})


@router.delete("/accounts/{account_type}/{account_id}", status_code=204)
def delete_account(
    account_type: str,
    account_id: str,
    request: Request,
) -> None:
    """
    @brief Remove an account from the base scenario YAML.
    @param account_type One of the supported account type strings.
    @param account_id Account identifier string.
    @param request FastAPI Request.
    """
    _validate_type(account_type)
    yaml_key = _TYPE_TO_YAML_KEY[account_type]

    try:
        data = _load_base_raw(request)
        accounts_list = data.get(yaml_key, []) or []

        idx = _find_account_index(accounts_list, account_id)
        if idx is None:
            raise HTTPException(
                status_code=404,
                detail=f"Account '{account_id}' not found in {account_type}",
            )

        del accounts_list[idx]
        data[yaml_key] = accounts_list
        _save_base_raw(request, data)
        logger.info("delete_account: removed %s/%s", account_type, account_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "delete_account: error for %s/%s: %s", account_type, account_id, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail={"error": "Delete error", "detail": str(exc)})
