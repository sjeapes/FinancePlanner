"""
@file scenarios.py
@brief FastAPI routes for scenario management.

Endpoints:
  GET    /api/scenarios                         — list all scenario YAML files
  GET    /api/scenarios/templates               — list all template YAML files
  GET    /api/scenarios/{name}                  — load and return a scenario
  POST   /api/scenarios                         — create a new scenario YAML
  PUT    /api/scenarios/{name}                  — update a scenario YAML
  DELETE /api/scenarios/{name}                  — delete a scenario (not base)
  GET    /api/scenarios/compare?paths=a,b       — compare key metrics side-by-side
                                                  (accepts full relative paths)
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from backend.engine.calculator import ProjectionEngine
from backend.engine.scenario_engine import load_scenario_for_projection
from backend.models.pydantic_models import ScenarioModel
from backend.persistence.yaml_serialiser import (
    dump_yaml,
    load_scenario_from_file,
    load_yaml,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class ScenarioListItem(BaseModel):
    """
    @brief Summary item for scenario list response.
    @param name Scenario file name (without .yaml).
    @param path Relative file path.
    @param id Scenario id from YAML.
    @param display_name Scenario display name.
    @param is_base Whether this is the base scenario.
    @param description Scenario description.
    """
    model_config = ConfigDict(from_attributes=True)

    name: str
    path: str
    id: str = ""
    display_name: str = ""
    is_base: bool = False
    description: str = ""


class CreateScenarioRequest(BaseModel):
    """
    @brief Request body for POST /api/scenarios.
    @param name Filename for the new scenario (without .yaml extension).
    @param scenario_data Dict of YAML content for the new scenario.
    """
    model_config = ConfigDict(from_attributes=True)

    name: str
    scenario_data: dict


class UpdateScenarioRequest(BaseModel):
    """
    @brief Request body for PUT /api/scenarios/{name}.
    @param scenario_data Updated YAML content dict.
    """
    model_config = ConfigDict(from_attributes=True)

    scenario_data: dict


class ScenarioCompareMetrics(BaseModel):
    """
    @brief Key metrics for a single scenario in a comparison.
    @param name Scenario name.
    @param fire_year FIRE year or None.
    @param net_worth_2030 Net worth at 2030.
    @param net_worth_at_retirement Net worth at primary person's retirement year.
    @param final_net_worth Net worth at final projection year.
    @param prob_fire Monte Carlo FIRE probability (simplified deterministic value).
    """
    model_config = ConfigDict(from_attributes=True)

    name: str
    fire_year: Optional[int] = None
    net_worth_2030: float = 0.0
    net_worth_at_retirement: Optional[float] = None
    final_net_worth: float = 0.0


class ScenarioCompareResponse(BaseModel):
    """
    @brief Response for GET /api/scenarios/compare.
    @param scenarios List of per-scenario key metric summaries.
    """
    model_config = ConfigDict(from_attributes=True)

    scenarios: list[ScenarioCompareMetrics]


class ScenarioTemplateItem(BaseModel):
    """
    @brief A single scenario template entry for the template gallery.
    @param id   Template scenario id (from YAML).
    @param name Template display name (from YAML).
    @param path Relative path to the template YAML file.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    path: str


class ScenarioComparisonRow(BaseModel):
    """
    @brief One row in the Phase 3 scenario comparison response.
    @param scenario_id    Scenario id string.
    @param scenario_name  Scenario display name.
    @param fire_year      Year FIRE target first achieved, or None.
    @param net_worth_at_years  Dict mapping year string to net worth float.
    """
    model_config = ConfigDict(from_attributes=True)

    scenario_id: str
    scenario_name: str
    fire_year: Optional[int] = None
    net_worth_at_years: dict = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scenarios_dir(request: Request) -> str:
    """
    @brief Return the absolute path to the scenarios directory.
    @param request FastAPI Request with app.state.project_root.
    @return Absolute path to data/scenarios/.
    """
    root = getattr(request.app.state, "project_root", ".")
    return os.path.join(root, "data", "scenarios")


def _scenario_path(request: Request, name: str) -> str:
    """
    @brief Build the absolute file path for a named scenario.
    @param request FastAPI Request.
    @param name Scenario file name (without .yaml).
    @return Absolute path to the YAML file.
    """
    return os.path.join(_scenarios_dir(request), f"{name}.yaml")


def _templates_dir(request: Request) -> str:
    """
    @brief Return the absolute path to the scenario templates directory.
    @param request FastAPI Request with app.state.project_root.
    @return Absolute path to data/scenarios/templates/.
    """
    root = getattr(request.app.state, "project_root", ".")
    return os.path.join(root, "data", "scenarios", "templates")


def _resolve_scenario_path(request: Request, path: str) -> str:
    """
    @brief Resolve a relative scenario path to an absolute path.

    Accepts paths like 'data/scenarios/base.yaml' or
    'data/scenarios/templates/retire_at_55.yaml' and resolves them
    relative to project_root.

    @param request FastAPI Request with app.state.project_root.
    @param path    Relative path string.
    @return        Absolute path.
    """
    root = getattr(request.app.state, "project_root", ".")
    return os.path.join(root, path)


# ── Route handlers ────────────────────────────────────────────────────────────

@router.get("/scenarios/templates", response_model=list[ScenarioTemplateItem])
def list_scenario_templates(request: Request) -> list[ScenarioTemplateItem]:
    """
    @brief List all scenario template YAML files in data/scenarios/templates/.
    @param request FastAPI Request.
    @return List of ScenarioTemplateItem with id, name, and relative path.
    """
    try:
        tmpl_dir = _templates_dir(request)
        if not os.path.isdir(tmpl_dir):
            logger.warning("list_scenario_templates: templates dir not found: %s", tmpl_dir)
            return []

        results = []
        for filename in sorted(os.listdir(tmpl_dir)):
            if not filename.endswith(".yaml"):
                continue
            stem = filename[:-5]
            abs_path = os.path.join(tmpl_dir, filename)
            rel_path = os.path.join("data", "scenarios", "templates", filename)
            try:
                data = load_yaml(abs_path)
                results.append(ScenarioTemplateItem(
                    id=str(data.get("id", stem)),
                    name=str(data.get("name", stem)),
                    path=rel_path,
                ))
            except Exception as fe:
                logger.warning(
                    "list_scenario_templates: could not read %s: %s", filename, fe
                )
                results.append(ScenarioTemplateItem(id=stem, name=stem, path=rel_path))

        logger.info("list_scenario_templates: returned %d templates", len(results))
        return results

    except Exception as exc:
        logger.error("list_scenario_templates: error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Could not list templates", "detail": str(exc)},
        )


@router.get("/scenarios/compare_v2", response_model=list[ScenarioComparisonRow])
def compare_scenarios_v2(
    request: Request,
    paths: str = Query(..., description="Comma-separated relative paths to scenario YAMLs"),
) -> list[ScenarioComparisonRow]:
    """
    @brief Run projections for multiple scenarios by path and return comparison rows.

    Accepts full relative paths (e.g. 'data/scenarios/base.yaml' or
    'data/scenarios/templates/retire_at_55.yaml').  Each scenario is loaded
    with load_scenario_from_file, projected with ProjectionEngine, and a
    comparison row is returned with net worth at snapshot years 2030, 2040,
    2050 and the FIRE year.

    A bad path is skipped with a warning rather than aborting the whole request,
    so partial results are returned rather than a 500 error.

    @param request  FastAPI Request.
    @param paths    Comma-separated list of relative YAML paths.
    @return         List of ScenarioComparisonRow.
    """
    path_list = [p.strip() for p in paths.split(",") if p.strip()]
    if not path_list:
        raise HTTPException(status_code=422, detail="No paths provided in 'paths' parameter")

    config = request.app.state.config
    tax_profiles = request.app.state.tax_profiles
    project_root = getattr(request.app.state, "project_root", ".")
    snapshot_years = [2030, 2040, 2050]
    rows: list[ScenarioComparisonRow] = []

    for rel_path in path_list:
        abs_path = _resolve_scenario_path(request, rel_path)
        if not os.path.isfile(abs_path):
            logger.warning("compare_scenarios_v2: path not found — skipping: %s", abs_path)
            continue
        try:
            scenario = load_scenario_for_projection(abs_path, project_root)
            if scenario is None:
                logger.warning("compare_scenarios_v2: could not parse — skipping: %s", abs_path)
                continue

            engine = ProjectionEngine(config, tax_profiles)
            result = engine.project(scenario)

            nw_at_years: dict = {}
            for yr in snapshot_years:
                snap = result.year(yr)
                nw_at_years[str(yr)] = round(snap.total_net_worth, 2) if snap else 0.0

            rows.append(ScenarioComparisonRow(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                fire_year=result.fire_year,
                net_worth_at_years=nw_at_years,
            ))
        except Exception as exc:
            logger.error(
                "compare_scenarios_v2: engine error for '%s': %s", rel_path, exc, exc_info=True
            )
            # Skip bad scenarios — do not abort the whole comparison
            continue

    return rows


@router.get("/scenarios", response_model=list[ScenarioListItem])
def list_scenarios(request: Request) -> list[ScenarioListItem]:
    """
    @brief List all scenario YAML files in data/scenarios/.
    @param request FastAPI Request.
    @return List of ScenarioListItem summaries.
    """
    try:
        sc_dir = _scenarios_dir(request)
        if not os.path.isdir(sc_dir):
            logger.warning("list_scenarios: scenarios dir not found: %s", sc_dir)
            return []

        results = []
        for filename in sorted(os.listdir(sc_dir)):
            if not filename.endswith(".yaml"):
                continue
            name = filename[:-5]
            path = os.path.join(sc_dir, filename)
            try:
                data = load_yaml(path)
                meta = data.get("scenario", data)
                results.append(ScenarioListItem(
                    name=name,
                    path=os.path.join("data", "scenarios", filename),
                    id=str(meta.get("id", name)),
                    display_name=str(meta.get("name", name)),
                    is_base=bool(meta.get("is_base", False)),
                    description=str(meta.get("description", "")),
                ))
            except Exception as fe:
                logger.warning(
                    "list_scenarios: could not read %s: %s", filename, fe
                )
                results.append(ScenarioListItem(name=name, path=path))

        return results
    except Exception as exc:
        logger.error("list_scenarios: error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Could not list scenarios", "detail": str(exc)})


@router.get("/scenarios/compare", response_model=ScenarioCompareResponse)
def compare_scenarios(
    request: Request,
    scenarios: Optional[str] = Query(None, description="Comma-separated scenario names (legacy)"),
    paths: Optional[str] = Query(None, description="Comma-separated relative YAML paths"),
) -> ScenarioCompareResponse:
    """
    @brief Run projections for multiple scenarios and return side-by-side key metrics.

    Accepts either scenario names via 'scenarios' (legacy) or full relative
    paths via 'paths'.  When 'paths' is provided it takes precedence.  Paths
    may point to any YAML in data/scenarios/ or data/scenarios/templates/.

    @param request   FastAPI Request.
    @param scenarios Comma-separated scenario names (without .yaml extension).
    @param paths     Comma-separated relative YAML paths (takes precedence).
    @return          ScenarioCompareResponse with metrics for each scenario.
    """
    # Resolve path list — prefer paths param over legacy scenarios param
    if paths:
        path_inputs = [p.strip() for p in paths.split(",") if p.strip()]
        abs_paths = [_resolve_scenario_path(request, p) for p in path_inputs]
        label_map = {ap: pi for ap, pi in zip(abs_paths, path_inputs)}
    elif scenarios:
        names = [n.strip() for n in scenarios.split(",") if n.strip()]
        abs_paths = [_scenario_path(request, n) for n in names]
        label_map = {ap: n for ap, n in zip(abs_paths, names)}
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'scenarios' (names) or 'paths' (relative paths) query param",
        )

    if not abs_paths:
        raise HTTPException(status_code=422, detail="No scenario paths resolved")

    config = request.app.state.config
    tax_profiles = request.app.state.tax_profiles
    project_root = getattr(request.app.state, "project_root", ".")
    results = []

    for abs_path in abs_paths:
        label = label_map.get(abs_path, abs_path)
        if not os.path.isfile(abs_path):
            raise HTTPException(status_code=404, detail=f"Scenario not found: {label}")
        try:
            scenario = load_scenario_for_projection(abs_path, project_root)
            if scenario is None:
                raise HTTPException(status_code=422, detail=f"Could not parse scenario: {label}")

            engine = ProjectionEngine(config, tax_profiles)
            result = engine.project(scenario)

            # Key metrics extraction
            retirement_year = None
            if scenario.people:
                retirement_year = scenario.people[0].retirement_year()

            nw_2030 = result.year(2030)
            nw_final = result.years[-1].total_net_worth if result.years else 0.0
            nw_retirement = (
                result.year(retirement_year).total_net_worth
                if retirement_year and result.year(retirement_year)
                else None
            )

            results.append(ScenarioCompareMetrics(
                name=scenario.name,
                fire_year=result.fire_year,
                net_worth_2030=nw_2030.total_net_worth if nw_2030 else 0.0,
                net_worth_at_retirement=nw_retirement,
                final_net_worth=nw_final,
            ))
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("compare_scenarios: error for %s: %s", label, exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"error": f"Engine error for {label}", "detail": str(exc)},
            )

    return ScenarioCompareResponse(scenarios=results)


@router.get("/scenarios/{name}", response_model=ScenarioModel)
def get_scenario(name: str, request: Request) -> ScenarioModel:
    """
    @brief Load and return a full scenario by name.
    @param name Scenario file name (without .yaml).
    @param request FastAPI Request.
    @return ScenarioModel with all fields populated.
    """
    path = _scenario_path(request, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {name}")

    try:
        scenario = load_scenario_from_file(path)
        if scenario is None:
            raise HTTPException(status_code=422, detail=f"Could not parse scenario: {name}")
        return ScenarioModel.from_dataclass(scenario)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_scenario: error for %s: %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Load error", "detail": str(exc)})


@router.post("/scenarios", response_model=ScenarioListItem, status_code=201)
def create_scenario(body: CreateScenarioRequest, request: Request) -> ScenarioListItem:
    """
    @brief Create a new scenario YAML file.
    @param body CreateScenarioRequest with name and scenario_data dict.
    @param request FastAPI Request.
    @return ScenarioListItem for the newly created scenario.
    """
    sc_dir = _scenarios_dir(request)
    path = os.path.join(sc_dir, f"{body.name}.yaml")

    if os.path.exists(path):
        raise HTTPException(
            status_code=409,
            detail=f"Scenario already exists: {body.name}",
        )

    try:
        os.makedirs(sc_dir, exist_ok=True)
        ok = dump_yaml(body.scenario_data, path)
        if not ok:
            raise HTTPException(
                status_code=500,
                detail={"error": "Write error", "detail": f"Could not write {path}"},
            )
        meta = body.scenario_data.get("scenario", body.scenario_data)
        return ScenarioListItem(
            name=body.name,
            path=os.path.join("data", "scenarios", f"{body.name}.yaml"),
            id=str(meta.get("id", body.name)),
            display_name=str(meta.get("name", body.name)),
            is_base=bool(meta.get("is_base", False)),
            description=str(meta.get("description", "")),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("create_scenario: error for %s: %s", body.name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Create error", "detail": str(exc)})


@router.put("/scenarios/{name}", response_model=ScenarioListItem)
def update_scenario(
    name: str,
    body: UpdateScenarioRequest,
    request: Request,
) -> ScenarioListItem:
    """
    @brief Update an existing scenario YAML file.
    @param name Scenario file name (without .yaml).
    @param body UpdateScenarioRequest with new scenario_data.
    @param request FastAPI Request.
    @return Updated ScenarioListItem.
    """
    path = _scenario_path(request, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {name}")

    try:
        ok = dump_yaml(body.scenario_data, path)
        if not ok:
            raise HTTPException(
                status_code=500,
                detail={"error": "Write error", "detail": f"Could not write {path}"},
            )
        meta = body.scenario_data.get("scenario", body.scenario_data)
        return ScenarioListItem(
            name=name,
            path=os.path.join("data", "scenarios", f"{name}.yaml"),
            id=str(meta.get("id", name)),
            display_name=str(meta.get("name", name)),
            is_base=bool(meta.get("is_base", False)),
            description=str(meta.get("description", "")),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("update_scenario: error for %s: %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Update error", "detail": str(exc)})


@router.delete("/scenarios/{name}", status_code=204)
def delete_scenario(name: str, request: Request) -> None:
    """
    @brief Delete a scenario YAML file. The base scenario cannot be deleted.
    @param name Scenario file name (without .yaml).
    @param request FastAPI Request.
    """
    if name == "base":
        raise HTTPException(
            status_code=403,
            detail="The base scenario cannot be deleted.",
        )

    path = _scenario_path(request, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {name}")

    try:
        os.remove(path)
        logger.info("delete_scenario: removed %s", path)
    except Exception as exc:
        logger.error("delete_scenario: error for %s: %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Delete error", "detail": str(exc)})
