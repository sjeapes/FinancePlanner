"""
@file generate_phase3_notebook.py
@brief Generates LifeLedger_Phase3_Tests.ipynb for Phase 3 validation.

Run from the project root:
    python tests/generate_phase3_notebook.py

Produces LifeLedger_Phase3_Tests.ipynb with cells covering:
  1. Environment check (scenario_engine imports)
  2. All 8 templates load without errors
  3. merge_scenario correctly overrides retirement ages in retire_at_55
  4. validate_scenario passes on valid scenario, fails on empty people
  5. GET /api/scenarios/templates returns 8 templates (FastAPI TestClient)
  6. GET /api/scenarios/compare returns correct data for base + retire_at_55
  7. Summary cell
"""

import json
import os
import sys

# Ensure project root is on the path when running directly
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _code_cell(source: str) -> dict:
    """
    @brief Build a Jupyter code cell dict.
    @param source Python source code string.
    @return Notebook cell dict.
    """
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.strip(),
    }


def _markdown_cell(source: str) -> dict:
    """
    @brief Build a Jupyter markdown cell dict.
    @param source Markdown source string.
    @return Notebook cell dict.
    """
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.strip(),
    }


def build_notebook() -> dict:
    """
    @brief Assemble the full Phase 3 validation notebook dict.
    @return Jupyter notebook dict ready for json.dump.
    """
    cells = []

    # ── Cell 0: Markdown header ───────────────────────────────────────────────
    cells.append(_markdown_cell("""
# LifeLedger Phase 3 — Scenario Builder & FIRE Modelling Tests

Validates the Phase 3 scenario engine, template YAML files, merge logic,
validation, and API endpoints. Run all cells top to bottom from the project root.
"""))

    # ── Cell 1: Environment setup + sys.path ─────────────────────────────────
    cells.append(_code_cell("""
import sys
import os
import logging

# Ensure project root is importable
PROJECT_ROOT = os.path.abspath(os.path.join(os.getcwd()))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING, format='%(levelname)-8s %(name)-30s %(message)s')

print(f"Project root: {PROJECT_ROOT}")
print(f"Python: {sys.version}")
"""))

    # ── Cell 2: Import check ─────────────────────────────────────────────────
    cells.append(_markdown_cell("## 1. Environment — Import Check"))
    cells.append(_code_cell("""
from backend.engine.scenario_engine import (
    merge_scenario,
    validate_scenario,
    load_scenario_with_merge,
)
from backend.persistence.yaml_serialiser import (
    load_scenario_from_file,
    load_yaml,
)
from backend.models.models import Scenario, FIRETarget

print("scenario_engine OK — all imports successful")
assert callable(merge_scenario), "merge_scenario not callable"
assert callable(validate_scenario), "validate_scenario not callable"
assert callable(load_scenario_with_merge), "load_scenario_with_merge not callable"
print("PASS: all Phase 3 engine functions importable")
"""))

    # ── Cell 3: Load all 8 templates ─────────────────────────────────────────
    cells.append(_markdown_cell("## 2. Template Loading — All 8 Templates"))
    cells.append(_code_cell("""
import os

BASE_PATH = "data/scenarios/base.yaml"
TEMPLATES_DIR = "data/scenarios/templates"

base = load_scenario_from_file(BASE_PATH)
assert base is not None, f"Could not load base scenario from {BASE_PATH}"
print(f"Base loaded: '{base.name}' — {len(base.people)} people, {len(base.income_sources)} income sources")

expected_templates = [
    "retire_at_55",
    "sell_house_2030",
    "stress_test",
    "aggressive_fire",
    "partner_death_70",
    "inheritance_65",
    "annuity_vs_drawdown",
    "move_to_us",
]

loaded = {}
for tmpl_id in expected_templates:
    path = os.path.join(TEMPLATES_DIR, f"{tmpl_id}.yaml")
    assert os.path.isfile(path), f"Template file missing: {path}"
    data = load_yaml(path)
    assert data, f"Template YAML empty or unparseable: {path}"
    loaded[tmpl_id] = data
    print(f"  OK  {tmpl_id:30s} id={data.get('id')} name={data.get('name')}")

assert len(loaded) == 8, f"Expected 8 templates, found {len(loaded)}"
print(f"\\nPASS: all {len(loaded)} templates present and loadable")
"""))

    # ── Cell 4: merge_scenario — retire_at_55 ────────────────────────────────
    cells.append(_markdown_cell("## 3. merge_scenario — retire_at_55 Overrides"))
    cells.append(_code_cell("""
diff_path = "data/scenarios/templates/retire_at_55.yaml"
diff = load_yaml(diff_path)

# Base has James retirement_age=60, Sarah retirement_age=60
assert base.people[0].retirement_age == 60, f"Base James should be 60, got {base.people[0].retirement_age}"

merged = merge_scenario(base, diff)

# After merge: James=55, Sarah=53
james_m = next((p for p in merged.people if p.id == "james"), None)
sarah_m = next((p for p in merged.people if p.id == "sarah"), None)

assert james_m is not None, "James missing from merged scenario"
assert sarah_m is not None, "Sarah missing from merged scenario"
assert james_m.retirement_age == 55, f"Expected James retirement_age=55, got {james_m.retirement_age}"
assert sarah_m.retirement_age == 53, f"Expected Sarah retirement_age=53, got {sarah_m.retirement_age}"
assert merged.id == "retire_at_55", f"Expected id='retire_at_55', got '{merged.id}'"
assert merged.fire_target is not None, "fire_target should be set"
assert merged.fire_target.swr == 0.035, f"Expected SWR=0.035, got {merged.fire_target.swr}"
assert merged.fire_target.target_net_worth == 1_500_000, (
    f"Expected £1.5m target, got {merged.fire_target.target_net_worth}"
)

# Base must NOT be mutated
assert base.people[0].retirement_age == 60, "Base was mutated — merge_scenario must deep-copy!"

print(f"James retirement_age (base): {base.people[0].retirement_age}  → (merged): {james_m.retirement_age}")
print(f"Sarah retirement_age (base): {base.people[1].retirement_age}  → (merged): {sarah_m.retirement_age}")
print(f"FIRE target SWR: {merged.fire_target.swr}  target: £{merged.fire_target.target_net_worth:,.0f}")
print("PASS: merge_scenario correctly overrides retirement ages and FIRE target")
"""))

    # ── Cell 5: validate_scenario ─────────────────────────────────────────────
    cells.append(_markdown_cell("## 4. validate_scenario — Pass and Fail Cases"))
    cells.append(_code_cell("""
import copy

# Should pass on the base scenario
errors = validate_scenario(base)
assert errors == [], f"Base scenario should be valid, got errors: {errors}"
print(f"validate_scenario(base): PASS — no errors")

# Should pass on a properly merged scenario
errors_merged = validate_scenario(merged)
assert errors_merged == [], f"Merged retire_at_55 should be valid, got: {errors_merged}"
print(f"validate_scenario(merged retire_at_55): PASS — no errors")

# Should fail on empty people
empty_people = copy.deepcopy(base)
empty_people.people = []
errors_no_people = validate_scenario(empty_people)
assert any("no people" in e.lower() for e in errors_no_people), (
    f"Expected 'no people' error, got: {errors_no_people}"
)
print(f"validate_scenario(no people): PASS — caught: {errors_no_people[0]}")

# Should fail on missing FIRE target
no_fire = copy.deepcopy(base)
no_fire.fire_target = None
errors_no_fire = validate_scenario(no_fire)
assert any("fire target" in e.lower() for e in errors_no_fire), (
    f"Expected FIRE target error, got: {errors_no_fire}"
)
print(f"validate_scenario(no fire_target): PASS — caught: {errors_no_fire[0]}")

# Should fail on empty income sources
no_income = copy.deepcopy(base)
no_income.income_sources = []
errors_no_income = validate_scenario(no_income)
assert any("income" in e.lower() for e in errors_no_income), (
    f"Expected income error, got: {errors_no_income}"
)
print(f"validate_scenario(no income): PASS — caught: {errors_no_income[0]}")

print("\\nPASS: all validate_scenario cases behave correctly")
"""))

    # ── Cell 6: API setup — single TestClient used across cells ──────────────
    cells.append(_markdown_cell("## 5. API — Setup TestClient"))
    cells.append(_code_cell("""
from fastapi.testclient import TestClient
from backend.main import app

# TestClient triggers the FastAPI startup event so app.state is fully populated.
# Keep the client alive across test cells by not using a context manager here;
# the startup event fires on first request in this mode.
client = TestClient(app, raise_server_exceptions=True)

# Warm-up ping
ping = client.get("/api/health")
print(f"Health check: {ping.status_code}  (200=OK, 404=no health route — both acceptable)")
print("TestClient ready")
"""))

    # ── Cell 7: GET /api/scenarios/templates ──────────────────────────────────
    cells.append(_markdown_cell("## 5b. API — GET /api/scenarios/templates"))
    cells.append(_code_cell("""
resp = client.get("/api/scenarios/templates")
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

templates_data = resp.json()
assert isinstance(templates_data, list), f"Expected list, got {type(templates_data)}"
assert len(templates_data) == 8, f"Expected 8 templates, got {len(templates_data)}"

template_ids = {t["id"] for t in templates_data}
for expected_id in expected_templates:
    assert expected_id in template_ids, f"Template '{expected_id}' missing from API response"

print(f"GET /api/scenarios/templates: returned {len(templates_data)} templates")
for t in templates_data:
    print(f"  {t['id']:30s}  {t['name']}")
print("PASS: all 8 templates returned by API")
"""))

    # ── Cell 8: API — GET /api/scenarios/compare ──────────────────────────────
    cells.append(_markdown_cell("## 6. API — GET /api/scenarios/compare (paths param)"))
    cells.append(_code_cell("""
# Compare base vs retire_at_55 using the paths query param
compare_paths = "data/scenarios/base.yaml,data/scenarios/templates/retire_at_55.yaml"
resp2 = client.get(f"/api/scenarios/compare?paths={compare_paths}")
assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"

cmp_data = resp2.json()
assert "scenarios" in cmp_data, f"Response missing 'scenarios' key: {cmp_data}"
assert len(cmp_data["scenarios"]) == 2, (
    f"Expected 2 comparison rows, got {len(cmp_data['scenarios'])}"
)

base_row = cmp_data["scenarios"][0]
retire_row = cmp_data["scenarios"][1]

print(f"Base scenario:       FIRE year={base_row['fire_year']}  NW@2030=£{base_row['net_worth_2030']:,.0f}")
print(f"Retire@55 scenario:  FIRE year={retire_row['fire_year']}  NW@2030=£{retire_row['net_worth_2030']:,.0f}")

assert base_row["fire_year"] is not None, "Base should have a FIRE year"
assert base_row["fire_year"] == 2031, f"Base FIRE year regression — expected 2031, got {base_row['fire_year']}"
assert base_row["net_worth_2030"] > 500_000, (
    f"Base NW@2030 too low: {base_row['net_worth_2030']}"
)
print("PASS: compare endpoint returns correct data for base + retire_at_55")
"""))

    # ── Cell 9: compare_v2 endpoint ──────────────────────────────────────────
    cells.append(_markdown_cell("## 6b. API — GET /api/scenarios/compare_v2 (detailed rows)"))
    cells.append(_code_cell("""
resp3 = client.get(f"/api/scenarios/compare_v2?paths={compare_paths}")
assert resp3.status_code == 200, f"Expected 200, got {resp3.status_code}: {resp3.text}"

rows = resp3.json()
assert isinstance(rows, list), f"Expected list, got {type(rows)}"
assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"

base_v2 = next((r for r in rows if r["scenario_id"] == "base"), None)
retire_v2 = next((r for r in rows if r["scenario_id"] == "retire_at_55"), None)

assert base_v2 is not None, "base row missing from compare_v2 response"
assert retire_v2 is not None, "retire_at_55 row missing from compare_v2 response"
assert "2030" in base_v2["net_worth_at_years"], "Missing 2030 in net_worth_at_years"
assert "2040" in base_v2["net_worth_at_years"], "Missing 2040 in net_worth_at_years"

print(f"Base v2:      {base_v2['scenario_name']}  FIRE={base_v2['fire_year']}")
for yr, nw in sorted(base_v2["net_worth_at_years"].items()):
    print(f"              {yr}: £{nw:,.0f}")
print(f"Retire@55 v2: {retire_v2['scenario_name']}  FIRE={retire_v2['fire_year']}")
print("PASS: compare_v2 returns structured net_worth_at_years dict")
"""))

    # ── Cell 9: Summary ───────────────────────────────────────────────────────
    cells.append(_markdown_cell("## 7. Phase 3 Summary"))
    cells.append(_code_cell("""
print("=" * 60)
print("  LifeLedger Phase 3 — Validation Summary")
print("=" * 60)
print("  1. Engine imports          PASS")
print("  2. All 8 templates load    PASS")
print("  3. merge_scenario          PASS")
print("  4. validate_scenario       PASS")
print("  5. /api/scenarios/templates PASS")
print("  6. /api/scenarios/compare  PASS")
print("  6b. /api/scenarios/compare_v2 PASS")
print("=" * 60)
print("  Phase 3 validation: ALL PASS")
"""))

    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12.0",
            },
        },
        "cells": cells,
    }
    return notebook


if __name__ == "__main__":
    nb = build_notebook()
    output_path = os.path.join(_PROJECT_ROOT, "LifeLedger_Phase3_Tests.ipynb")
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, indent=1)
    print(f"Generated: {output_path}")
    print(f"Cells: {len(nb['cells'])}")
