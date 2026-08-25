"""
@file sankey.py
@brief FastAPI route for Sankey / cash-flow diagram data.

GET /api/sankey-data
    Reads the scenario YAML for the requested year and returns nodes and
    links suitable for rendering a two-column Sankey diagram showing:

    Left (sources)   → income sources (gross per source)
    Right (sinks)    → income tax, NI, pension contributions, ISA/GIA
                       contributions, mortgage payments, living expenses,
                       and the net savings remainder

    No full simulation run is needed — the endpoint computes tax using the
    existing tax_engine directly from the scenario config.

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from backend.persistence.yaml_serialiser import load_yaml
from backend.engine.tax_engine import calculate_net_income

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────────────────────────


class SankeyNode(BaseModel):
    """
    @brief One node in the Sankey diagram.

    @param id      Unique identifier.
    @param label   Display label.
    @param value   Flow value (same unit as links, e.g. annual GBP).
    @param colour  Hex colour for the node rectangle.
    @param column  0 = left (sources), 1 = right (sinks).
    @param group   Semantic group: 'income', 'tax', 'pension', 'isa',
                   'expense', 'mortgage', 'savings', 'gia'.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    value: float
    colour: str
    column: int
    group: str


class SankeyLink(BaseModel):
    """
    @brief One directed link (flow band) in the Sankey diagram.

    @param source  Source node id (left column).
    @param target  Target node id (right column).
    @param value   Flow value.
    @param colour  Hex colour for the link band (usually target node colour).
    @param label   Optional tooltip label.
    """
    model_config = ConfigDict(from_attributes=True)

    source: str
    target: str
    value: float
    colour: str
    label: str = ""


class SankeyData(BaseModel):
    """
    @brief Full Sankey diagram data for one year.

    @param year     Calendar year the data represents.
    @param currency Currency code.
    @param nodes    All nodes (sources + sinks).
    @param links    All directed links.
    @param total_gross  Total gross income (sum of source values).
    @param warnings Parser or calculation warnings.
    """
    model_config = ConfigDict(from_attributes=True)

    year: int
    currency: str
    nodes: list[SankeyNode]
    links: list[SankeyLink]
    total_gross: float
    warnings: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# Colour palette
# ─────────────────────────────────────────────────────────────────────────────

_SOURCE_COLOURS = [
    "#0e9aad",   # primary income — teal
    "#58a6ff",   # secondary — blue
    "#a5d6ff",   # tertiary — light blue
    "#79c0ff",   # quaternary
    "#388bfd",   # quinary
]

_SINK_COLOURS = {
    "tax":      "#e05252",   # income tax — red
    "ni":       "#f07070",   # NI — lighter red
    "pension":  "#a78bfa",   # pension — purple
    "isa":      "#d4a843",   # ISA — gold
    "gia":      "#8fa3b8",   # GIA — slate
    "mortgage": "#6b7280",   # mortgage — grey
    "expense":  "#f97316",   # living expenses — orange
    "savings":  "#2dbd7e",   # net savings — green
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _is_active(item: dict, year: int) -> bool:
    """
    @brief Return True if an income source or expense is active in the given year.

    @param item  Dict with optional 'start_date' and 'end_date' keys.
    @param year  Calendar year to test.
    @return      True if active.
    """
    start = item.get("start_date")
    end   = item.get("end_date")
    if start:
        try:
            if int(str(start)[:4]) > year:
                return False
        except (ValueError, TypeError):
            pass
    if end:
        try:
            if int(str(end)[:4]) < year:
                return False
        except (ValueError, TypeError):
            pass
    return True


def _account_label(account_id: str, scenario: dict) -> str:
    """
    @brief Look up the display name for an account by ID.

    @param account_id  Account identifier string.
    @param scenario    Raw scenario YAML dict.
    @return            Display name or the raw ID if not found.
    """
    for section in [
        "savings_accounts", "investment_accounts", "pension_funds",
    ]:
        for acc in scenario.get(section, []):
            if acc.get("id") == account_id:
                return acc.get("name", account_id)
    return account_id


def _classify_account(account_id: str, scenario: dict) -> str:
    """
    @brief Classify an account as 'pension', 'isa', or 'gia'.

    @param account_id  Account identifier string.
    @param scenario    Raw scenario YAML dict.
    @return            Group string: 'pension', 'isa', or 'gia'.
    """
    for acc in scenario.get("pension_funds", []):
        if acc.get("id") == account_id:
            return "pension"
    for acc in scenario.get("investment_accounts", []):
        if acc.get("id") == account_id:
            atype = acc.get("account_type", "").upper()
            return "isa" if "ISA" in atype else "gia"
    return "gia"


# ─────────────────────────────────────────────────────────────────────────────
# Core builder
# ─────────────────────────────────────────────────────────────────────────────


def _build_sankey(scenario: dict, year: int, tax_profiles: dict) -> SankeyData:
    """
    @brief Compute Sankey nodes and links from a scenario for one year.

    @param scenario     Raw scenario YAML dict.
    @param year         Calendar year to compute.
    @param tax_profiles Tax profile dicts (from app state).
    @return             SankeyData with nodes and links.
    """
    warnings: list[str] = []
    nodes:    list[SankeyNode] = []
    links:    list[SankeyLink] = []

    # ── Aggregate sinks ───────────────────────────────────────────────────────
    # We build sinks from source routing, then emit a single node per sink type
    # Keys: sink_id → {label, group, value, colour}
    sinks: dict[str, dict] = {}

    def accum_sink(sid: str, label: str, group: str, amount: float) -> None:
        if amount <= 0:
            return
        if sid not in sinks:
            sinks[sid] = {"label": label, "group": group,
                          "colour": _SINK_COLOURS.get(group, "#8fa3b8"), "value": 0.0}
        sinks[sid]["value"] += amount

    # ── Process income sources ────────────────────────────────────────────────
    raw_links: list[dict] = []   # {source, target, value, colour}
    total_gross = 0.0

    income_sources = scenario.get("income_sources", [])
    for idx, isrc in enumerate(income_sources):
        if not _is_active(isrc, year):
            continue

        gross = float(isrc.get("gross_annual", 0.0))
        if gross <= 0:
            continue

        # Apply real salary growth up to this year
        growth = float(isrc.get("annual_growth_rate", 0.0))
        start_year = int(str(isrc.get("start_date", f"{year}-01-01"))[:4])
        years_elapsed = max(0, year - start_year)
        gross = gross * ((1 + growth) ** years_elapsed)

        total_gross += gross

        # Tax calculation
        treatment = isrc.get("tax_treatment", "PAYE")
        profile_id = isrc.get("tax_profile_id") or "uk_standard"
        profile = tax_profiles.get(profile_id, {}) if isinstance(tax_profiles, dict) else {}

        try:
            tax_result = calculate_net_income(gross, treatment, profile)
            income_tax = tax_result.income_tax
            ni         = tax_result.national_insurance
        except Exception as exc:
            warnings.append(f"Tax calc failed for {isrc.get('id', '?')}: {exc}")
            income_tax = gross * 0.20
            ni         = gross * 0.08

        # Source node
        src_id = f"src_{isrc.get('id', idx)}"
        colour = _SOURCE_COLOURS[idx % len(_SOURCE_COLOURS)]
        nodes.append(SankeyNode(
            id=src_id, label=isrc.get("name", f"Income {idx+1}"),
            value=round(gross, 2), colour=colour, column=0, group="income",
        ))

        # Link: income → income tax
        accum_sink("income_tax", "Income Tax", "tax", income_tax)
        raw_links.append({"source": src_id, "target": "income_tax",
                          "value": income_tax, "colour": _SINK_COLOURS["tax"]})

        # Link: income → NI
        accum_sink("ni", "National Insurance", "ni", ni)
        raw_links.append({"source": src_id, "target": "ni",
                          "value": ni, "colour": _SINK_COLOURS["ni"]})

        # Contributions routing
        contributions = isrc.get("contributions", [])
        total_contrib = 0.0
        for contrib in contributions:
            dest_id     = contrib.get("destination_account_id", "unknown")
            rate        = float(contrib.get("rate", 0.0))
            cap         = float(contrib.get("cap_annual", 1e9))
            emp_match   = float(contrib.get("employer_top_up", 0.0))
            amount      = min(gross * rate, cap)
            match_amt   = min(gross * emp_match, cap)
            total_amount = amount + match_amt
            if total_amount <= 0:
                continue

            group     = _classify_account(dest_id, scenario)
            dest_name = _account_label(dest_id, scenario)
            sink_key  = f"contrib_{dest_id}"
            accum_sink(sink_key, dest_name, group, total_amount)
            raw_links.append({"source": src_id, "target": sink_key,
                               "value": total_amount, "colour": _SINK_COLOURS.get(group, "#8fa3b8"),
                               "label": dest_name})
            total_contrib += total_amount

        # Remainder from this source → allocated to expenses and savings
        # We do this allocation after processing all sources
        remainder = gross - income_tax - ni - total_contrib
        if remainder > 0:
            raw_links.append({"source": src_id, "target": "__remainder__",
                               "value": remainder, "colour": "#00000000",
                               "label": "remainder"})

    # ── Expense buckets ────────────────────────────────────────────────────────
    total_expenses = 0.0
    inflation_base = 0.025
    ref_year = int(str(year))

    for bucket in scenario.get("expense_buckets", []):
        if not _is_active(bucket, ref_year):
            continue
        amount = float(bucket.get("annual_amount", 0.0))
        if bucket.get("inflation_linked", False):
            start = int(str(bucket.get("start_date", f"{ref_year}-01-01"))[:4])
            amount = amount * ((1 + inflation_base) ** max(0, ref_year - start))
        total_expenses += amount

    # ── Mortgage annual payment ────────────────────────────────────────────────
    total_mortgage = 0.0
    for mort in scenario.get("mortgages", []):
        if not _is_active(mort, ref_year):
            continue
        balance = float(mort.get("current_balance", 0.0))
        # Approximate annual payment from latest rate period
        rate = 0.045   # default fallback
        for rp in reversed(mort.get("rate_periods", [])):
            try:
                rate = float(rp.get("rate", 0.045))
                break
            except (ValueError, TypeError):
                pass
        term_remaining = max(1, int(mort.get("term_years", 25)))
        if balance > 0 and rate > 0:
            # Standard annuity formula (monthly rate, monthly payments)
            r_m = rate / 12
            n_m = term_remaining * 12
            try:
                monthly = balance * (r_m * (1 + r_m) ** n_m) / ((1 + r_m) ** n_m - 1)
                total_mortgage += monthly * 12
            except ZeroDivisionError:
                total_mortgage += balance / term_remaining

    # ── Resolve remainder links → expenses and savings ────────────────────────
    total_remainder = sum(l["value"] for l in raw_links if l["target"] == "__remainder__")
    expenses_share  = min(total_expenses, total_remainder)
    mortgage_share  = min(total_mortgage, max(0, total_remainder - expenses_share))
    savings_share   = max(0, total_remainder - expenses_share - mortgage_share)

    # Distribute remainder proportionally across sources
    remainder_links = [l for l in raw_links if l["target"] == "__remainder__"]
    total_rem_val   = sum(l["value"] for l in remainder_links) or 1
    for l in remainder_links:
        share = l["value"] / total_rem_val
        src = l["source"]
        if expenses_share > 0:
            e_share = expenses_share * share
            accum_sink("expenses", "Living Expenses", "expense", e_share)
            raw_links.append({"source": src, "target": "expenses",
                               "value": e_share, "colour": _SINK_COLOURS["expense"]})
        if mortgage_share > 0:
            m_share = mortgage_share * share
            accum_sink("mortgage", "Mortgage", "mortgage", m_share)
            raw_links.append({"source": src, "target": "mortgage",
                               "value": m_share, "colour": _SINK_COLOURS["mortgage"]})
        if savings_share > 0:
            s_share = savings_share * share
            accum_sink("savings", "Net Savings", "savings", s_share)
            raw_links.append({"source": src, "target": "savings",
                               "value": s_share, "colour": _SINK_COLOURS["savings"]})

    # ── Remove placeholder links ──────────────────────────────────────────────
    final_links = [l for l in raw_links if l["target"] != "__remainder__" and l["value"] > 0]

    # ── Build sink nodes ──────────────────────────────────────────────────────
    for sid, s in sinks.items():
        if s["value"] > 0:
            nodes.append(SankeyNode(
                id=sid, label=s["label"], value=round(s["value"], 2),
                colour=s["colour"], column=1, group=s["group"],
            ))

    # ── Build link list ───────────────────────────────────────────────────────
    for l in final_links:
        links.append(SankeyLink(
            source=l["source"], target=l["target"],
            value=round(l["value"], 2), colour=l["colour"],
            label=l.get("label", ""),
        ))

    return SankeyData(
        year=year,
        currency="GBP",
        nodes=nodes,
        links=links,
        total_gross=round(total_gross, 2),
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/sankey-data", response_model=SankeyData)
def get_sankey_data(
    request: Request,
    scenario_path: str = Query(default="data/scenarios/base.yaml"),
    year: int = Query(default=0),
) -> SankeyData:
    """
    @brief Return Sankey diagram nodes and links for one calendar year.

    Reads the scenario YAML and computes income flows without running a
    full projection. Tax is computed via the tax engine. Contributions,
    expenses, and mortgage payments come from scenario config.

    @param scenario_path  Path to the scenario YAML (relative to project root).
    @param year           Calendar year. Defaults to current year.
    @param request        FastAPI Request.
    @return               SankeyData with nodes and links.
    """
    if year == 0:
        year = date.today().year

    root = getattr(request.app.state, "project_root", ".")
    abs_path = scenario_path if os.path.isabs(scenario_path) \
               else os.path.join(root, scenario_path)

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_path}")

    try:
        raw = load_yaml(abs_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load scenario: {exc}")

    scenario = raw.get("scenario", raw)
    tax_profiles = getattr(request.app.state, "tax_profiles", {})

    try:
        return _build_sankey(scenario, year, tax_profiles)
    except Exception as exc:
        logger.error("get_sankey_data: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)})
