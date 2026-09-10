"""
@file fire.py
@brief FastAPI routes powering the FIRE (Financial Independence, Retire Early) tab.

The projection engine already computes everything the FIRE tab needs
per year (`fire_coverage`, `fire_achieved`, and `TimelineResult.fire_year`),
and `FIRETarget.implied_target()` already derives a target net worth from
annual expenses and a safe withdrawal rate — none of that is duplicated
here. This module's job is purely to package those existing numbers into
one guided response, and to let the user edit the FIRE target.

Endpoints
---------
GET /api/fire/status?scenario_path=...
    Current net worth, the FIRE number (implied + explicit), progress,
    and the year FIRE is projected to be reached — plus a suggested
    annual-expenses figure derived from the user's own post-retirement
    expense buckets, to help them set a realistic number rather than
    guessing.

PUT /api/fire/target
    Update annual_expenses_target / swr / fire_type / target_net_worth
    on a scenario's fire_target block.

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.engine.calculator import ProjectionEngine, compute_current_net_worth
from backend.engine.scenario_engine import load_scenario_for_projection
from backend.persistence.yaml_serialiser import dump_yaml, load_yaml

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Response / request models
# ─────────────────────────────────────────────────────────────────────────────


class FireStatusResponse(BaseModel):
    """
    @brief Full guided FIRE status for a scenario.
    @param has_fire_target       Whether a fire_target block exists in the scenario YAML.
    @param fire_type             lean_fire | fire | fat_fire | coast_fire.
    @param annual_expenses_target The expenses figure the FIRE number is derived from.
    @param swr                   Safe withdrawal rate used (e.g. 0.04 = 4%).
    @param explicit_target_net_worth The literal target_net_worth stored in YAML (fallback only).
    @param fire_number           The number actually used: expenses / swr (or the explicit
                                  target if expenses/swr aren't set meaningfully).
    @param current_net_worth     Today's real net worth, EXCLUDING the primary residence —
                                  a home you live in isn't a source of retirement spending
                                  unless sold or downsized, so it's excluded from FIRE progress.
                                  General net worth displays elsewhere in the app correctly
                                  still include it; this figure deliberately does not.
    @param primary_residence_excluded The primary residence value backed out of
                                  current_net_worth, so the UI can show what was excluded
                                  and why the figure differs from the Dashboard's net worth.
    @param progress_pct          current_net_worth / fire_number * 100, capped at 999.
    @param fire_year             Calendar year FIRE is first achieved in this scenario, if any.
    @param years_to_fire         fire_year - current year, if fire_year is set.
    @param current_fire_coverage Today's real net worth divided by the FIRE number.
    @param retirement_year       The primary person's planned retirement year, if known.
    @param suggested_annual_expenses A data-driven suggestion for annual_expenses_target,
                                      taken from the scenario's own projected expenses in
                                      the retirement year — use this to sanity-check the
                                      number rather than guessing it from scratch.
    @param warnings              Any data-quality notes (e.g. no people/expenses configured).
    """
    model_config = ConfigDict(from_attributes=True)

    has_fire_target: bool
    fire_type: str
    annual_expenses_target: float
    swr: float
    explicit_target_net_worth: float
    fire_number: float
    current_net_worth: float
    primary_residence_excluded: float
    progress_pct: float
    fire_year: Optional[int]
    years_to_fire: Optional[int]
    current_fire_coverage: float
    retirement_year: Optional[int]
    suggested_annual_expenses: Optional[float]
    warnings: list[str] = []


class UpdateFireTargetRequest(BaseModel):
    """
    @brief Request body for PUT /api/fire/target.
    @param scenario_path Path to the scenario YAML, relative to project root.
    @param annual_expenses_target Target annual expenses in retirement.
    @param swr Safe withdrawal rate (e.g. 0.04 for the standard 4% rule).
    @param fire_type lean_fire | fire | fat_fire | coast_fire.
    @param target_net_worth Optional explicit override; if omitted, the engine always
                             prefers annual_expenses_target / swr.
    """
    model_config = ConfigDict(from_attributes=True)

    scenario_path: str
    annual_expenses_target: float = Field(gt=0)
    swr: float = Field(gt=0, le=0.20)
    fire_type: str = "fire"
    target_net_worth: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_VALID_FIRE_TYPES = {"lean_fire", "fire", "fat_fire", "coast_fire"}


def _resolve_path(request: Request, scenario_path: str) -> str:
    """@brief Resolve a scenario path to an absolute path using the app project root."""
    if os.path.isabs(scenario_path):
        return scenario_path
    project_root = getattr(request.app.state, "project_root", ".")
    return os.path.join(project_root, scenario_path)


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/fire/status", response_model=FireStatusResponse)
def fire_status(scenario_path: str, request: Request) -> FireStatusResponse:
    """
    @brief Return a guided FIRE status for a scenario: current progress, the FIRE
           number, and the projected FIRE year — plus a data-driven suggestion for
           the target expenses figure, based on the user's own configured
           post-retirement spending rather than a guess.

    @param scenario_path Path to the scenario YAML, relative to project root.
    @param request       FastAPI request.
    @return              FireStatusResponse.
    """
    abs_path = _resolve_path(request, scenario_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario file not found: {scenario_path}")

    warnings: list[str] = []
    try:
        project_root = getattr(request.app.state, "project_root", ".")
        scenario = load_scenario_for_projection(abs_path, project_root)
        if scenario is None:
            raise HTTPException(status_code=422, detail=f"Failed to parse scenario YAML: {scenario_path}")

        config = request.app.state.config
        tax_profiles = request.app.state.tax_profiles
        engine = ProjectionEngine(config, tax_profiles)
        result = engine.project(scenario)

        if not result.years:
            raise HTTPException(status_code=422, detail="Projection produced no years — check scenario data")

        current = result.years[0]
        ft = scenario.fire_target

        # Today's real net worth — raw balances, no simulated growth. Do NOT
        # use `current.total_net_worth` here: that's the year==start engine
        # snapshot, which already has a full year of growth/income/
        # contributions applied on top of the as-entered balances.
        # For FIRE progress specifically, exclude the primary residence: a
        # home you live in isn't a source of retirement spending unless
        # sold or downsized, so counting it inflates progress toward a
        # number meant to represent sustainable withdrawal capacity.
        # General net worth displays (Dashboard, Portfolio Mix) correctly
        # still include it via total_net_worth — only this FIRE-specific
        # figure excludes it.
        current_nw_result = compute_current_net_worth(scenario)
        current_nw = current_nw_result.total_net_worth_investable

        has_fire_target = ft is not None
        fire_type = ft.fire_type if ft else "fire"
        swr = ft.swr if ft and ft.swr > 0 else 0.04
        annual_expenses_target = ft.annual_expenses_target if ft else 0.0
        explicit_target = ft.target_net_worth if ft else 0.0

        retirement_year = None
        if scenario.people:
            try:
                retirement_year = scenario.people[0].retirement_year()
            except Exception as exc:
                logger.warning("fire_status: could not compute retirement_year: %s", exc)
        else:
            warnings.append("No people configured on this scenario — retirement year unknown.")

        # Prefer expenses/swr when meaningfully set; otherwise fall back to the
        # explicit target_net_worth (mirrors FIRETarget.implied_target's own logic).
        if ft and annual_expenses_target > 0:
            standard_fire_number = annual_expenses_target / swr
        elif explicit_target > 0:
            standard_fire_number = explicit_target
        else:
            standard_fire_number = 0.0
            warnings.append("No FIRE target set yet — enter your target annual expenses to get a number.")

        if fire_type == "coast_fire":
            # Coast FIRE is NOT expenses/swr — it's a fundamentally different
            # question: "how much do I need invested TODAY that, with zero
            # further contributions, will grow on its own to the standard
            # FIRE number by my retirement age?" That's the standard number
            # discounted back from retirement_year to today at an assumed
            # growth rate. Treating it as expenses/swr (as every other type
            # does) would make coast_fire produce the exact same number as
            # 'fire' whenever expenses/swr match — which defeats the point
            # of having it as a distinct type at all.
            growth_rate = float(config.raw.get("engine", {}).get("default_growth_rate", 0.07)) if config.raw else 0.07
            years_to_retirement = (retirement_year - current.year) if retirement_year is not None else None
            if standard_fire_number > 0 and years_to_retirement is not None and years_to_retirement > 0:
                fire_number = standard_fire_number / ((1.0 + growth_rate) ** years_to_retirement)
            else:
                fire_number = standard_fire_number
                warnings.append(
                    "Coast FIRE needs a known retirement year to discount back from — "
                    "showing the standard FIRE number instead."
                )
        else:
            fire_number = standard_fire_number

        progress_pct = min(999.0, (current_nw / fire_number * 100.0)) if fire_number > 0 else 0.0

        if current_nw_result.primary_residence_value > 0:
            warnings.append(
                f"Excludes your primary residence (£{current_nw_result.primary_residence_value:,.0f}) — "
                "a home you live in isn't a source of retirement spending unless sold or downsized."
            )

        years_to_fire = None
        if result.fire_year is not None:
            years_to_fire = result.fire_year - current.year

        suggested_annual_expenses = None
        if retirement_year is not None:
            post_retirement_years = [y for y in result.years if y.year >= retirement_year]
            if post_retirement_years:
                suggested_annual_expenses = post_retirement_years[0].total_expenses
            else:
                warnings.append("Projection doesn't reach the retirement year — can't suggest an expenses figure.")
        if not scenario.expense_buckets:
            warnings.append("No expense buckets configured — the suggested figure may be unreliable.")

        return FireStatusResponse(
            has_fire_target=has_fire_target,
            fire_type=fire_type,
            annual_expenses_target=annual_expenses_target,
            swr=swr,
            explicit_target_net_worth=explicit_target,
            fire_number=fire_number,
            current_net_worth=current_nw,
            primary_residence_excluded=current_nw_result.primary_residence_value,
            progress_pct=progress_pct,
            fire_year=result.fire_year,
            years_to_fire=years_to_fire,
            current_fire_coverage=(current_nw / fire_number) if fire_number > 0 else 0.0,
            retirement_year=retirement_year,
            suggested_annual_expenses=suggested_annual_expenses,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("fire_status: engine error for %s: %s", abs_path, exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Engine error", "detail": str(exc)})


@router.put("/fire/target")
def update_fire_target(body: UpdateFireTargetRequest, request: Request) -> dict:
    """
    @brief Create or update the fire_target block on a scenario YAML.

    @param body    UpdateFireTargetRequest.
    @param request FastAPI request.
    @return        {"success": True, "fire_target": {...}}
    """
    abs_path = _resolve_path(request, body.scenario_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"Scenario file not found: {body.scenario_path}")
    if body.fire_type not in _VALID_FIRE_TYPES:
        raise HTTPException(status_code=422, detail=f"fire_type must be one of {sorted(_VALID_FIRE_TYPES)}")

    try:
        raw = load_yaml(abs_path)

        fire_target = {
            "target_net_worth": body.target_net_worth if body.target_net_worth is not None
                                 else round(body.annual_expenses_target / body.swr, 2),
            "annual_expenses_target": body.annual_expenses_target,
            "swr": body.swr,
            "fire_type": body.fire_type,
        }
        # fire_target always lives at the TOP level of the scenario file —
        # parse_scenario() reads it via d.get("fire_target"), not from inside
        # any nested 'scenario:' metadata block. Writing it into raw.get(
        # "scenario", raw) (mirroring the pattern used for id/name/is_base)
        # would bury it inside that metadata block on files that have one,
        # so the write silently never lands where the reader looks — always
        # set it directly on the raw dict itself, regardless of whether a
        # nested 'scenario:' block exists alongside it.
        raw["fire_target"] = fire_target
        if not dump_yaml(raw, abs_path):
            raise HTTPException(status_code=500, detail=f"Failed to write scenario file: {abs_path}")

        logger.info("update_fire_target: wrote fire_target %s to %s", fire_target, abs_path)
        return {"success": True, "fire_target": fire_target}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("update_fire_target: failed for %s: %s", abs_path, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update FIRE target: {exc}")
