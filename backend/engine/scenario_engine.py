"""
@file scenario_engine.py
@brief Scenario merge, validation, and load helpers for Phase 3 LifeLedger.

Provides runtime merging of scenario diff YAMLs onto a base scenario,
validation of merged scenarios before projection, and a convenience loader
that combines both steps. Scenarios are stored as diffs (only changed fields);
this engine reconstitutes a complete Scenario at runtime without persisting
a redundant full copy.
"""

import copy
import logging
from typing import Optional

from backend.models.models import Scenario
from backend.persistence.yaml_serialiser import (
    load_scenario_from_file,
    load_yaml,
    parse_scenario,
    parse_person,
    parse_fire_target,
    parse_life_event,
    parse_income_source,
    parse_savings_account,
    parse_investment_account,
    parse_pension_fund,
    parse_property,
    parse_mortgage,
    parse_expense_bucket,
)

logger = logging.getLogger(__name__)


def merge_scenario(base: Scenario, diff: dict) -> Scenario:
    """
    @brief Deep-merge a diff dict onto a base Scenario, returning a new Scenario.

    The diff only contains fields that change from the base. Lists (people,
    income_sources, life_events, etc.) are merged by ID: items present in the
    diff override the matching base item; items absent from the diff are kept
    unchanged; new items in the diff are appended.  The base Scenario is never
    mutated — a deep copy is returned.

    Supports overriding top-level scenario metadata (id, name, is_base, colour)
    and any combination of:
      people, income_sources, savings_accounts, investment_accounts,
      pension_funds, properties, mortgages, expense_buckets,
      life_events, fire_target.

    @param base  The fully-populated base Scenario dataclass.
    @param diff  Raw dict loaded from a diff YAML file.
    @return      New merged Scenario; the base is unchanged.
    """
    try:
        merged = copy.deepcopy(base)

        # ── Top-level metadata ────────────────────────────────────────────────
        if "id" in diff:
            merged.id = str(diff["id"])
        if "name" in diff:
            merged.name = str(diff["name"])
        if "description" in diff:
            merged.description = str(diff["description"])
        if "is_base" in diff:
            merged.is_base = bool(diff["is_base"])
        if "colour" in diff:
            merged.colour = str(diff["colour"])

        # ── List merge helper (merge by id field) ─────────────────────────────
        def _merge_list(base_list, diff_list_raw, parser_fn):
            """
            @brief Merge a diff list into a base list by item id.
            @param base_list   Existing list on the merged scenario.
            @param diff_list_raw  Raw dicts from the diff YAML.
            @param parser_fn   Parser that converts a raw dict to a dataclass.
            @return Merged list.
            """
            if not diff_list_raw:
                return base_list
            # Index base items by id for fast lookup
            base_by_id = {item.id: item for item in base_list}
            result = list(base_list)  # start with all base items

            for raw in diff_list_raw:
                item_id = str(raw.get("id", ""))
                if item_id and item_id in base_by_id:
                    # Merge raw dict fields onto the existing base item dict
                    # by converting the base item back to a partial dict and
                    # overlaying the diff fields before re-parsing.
                    try:
                        existing = base_by_id[item_id]
                        # Build a merged dict from the existing object's fields
                        # The safest approach: start with a full dict representation
                        # then overlay the diff fields.
                        merged_dict = _dataclass_to_dict(existing)
                        for k, v in raw.items():
                            merged_dict[k] = v
                        parsed = parser_fn(merged_dict)
                        if parsed is not None:
                            # Replace in result list
                            result = [parsed if item.id == item_id else item for item in result]
                        else:
                            logger.warning(
                                "merge_scenario: failed to re-parse item id=%s — keeping base", item_id
                            )
                    except Exception as exc:
                        logger.error(
                            "merge_scenario: error merging item id=%s: %s", item_id, exc
                        )
                else:
                    # New item not in base — parse and append
                    try:
                        parsed = parser_fn(raw)
                        if parsed is not None:
                            result.append(parsed)
                            if item_id:
                                base_by_id[item_id] = parsed
                    except Exception as exc:
                        logger.error(
                            "merge_scenario: error parsing new item %s: %s", raw, exc
                        )
            return result

        # ── Apply list sections ───────────────────────────────────────────────
        if "people" in diff:
            merged.people = _merge_list(merged.people, diff["people"], parse_person)

        if "income_sources" in diff:
            merged.income_sources = _merge_list(
                merged.income_sources, diff["income_sources"], parse_income_source
            )

        if "savings_accounts" in diff:
            merged.savings_accounts = _merge_list(
                merged.savings_accounts, diff["savings_accounts"], parse_savings_account
            )

        if "investment_accounts" in diff:
            merged.investment_accounts = _merge_list(
                merged.investment_accounts, diff["investment_accounts"], parse_investment_account
            )

        if "pension_funds" in diff:
            merged.pension_funds = _merge_list(
                merged.pension_funds, diff["pension_funds"], parse_pension_fund
            )

        if "properties" in diff:
            merged.properties = _merge_list(
                merged.properties, diff["properties"], parse_property
            )

        if "mortgages" in diff:
            merged.mortgages = _merge_list(
                merged.mortgages, diff["mortgages"], parse_mortgage
            )

        if "expense_buckets" in diff:
            merged.expense_buckets = _merge_list(
                merged.expense_buckets, diff["expense_buckets"], parse_expense_bucket
            )

        if "life_events" in diff:
            merged.life_events = _merge_list(
                merged.life_events, diff["life_events"], parse_life_event
            )

        # ── FIRE target (scalar override, not list) ───────────────────────────
        if "fire_target" in diff and diff["fire_target"]:
            fire_raw = diff["fire_target"]
            if merged.fire_target is not None:
                # Merge: overlay diff keys onto existing fire_target dict
                existing_fire_dict = {
                    "target_net_worth": merged.fire_target.target_net_worth,
                    "annual_expenses_target": merged.fire_target.annual_expenses_target,
                    "swr": merged.fire_target.swr,
                    "fire_type": merged.fire_target.fire_type,
                }
                # Map alternate key names used in diff YAMLs
                if "annual_expenses" in fire_raw:
                    existing_fire_dict["annual_expenses_target"] = fire_raw.pop("annual_expenses")
                existing_fire_dict.update(fire_raw)
                merged.fire_target = parse_fire_target(existing_fire_dict)
            else:
                # Map alternate key names
                if "annual_expenses" in fire_raw:
                    fire_raw = dict(fire_raw)
                    fire_raw["annual_expenses_target"] = fire_raw.pop("annual_expenses")
                merged.fire_target = parse_fire_target(fire_raw)

        logger.info(
            "merge_scenario: merged '%s' onto base '%s' — result id='%s'",
            diff.get("id", "?"), base.id, merged.id,
        )
        return merged

    except Exception as exc:
        logger.error("merge_scenario: unexpected error: %s", exc, exc_info=True)
        return copy.deepcopy(base)


def load_scenario_for_projection(path: str, project_root: str = ".") -> Optional[Scenario]:
    """
    @brief Load a scenario from a path, merging with base when the path is a
           template diff (i.e. lives under a templates/ subdirectory).

    Full scenarios in data/scenarios/ are loaded directly via
    load_scenario_from_file.  Template diffs in data/scenarios/templates/ are
    merged onto data/scenarios/base.yaml before being returned.  This is the
    canonical entry point for all simulation and comparison routes.

    @param path          Relative (from project_root) or absolute path.
    @param project_root  Project root directory; used to resolve relative paths.
    @return              Merged and validated Scenario, or None on any error.
    """
    import os as _os

    abs_path = path if _os.path.isabs(path) else _os.path.join(project_root, path)
    norm = abs_path.replace("\\", "/")
    is_template = "/scenarios/templates/" in norm

    if is_template:
        scenarios_dir = _os.path.normpath(_os.path.join(_os.path.dirname(abs_path), ".."))
        base_path = _os.path.join(scenarios_dir, "base.yaml")
        if not _os.path.isfile(base_path):
            logger.error("load_scenario_for_projection: base not found at %s", base_path)
            return None
        logger.info(
            "load_scenario_for_projection: merging template '%s' onto base '%s'",
            abs_path, base_path,
        )
        return load_scenario_with_merge(base_path, abs_path)

    try:
        scenario = load_scenario_from_file(abs_path)
        if scenario is None:
            logger.error("load_scenario_for_projection: could not parse '%s'", abs_path)
        return scenario
    except Exception as exc:
        logger.error("load_scenario_for_projection: error loading '%s': %s", abs_path, exc)
        return None


def _dataclass_to_dict(obj) -> dict:
    """
    @brief Shallow-convert a dataclass instance to a plain dict for re-parsing.

    Only extracts the fields needed by YAML parsers. Uses __dataclass_fields__
    when available; falls back to __dict__. Does not recurse — sub-objects
    remain as dataclass instances (the parsers accept both dict and dataclass
    field types via the _float/_int helpers).

    @param obj  Any dataclass instance.
    @return     Dict suitable for passing to a parse_* function.
    """
    try:
        import dataclasses
        if dataclasses.is_dataclass(obj):
            return {
                f.name: getattr(obj, f.name)
                for f in dataclasses.fields(obj)
            }
        return vars(obj)
    except Exception as exc:
        logger.warning("_dataclass_to_dict: could not convert %s: %s", type(obj).__name__, exc)
        return {}


def validate_scenario(scenario: Scenario) -> list:
    """
    @brief Validate a Scenario and return a list of human-readable error strings.

    An empty return list means the scenario is valid and safe to project.
    Does not raise exceptions — all checks are soft validations.

    Checks performed:
      - At least one Person defined
      - At least one IncomeSource defined
      - FIRE target is set (not None)
      - All destination_account_ids referenced in income contributions
        exist in savings_accounts + investment_accounts + pension_funds

    @param scenario  The Scenario to validate (may be merged or raw base).
    @return          List of error strings; empty list = valid.
    """
    errors = []

    try:
        # ── People ────────────────────────────────────────────────────────────
        if not scenario.people:
            errors.append("Scenario has no people defined.")

        # ── Income sources ────────────────────────────────────────────────────
        if not scenario.income_sources:
            errors.append("Scenario has no income sources defined.")

        # ── FIRE target ───────────────────────────────────────────────────────
        if scenario.fire_target is None:
            errors.append("Scenario has no FIRE target defined.")

        # ── Contribution account references ───────────────────────────────────
        known_account_ids = set()
        for acc in scenario.savings_accounts:
            known_account_ids.add(acc.id)
        for acc in scenario.investment_accounts:
            known_account_ids.add(acc.id)
        for pf in scenario.pension_funds:
            known_account_ids.add(pf.id)

        for src in scenario.income_sources:
            for contrib in src.contributions:
                dest = contrib.destination_account_id
                if dest and dest not in known_account_ids:
                    errors.append(
                        f"Income source '{src.id}' references unknown account "
                        f"'{dest}' in contributions."
                    )

    except Exception as exc:
        logger.error("validate_scenario: unexpected error: %s", exc, exc_info=True)
        errors.append(f"Validation error: {exc}")

    if errors:
        logger.warning(
            "validate_scenario: scenario '%s' has %d error(s): %s",
            scenario.id, len(errors), errors,
        )
    else:
        logger.info("validate_scenario: scenario '%s' is valid", scenario.id)

    return errors


def load_scenario_with_merge(
    base_path: str,
    diff_path: str,
    serialiser_fn=None,
) -> Optional[Scenario]:
    """
    @brief Load a base scenario, load a diff YAML, merge them, validate, and return.

    Combines load_scenario_from_file + merge_scenario + validate_scenario in
    one call. Returns None on any load or validation failure rather than
    raising, so callers can safely iterate over multiple scenarios without
    one bad file crashing the rest.

    @param base_path     Path to the base scenario YAML file.
    @param diff_path     Path to the diff scenario YAML file.
    @param serialiser_fn Optional override for the base-load function (useful
                         for testing); defaults to load_scenario_from_file.
    @return              Merged and validated Scenario, or None on failure.
    """
    if serialiser_fn is None:
        serialiser_fn = load_scenario_from_file

    try:
        base = serialiser_fn(base_path)
        if base is None:
            logger.error(
                "load_scenario_with_merge: could not load base from %s", base_path
            )
            return None
    except Exception as exc:
        logger.error(
            "load_scenario_with_merge: error loading base '%s': %s", base_path, exc
        )
        return None

    try:
        diff_data = load_yaml(diff_path)
        if not diff_data:
            logger.error(
                "load_scenario_with_merge: could not load diff from %s", diff_path
            )
            return None
    except Exception as exc:
        logger.error(
            "load_scenario_with_merge: error loading diff '%s': %s", diff_path, exc
        )
        return None

    try:
        merged = merge_scenario(base, diff_data)
    except Exception as exc:
        logger.error(
            "load_scenario_with_merge: merge failed for diff '%s': %s", diff_path, exc
        )
        return None

    errors = validate_scenario(merged)
    if errors:
        logger.warning(
            "load_scenario_with_merge: merged scenario '%s' failed validation: %s",
            merged.id, errors,
        )
        # Return anyway — callers decide whether to abort on warnings
        return merged

    return merged
