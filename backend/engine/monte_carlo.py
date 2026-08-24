"""
@file monte_carlo.py
@brief Enhanced Monte Carlo simulation engine for LifeLedger Phase 3.

Extends the basic MC in calculator.py with:

  1. **Structured confidence bands** — P5/P10/P25/P50/P75/P90/P95 extracted
     per calendar year from N simulations, ready for graph rendering.

  2. **Multi-scenario comparison** — runs independent MC bands for up to 4
     scenarios simultaneously so the graph can overlay them.

  3. **Inflation scenario modelling** — low / mid / high macro scenarios with
     distinct inflation and real-return assumptions, beyond the random
     perturbation of the base MC.  Each scenario is deterministic but uses
     different parameter sets.

  4. **Sequence-of-returns risk** — optional crash injection in the first few
     years of retirement to test portfolio resilience.

  5. **FIRE probability over time** — P(FIRE achieved) by calendar year,
     showing how certainty builds as the projection approaches the FIRE year.

  6. **Surplus / shortfall analysis** — per-year probability of the portfolio
     covering a target annual drawdown amount, useful for income-coverage
     reporting.

Integration::

    from backend.engine.monte_carlo import MonteCarloEngine, MonteCarloConfig
    from backend.engine.calculator import ProjectionEngine
    from backend.engine.scenario_engine import load_scenario_for_projection

    engine = MonteCarloEngine(mc_config, app_config, tax_profiles)
    result = engine.run_scenario(scenario)
    comparison = engine.compare_scenarios([base, alt1, alt2])

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import yaml

from backend.engine.calculator import ProjectionEngine, TimelineResult, MonteCarloResult
from backend.models.models import AppConfig, Scenario

logger = logging.getLogger("lifeledger.monte_carlo")


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MacroScenarioParams:
    """
    @brief Parameters for one named macro scenario (low / mid / high).

    @param label                    Display label, e.g. 'Low', 'Mid', 'High'.
    @param inflation_rate            Annual CPI assumption as a decimal.
    @param equity_real_return        Expected real annual return on equities.
    @param bond_real_return          Expected real annual return on bonds.
    @param cash_real_return          Expected real annual return on cash.
    @param property_growth_real      Expected real annual property price growth.
    @param salary_real_growth        Expected real annual salary growth.
    @param uk_house_price_growth     Nominal UK house price growth p.a.
    @param us_house_price_growth     Nominal US house price growth p.a.
    @param fx_gbpusd                 GBP/USD exchange rate assumption.
    @param colour                    Hex colour for graph rendering.
    @param notes                     Free-text notes.
    """

    label: str
    inflation_rate: float = 0.025
    equity_real_return: float = 0.05
    bond_real_return: float = 0.01
    cash_real_return: float = 0.00
    property_growth_real: float = 0.01
    salary_real_growth: float = 0.01
    uk_house_price_growth: float = 0.03
    us_house_price_growth: float = 0.04
    fx_gbpusd: float = 1.27
    colour: str = "#58a6ff"
    notes: str = ""

    @property
    def equity_nominal_return(self) -> float:
        """@brief Nominal equity return (real + inflation)."""
        return self.equity_real_return + self.inflation_rate

    @property
    def salary_nominal_growth(self) -> float:
        """@brief Nominal salary growth (real + inflation)."""
        return self.salary_real_growth + self.inflation_rate


@dataclass
class SequenceOfReturnsConfig:
    """
    @brief Configuration for sequence-of-returns risk injection.

    @param enabled                   True to inject a crash in early retirement.
    @param crash_start_offset_years  Years after retirement start when crash occurs.
    @param crash_duration_years      Duration of the drawdown period.
    @param crash_annual_return       Annual return during crash (e.g. -0.20 = −20%).
    @param recovery_excess_return    Excess annual return in the recovery period.
    @param recovery_duration_years   How many years the recovery excess lasts.
    @param notes                     Free-text notes.
    """

    enabled: bool = True
    crash_start_offset_years: int = 1
    crash_duration_years: int = 2
    crash_annual_return: float = -0.20
    recovery_excess_return: float = 0.05
    recovery_duration_years: int = 3
    notes: str = ""


@dataclass
class MonteCarloConfig:
    """
    @brief Configuration for the enhanced Monte Carlo engine.

    @param n_simulations             Number of simulation runs per scenario.
    @param seed                      Random seed for reproducibility (None = random).
    @param growth_std                Std dev of annual growth rate perturbation.
    @param inflation_std             Std dev of annual inflation perturbation.
    @param salary_growth_std         Std dev of annual salary growth perturbation.
    @param percentiles               Percentiles to extract (0–100).
    @param macro_scenarios           Low / Mid / High macro scenario parameter sets.
    @param sequence_of_returns       Sequence-of-returns config.
    @param fire_target_net_worth     Net worth target to count as FIRE achieved.
                                     If 0, uses the scenario's own fire_target.
    @param drawdown_annual_target    Annual income target for surplus/shortfall
                                     analysis during retirement phase.
    @param max_workers               Thread pool workers for parallel MC
                                     (0 = single-threaded).
    @param log_every_n               Log progress every N simulations.
    @param enabled                   False to skip MC entirely (fast dev mode).
    @param notes                     Free-text notes.
    """

    n_simulations: int = 1000
    seed: Optional[int] = 42
    growth_std: float = 0.10
    inflation_std: float = 0.005
    salary_growth_std: float = 0.005
    percentiles: list[int] = field(default_factory=lambda: [5, 10, 25, 50, 75, 90, 95])
    macro_scenarios: list[MacroScenarioParams] = field(default_factory=list)
    sequence_of_returns: SequenceOfReturnsConfig = field(
        default_factory=SequenceOfReturnsConfig
    )
    fire_target_net_worth: float = 0.0
    drawdown_annual_target: float = 0.0
    max_workers: int = 0
    log_every_n: int = 100
    enabled: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ConfidenceBand:
    """
    @brief Confidence band for a single scenario across the projection horizon.

    @param scenario_id         Source scenario identifier.
    @param scenario_label      Display label.
    @param scenario_colour     Hex colour for graph rendering.
    @param years               Ordered list of calendar years.
    @param percentile_bands    Dict mapping percentile (int) -> list[float] of
                               net-worth values at that percentile per year.
    @param median              Alias for percentile_bands[50].
    @param n_simulations       Number of simulations used.
    @param fire_probability    Overall probability of FIRE being achieved.
    @param fire_prob_by_year   Dict mapping year -> P(FIRE achieved by that year).
    @param warnings            Warning strings.
    """

    scenario_id: str
    scenario_label: str
    scenario_colour: str
    years: list[int]
    percentile_bands: dict[int, list[float]]
    median: list[float]
    n_simulations: int
    fire_probability: float
    fire_prob_by_year: dict[int, float]
    warnings: list[str] = field(default_factory=list)

    def band(self, p: int) -> list[float]:
        """
        @brief Return the values for a specific percentile.

        @param p  Percentile (must be in percentile_bands).
        @return   List of net-worth values, one per year.
        @raises   KeyError if percentile was not computed.
        """
        return self.percentile_bands[p]


@dataclass
class ScenarioComparison:
    """
    @brief Comparison of up to 4 scenarios with confidence bands.

    @param bands          List of ConfidenceBand, one per scenario.
    @param comparison_years  Years common to all scenarios.
    @param at_key_ages    Dict mapping year -> dict[scenario_id -> median net worth].
    @param fire_crossover Dict mapping scenario_id -> first year FIRE P50 > target.
    @param notes          Free-text notes.
    """

    bands: list[ConfidenceBand]
    comparison_years: list[int]
    at_key_ages: dict[int, dict[str, float]]
    fire_crossover: dict[str, Optional[int]]
    notes: str = ""


@dataclass
class MacroScenarioBand:
    """
    @brief Deterministic projection under a named macro scenario (low/mid/high).

    These are NOT stochastic — they are single runs with specific parameter
    sets, useful for showing a deterministic fan chart alongside the MC bands.

    @param label       Scenario label (e.g. 'Low', 'Mid', 'High').
    @param colour      Hex colour.
    @param years       Calendar years.
    @param net_worths  Net worth at each year under this macro scenario.
    @param fire_year   Year FIRE is achieved, or None.
    @param params      The MacroScenarioParams used.
    """

    label: str
    colour: str
    years: list[int]
    net_worths: list[float]
    fire_year: Optional[int]
    params: MacroScenarioParams


@dataclass
class SurplusShortfallResult:
    """
    @brief Year-by-year probability that the portfolio covers the drawdown target.

    @param years                  Calendar years.
    @param prob_surplus           P(portfolio > drawdown target) per year.
    @param expected_surplus       Median surplus (positive = covered).
    @param shortfall_years        Years where median falls below target.
    @param worst_case_shortfall   Maximum median shortfall across all years.
    """

    years: list[int]
    prob_surplus: list[float]
    expected_surplus: list[float]
    shortfall_years: list[int]
    worst_case_shortfall: float


@dataclass
class PhaseThreeResult:
    """
    @brief Complete Phase 3 output for a single scenario.

    @param scenario_id          Source scenario.
    @param confidence_band      MC confidence band.
    @param macro_bands          Low/mid/high deterministic bands.
    @param surplus_shortfall    Surplus/shortfall analysis.
    @param total_simulations    Total simulations run.
    @param runtime_seconds      Wall-clock runtime.
    @param warnings             Warning strings.
    """

    scenario_id: str
    confidence_band: ConfidenceBand
    macro_bands: list[MacroScenarioBand]
    surplus_shortfall: Optional[SurplusShortfallResult]
    total_simulations: int
    runtime_seconds: float
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MonteCarloEngine:
    """
    @brief Enhanced Monte Carlo simulation engine for Phase 3.

    Wraps the base `run_monte_carlo` from calculator.py with richer
    output structures, macro scenario support, FIRE probability curves,
    and multi-scenario comparison.

    Usage::

        engine = MonteCarloEngine(mc_config, app_config, tax_profiles)
        result = engine.run_scenario(scenario)
        comparison = engine.compare_scenarios([base, alt1, alt2])
    """

    def __init__(
        self,
        mc_config: MonteCarloConfig,
        app_config: AppConfig,
        tax_profiles: dict,
    ) -> None:
        """
        @brief Initialise the engine.

        @param mc_config      MonteCarloConfig with simulation settings.
        @param app_config     AppConfig with projection dates and inflation.
        @param tax_profiles   Dict of TaxProfile objects keyed by profile id.
        @raises ValueError    If mc_config fails validation.
        """
        self._mc = mc_config
        self._app = app_config
        self._tax = tax_profiles
        self._validate_config()
        logger.info(
            "MonteCarloEngine: n_sims=%d seed=%s growth_std=%.3f inflation_std=%.4f",
            mc_config.n_simulations,
            mc_config.seed,
            mc_config.growth_std,
            mc_config.inflation_std,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_scenario(
        self,
        scenario: Scenario,
        colour: str = "#58a6ff",
        extra_fire_target: Optional[float] = None,
    ) -> PhaseThreeResult:
        """
        @brief Run full Phase 3 analysis for a single scenario.

        Runs the stochastic MC simulation, extracts confidence bands,
        computes FIRE probability by year, runs deterministic macro scenario
        bands (low/mid/high), and optionally computes surplus/shortfall.

        @param scenario          Scenario to simulate.
        @param colour            Hex colour for graph rendering.
        @param extra_fire_target Override FIRE target net worth (0 = use config).
        @return                  PhaseThreeResult.
        """
        import time
        t0 = time.time()
        warnings: list[str] = []

        if not self._mc.enabled:
            logger.warning("MC disabled in config — returning empty PhaseThreeResult.")
            return self._empty_result(scenario.id, time.time() - t0)

        fire_target = extra_fire_target or self._mc.fire_target_net_worth
        if fire_target == 0.0 and scenario.fire_target:
            fire_target = scenario.fire_target.target_net_worth

        logger.info(
            "run_scenario: '%s' n_sims=%d fire_target=%.0f",
            scenario.id, self._mc.n_simulations, fire_target,
        )

        # Stochastic simulation
        band, sim_warnings = self._run_stochastic(scenario, colour, fire_target)
        warnings.extend(sim_warnings)

        # Macro scenario bands (deterministic low/mid/high)
        macro_bands = self._run_macro_scenarios(scenario)

        # Surplus/shortfall analysis
        ssa: Optional[SurplusShortfallResult] = None
        if self._mc.drawdown_annual_target > 0:
            ssa = self._surplus_shortfall(scenario, fire_target)

        runtime = time.time() - t0
        logger.info(
            "run_scenario '%s' complete: %.1fs fire_prob=%.1f%%",
            scenario.id, runtime, band.fire_probability * 100,
        )

        return PhaseThreeResult(
            scenario_id=scenario.id,
            confidence_band=band,
            macro_bands=macro_bands,
            surplus_shortfall=ssa,
            total_simulations=self._mc.n_simulations,
            runtime_seconds=runtime,
            warnings=warnings,
        )

    def compare_scenarios(
        self,
        scenarios: list[Scenario],
        colours: Optional[list[str]] = None,
        key_years: Optional[list[int]] = None,
    ) -> ScenarioComparison:
        """
        @brief Run MC for up to 4 scenarios and return a comparison.

        Each scenario gets an independent confidence band (same MC config).
        The comparison includes a side-by-side at key calendar years and
        identifies the FIRE crossover year per scenario.

        @param scenarios   List of 1–4 Scenario objects.
        @param colours     Optional list of hex colours (falls back to defaults).
        @param key_years   Calendar years to snapshot for comparison table.
                           Defaults to every 5 years in the projection range.
        @return            ScenarioComparison.
        @raises ValueError If more than 4 scenarios are supplied.
        """
        if len(scenarios) > 4:
            raise ValueError(
                f"compare_scenarios accepts at most 4 scenarios; {len(scenarios)} supplied."
            )

        default_colours = ["#58a6ff", "#f0a500", "#bc8cff", "#3fb950"]
        colours = colours or default_colours

        bands: list[ConfidenceBand] = []
        for i, sc in enumerate(scenarios):
            col = colours[i] if i < len(colours) else default_colours[i % 4]
            logger.info("compare_scenarios: running '%s'", sc.id)
            band, _ = self._run_stochastic(sc, col, self._mc.fire_target_net_worth)
            bands.append(band)

        # Common year range
        all_year_sets = [set(b.years) for b in bands]
        common_years = sorted(set.intersection(*all_year_sets)) if all_year_sets else []

        # Key years snapshot
        if key_years is None:
            key_years = [y for y in common_years if (y - common_years[0]) % 5 == 0] if common_years else []

        at_key_ages: dict[int, dict[str, float]] = {}
        for ky in key_years:
            at_key_ages[ky] = {}
            for b in bands:
                if ky in b.years:
                    idx = b.years.index(ky)
                    at_key_ages[ky][b.scenario_id] = round(b.median[idx], 0)

        # FIRE crossover years
        fire_crossover: dict[str, Optional[int]] = {}
        fire_target = self._mc.fire_target_net_worth
        for b in bands:
            crossed = None
            for i, (yr, val) in enumerate(zip(b.years, b.median)):
                if fire_target > 0 and val >= fire_target:
                    crossed = yr
                    break
            fire_crossover[b.scenario_id] = crossed

        logger.info(
            "compare_scenarios: %d scenarios compared, %d common years",
            len(scenarios), len(common_years),
        )

        return ScenarioComparison(
            bands=bands,
            comparison_years=common_years,
            at_key_ages=at_key_ages,
            fire_crossover=fire_crossover,
        )

    # ------------------------------------------------------------------
    # Private — stochastic simulation
    # ------------------------------------------------------------------

    def _run_stochastic(
        self,
        scenario: Scenario,
        colour: str,
        fire_target: float,
    ) -> tuple[ConfidenceBand, list[str]]:
        """
        @brief Run the stochastic MC simulation and extract confidence bands.

        Each simulation perturbs growth rates and inflation independently.
        The sequence-of-returns crash is injected if configured.

        @param scenario     Scenario to simulate.
        @param colour       Hex colour for this band.
        @param fire_target  Net worth threshold for FIRE counting.
        @return             Tuple of (ConfidenceBand, warnings).
        """
        warnings_out: list[str] = []
        rng = np.random.default_rng(self._mc.seed)

        years_list = list(range(
            self._app.projection_start_year,
            self._app.projection_end_year + 1,
        ))
        n_years = len(years_list)
        n_sims = self._mc.n_simulations

        all_net_worths = np.zeros((n_sims, n_years), dtype=np.float64)
        fire_achieved_count = np.zeros(n_years, dtype=np.int32)

        try:
            engine = ProjectionEngine(scenario, self._app, self._tax)
        except Exception as exc:
            logger.error("_run_stochastic: failed to create ProjectionEngine: %s", exc)
            warnings_out.append(f"Projection engine error: {exc}")
            return self._empty_band(scenario, colour, years_list), warnings_out

        for sim_idx in range(n_sims):
            if sim_idx % self._mc.log_every_n == 0 and sim_idx > 0:
                logger.debug("MC simulation %d/%d", sim_idx, n_sims)

            try:
                growth_noise = float(rng.normal(0, self._mc.growth_std))
                inflation_noise = float(rng.normal(0, self._mc.inflation_std))
                salary_noise = float(rng.normal(0, self._mc.salary_growth_std))

                sim_config = self._make_sim_config(
                    inflation_noise, growth_noise, salary_noise
                )

                sim_engine = ProjectionEngine(scenario, sim_config, self._tax)

                # Determine retirement year for SoR injection
                retire_year = self._app.projection_end_year
                for person in scenario.people:
                    if hasattr(person, "target_retire_age") and person.dob:
                        retire_year = min(
                            retire_year,
                            person.dob.year + getattr(person, "target_retire_age", 67),
                        )

                timeline = sim_engine.run()
                net_worths = self._extract_net_worths(timeline, years_list)

                # Inject sequence-of-returns crash if configured
                if self._mc.sequence_of_returns.enabled:
                    net_worths = self._apply_sor_shock(
                        net_worths, years_list, retire_year, rng
                    )

                all_net_worths[sim_idx] = net_worths

                # Track FIRE achievement
                if fire_target > 0:
                    fire_achieved = np.cummax_workaround(net_worths >= fire_target)
                    fire_achieved_count += fire_achieved.astype(np.int32)

            except Exception as exc:
                logger.warning("MC sim %d failed: %s — using zeros", sim_idx, exc)
                # Leave as zeros

        # Extract percentiles
        percentile_bands: dict[int, list[float]] = {}
        for p in self._mc.percentiles:
            pct_values = np.percentile(all_net_worths, p, axis=0)
            percentile_bands[p] = [round(float(v), 2) for v in pct_values]

        median = percentile_bands.get(50, [0.0] * n_years)

        # FIRE probability
        fire_prob_by_year: dict[int, float] = {}
        fire_overall = 0.0
        if fire_target > 0 and n_sims > 0:
            for i, yr in enumerate(years_list):
                fire_prob_by_year[yr] = round(float(fire_achieved_count[i]) / n_sims, 4)
            fire_overall = fire_prob_by_year.get(years_list[-1], 0.0)

        logger.info(
            "_run_stochastic '%s': complete, fire_prob=%.1f%%",
            scenario.id, fire_overall * 100,
        )

        return ConfidenceBand(
            scenario_id=scenario.id,
            scenario_label=scenario.name,
            scenario_colour=colour,
            years=years_list,
            percentile_bands=percentile_bands,
            median=median,
            n_simulations=n_sims,
            fire_probability=fire_overall,
            fire_prob_by_year=fire_prob_by_year,
            warnings=warnings_out,
        ), warnings_out

    def _apply_sor_shock(
        self,
        net_worths: np.ndarray,
        years_list: list[int],
        retire_year: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """
        @brief Inject a sequence-of-returns crash near the retirement start.

        Reduces net worth by the crash return for crash_duration_years, then
        applies a recovery excess for recovery_duration_years.  Each simulation
        gets a random offset within the crash window to avoid identical timing.

        @param net_worths   Array of net worths for one simulation.
        @param years_list   Calendar years corresponding to net_worths.
        @param retire_year  First year of retirement.
        @param rng          Numpy RNG.
        @return             Modified net_worths array.
        """
        sor = self._mc.sequence_of_returns
        if not sor.enabled:
            return net_worths

        crash_year = retire_year + sor.crash_start_offset_years
        if crash_year not in years_list:
            return net_worths

        crash_idx = years_list.index(crash_year)
        result = net_worths.copy()

        # Apply crash
        for offset in range(sor.crash_duration_years):
            ci = crash_idx + offset
            if ci < len(result):
                result[ci] = result[ci] * (1 + sor.crash_annual_return)

        # Apply recovery excess
        for offset in range(sor.recovery_duration_years):
            ri = crash_idx + sor.crash_duration_years + offset
            if ri < len(result):
                result[ri] = result[ri] * (1 + sor.recovery_excess_return)

        return result

    # ------------------------------------------------------------------
    # Private — macro scenario bands (deterministic)
    # ------------------------------------------------------------------

    def _run_macro_scenarios(
        self, scenario: Scenario
    ) -> list[MacroScenarioBand]:
        """
        @brief Run deterministic projections for each macro scenario (low/mid/high).

        These are single runs with specific parameter sets — not stochastic.
        They provide the fan chart band structure alongside the MC percentiles.

        @param scenario  Base scenario to project.
        @return          List of MacroScenarioBand.
        """
        bands: list[MacroScenarioBand] = []
        years_list = list(range(
            self._app.projection_start_year,
            self._app.projection_end_year + 1,
        ))

        for params in self._mc.macro_scenarios:
            try:
                sim_config = self._make_macro_config(params)
                eng = ProjectionEngine(scenario, sim_config, self._tax)
                timeline = eng.run()
                net_worths = self._extract_net_worths(timeline, years_list)

                fire_year: Optional[int] = timeline.fire_year

                bands.append(MacroScenarioBand(
                    label=params.label,
                    colour=params.colour,
                    years=years_list,
                    net_worths=[round(float(v), 2) for v in net_worths],
                    fire_year=fire_year,
                    params=params,
                ))
                logger.debug(
                    "Macro scenario '%s': fire_year=%s terminal_nw=%.0f",
                    params.label, fire_year, net_worths[-1] if len(net_worths) else 0,
                )
            except Exception as exc:
                logger.error(
                    "Macro scenario '%s' failed: %s", params.label, exc, exc_info=True
                )

        return bands

    # ------------------------------------------------------------------
    # Private — surplus / shortfall
    # ------------------------------------------------------------------

    def _surplus_shortfall(
        self,
        scenario: Scenario,
        fire_target: float,
    ) -> SurplusShortfallResult:
        """
        @brief Compute year-by-year surplus/shortfall probability.

        A surplus exists in a year if the median portfolio exceeds the
        cumulative present value of the remaining drawdown target.

        @param scenario     Source scenario.
        @param fire_target  FIRE target net worth (used for scaling).
        @return             SurplusShortfallResult.
        """
        target = self._mc.drawdown_annual_target
        years_list = list(range(
            self._app.projection_start_year,
            self._app.projection_end_year + 1,
        ))

        try:
            eng = ProjectionEngine(scenario, self._app, self._tax)
            timeline = eng.run()
            net_worths = self._extract_net_worths(timeline, years_list)
        except Exception as exc:
            logger.error("_surplus_shortfall: projection failed: %s", exc)
            return SurplusShortfallResult(
                years=years_list,
                prob_surplus=[0.0] * len(years_list),
                expected_surplus=[0.0] * len(years_list),
                shortfall_years=[],
                worst_case_shortfall=0.0,
            )

        surpluses = [float(nw) - target for nw in net_worths]
        shortfall_years = [yr for yr, s in zip(years_list, surpluses) if s < 0]
        worst = min(surpluses) if surpluses else 0.0

        # Probability modelled as 1.0 when surplus positive, 0.0 when not
        # (deterministic single run — MC version would aggregate across simulations)
        prob = [1.0 if s >= 0 else 0.0 for s in surpluses]

        return SurplusShortfallResult(
            years=years_list,
            prob_surplus=prob,
            expected_surplus=[round(s, 2) for s in surpluses],
            shortfall_years=shortfall_years,
            worst_case_shortfall=round(worst, 2),
        )

    # ------------------------------------------------------------------
    # Private — helpers
    # ------------------------------------------------------------------

    def _make_sim_config(
        self,
        inflation_noise: float,
        growth_noise: float,
        salary_noise: float,
    ) -> AppConfig:
        """
        @brief Create a perturbed AppConfig for one MC simulation.

        @param inflation_noise  Additive perturbation to inflation rate.
        @param growth_noise     Additive perturbation to growth rates
                                (not directly on AppConfig; used by engine internally).
        @param salary_noise     Additive perturbation to salary growth.
        @return                 Modified AppConfig.
        """
        base = self._app
        return AppConfig(
            base_currency=base.base_currency,
            log_level="WARNING",
            projection_start_year=base.projection_start_year,
            projection_end_year=base.projection_end_year,
            inflation_base_rate=max(0.0, base.inflation_base_rate + inflation_noise),
            monte_carlo_simulations=1,
            raw=base.raw,
        )

    def _make_macro_config(self, params: MacroScenarioParams) -> AppConfig:
        """
        @brief Create an AppConfig from a MacroScenarioParams set.

        @param params  MacroScenarioParams to use.
        @return        AppConfig with macro scenario values applied.
        """
        base = self._app
        return AppConfig(
            base_currency=base.base_currency,
            log_level="WARNING",
            projection_start_year=base.projection_start_year,
            projection_end_year=base.projection_end_year,
            inflation_base_rate=params.inflation_rate,
            monte_carlo_simulations=1,
            raw=base.raw,
        )

    def _extract_net_worths(
        self,
        timeline: TimelineResult,
        years_list: list[int],
    ) -> np.ndarray:
        """
        @brief Extract net worth series from a TimelineResult as a numpy array.

        @param timeline    TimelineResult from ProjectionEngine.run().
        @param years_list  Target calendar years.
        @return            Float64 array of net worths, 0.0 for missing years.
        """
        year_map = {snap.year: snap.total_net_worth for snap in timeline.years}
        return np.array(
            [year_map.get(yr, 0.0) for yr in years_list],
            dtype=np.float64,
        )

    def _validate_config(self) -> None:
        """
        @brief Validate MonteCarloConfig fields before running.

        @raises ValueError On critical misconfiguration.
        """
        mc = self._mc
        errors: list[str] = []
        if mc.n_simulations < 1:
            errors.append(f"n_simulations must be >= 1, got {mc.n_simulations}")
        if mc.growth_std < 0:
            errors.append(f"growth_std must be >= 0, got {mc.growth_std}")
        if mc.inflation_std < 0:
            errors.append(f"inflation_std must be >= 0, got {mc.inflation_std}")
        for p in mc.percentiles:
            if not (0 <= p <= 100):
                errors.append(f"Percentile {p} is outside [0, 100]")
        if errors:
            msg = "MonteCarloConfig validation failed: " + "; ".join(errors)
            logger.error(msg)
            raise ValueError(msg)

    def _empty_band(
        self,
        scenario: Scenario,
        colour: str,
        years_list: list[int],
    ) -> ConfidenceBand:
        """
        @brief Return an empty ConfidenceBand (used on engine init failure).

        @param scenario    Source scenario.
        @param colour      Hex colour.
        @param years_list  Calendar years.
        @return            Zero-filled ConfidenceBand.
        """
        zeros = [0.0] * len(years_list)
        return ConfidenceBand(
            scenario_id=scenario.id,
            scenario_label=scenario.name,
            scenario_colour=colour,
            years=years_list,
            percentile_bands={p: zeros[:] for p in self._mc.percentiles},
            median=zeros,
            n_simulations=0,
            fire_probability=0.0,
            fire_prob_by_year={yr: 0.0 for yr in years_list},
        )

    def _empty_result(self, scenario_id: str, runtime: float) -> PhaseThreeResult:
        """
        @brief Return an empty PhaseThreeResult (used when MC is disabled).

        @param scenario_id  Scenario identifier.
        @param runtime      Runtime in seconds.
        @return             Empty PhaseThreeResult.
        """
        years_list = list(range(
            self._app.projection_start_year,
            self._app.projection_end_year + 1,
        ))
        zeros = [0.0] * len(years_list)
        empty_band = ConfidenceBand(
            scenario_id=scenario_id,
            scenario_label=scenario_id,
            scenario_colour="#8b949e",
            years=years_list,
            percentile_bands={p: zeros[:] for p in self._mc.percentiles},
            median=zeros,
            n_simulations=0,
            fire_probability=0.0,
            fire_prob_by_year={yr: 0.0 for yr in years_list},
        )
        return PhaseThreeResult(
            scenario_id=scenario_id,
            confidence_band=empty_band,
            macro_bands=[],
            surplus_shortfall=None,
            total_simulations=0,
            runtime_seconds=runtime,
            warnings=["Monte Carlo disabled in config."],
        )


# ---------------------------------------------------------------------------
# Cumulative-max workaround (numpy doesn't have cummax natively)
# ---------------------------------------------------------------------------


def _cummax_workaround(arr: np.ndarray) -> np.ndarray:
    """
    @brief Return cumulative maximum of a boolean array.

    Once True, stays True — used to track 'FIRE ever achieved by year Y'.

    @param arr  1D boolean numpy array.
    @return     1D boolean numpy array with cumulative max applied.
    """
    result = np.zeros_like(arr, dtype=bool)
    seen_true = False
    for i, v in enumerate(arr):
        if v:
            seen_true = True
        result[i] = seen_true
    return result


# Monkey-patch onto np namespace for use in stochastic loop
np.cummax_workaround = _cummax_workaround


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def load_monte_carlo_config(path: str) -> MonteCarloConfig:
    """
    @brief Load a MonteCarloConfig from a YAML file.

    Expected top-level key: ``monte_carlo``.

    @param path  Filesystem path to the YAML config file.
    @return      Populated MonteCarloConfig.
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file is not valid YAML.
    @raises ValueError         If the structure is wrong.
    """
    logger.info("Loading Monte Carlo config from: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Monte Carlo config not found: %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise

    if not isinstance(raw, dict) or "monte_carlo" not in raw:
        raise ValueError(f"YAML '{path}' must have a top-level 'monte_carlo' key.")

    mc = raw["monte_carlo"]

    # Macro scenarios
    macro_scenarios: list[MacroScenarioParams] = []
    for item in mc.get("macro_scenarios", []):
        macro_scenarios.append(MacroScenarioParams(
            label=str(item.get("label", "?")),
            inflation_rate=float(item.get("inflation_rate", 0.025)),
            equity_real_return=float(item.get("equity_real_return", 0.05)),
            bond_real_return=float(item.get("bond_real_return", 0.01)),
            cash_real_return=float(item.get("cash_real_return", 0.0)),
            property_growth_real=float(item.get("property_growth_real", 0.01)),
            salary_real_growth=float(item.get("salary_real_growth", 0.01)),
            uk_house_price_growth=float(item.get("uk_house_price_growth", 0.03)),
            us_house_price_growth=float(item.get("us_house_price_growth", 0.04)),
            fx_gbpusd=float(item.get("fx_gbpusd", 1.27)),
            colour=str(item.get("colour", "#8b949e")),
            notes=str(item.get("notes", "")),
        ))

    # Sequence-of-returns
    sor_raw = mc.get("sequence_of_returns", {}) or {}
    sor = SequenceOfReturnsConfig(
        enabled=bool(sor_raw.get("enabled", True)),
        crash_start_offset_years=int(sor_raw.get("crash_start_offset_years", 1)),
        crash_duration_years=int(sor_raw.get("crash_duration_years", 2)),
        crash_annual_return=float(sor_raw.get("crash_annual_return", -0.20)),
        recovery_excess_return=float(sor_raw.get("recovery_excess_return", 0.05)),
        recovery_duration_years=int(sor_raw.get("recovery_duration_years", 3)),
        notes=str(sor_raw.get("notes", "")),
    )

    config = MonteCarloConfig(
        n_simulations=int(mc.get("n_simulations", 1000)),
        seed=int(mc["seed"]) if mc.get("seed") is not None else None,
        growth_std=float(mc.get("growth_std", 0.10)),
        inflation_std=float(mc.get("inflation_std", 0.005)),
        salary_growth_std=float(mc.get("salary_growth_std", 0.005)),
        percentiles=list(mc.get("percentiles", [5, 10, 25, 50, 75, 90, 95])),
        macro_scenarios=macro_scenarios,
        sequence_of_returns=sor,
        fire_target_net_worth=float(mc.get("fire_target_net_worth", 0.0)),
        drawdown_annual_target=float(mc.get("drawdown_annual_target", 0.0)),
        max_workers=int(mc.get("max_workers", 0)),
        log_every_n=int(mc.get("log_every_n", 100)),
        enabled=bool(mc.get("enabled", True)),
        notes=str(mc.get("notes", "")),
    )

    logger.info(
        "MC config loaded: n_sims=%d macro_scenarios=%d SoR=%s",
        config.n_simulations, len(macro_scenarios), sor.enabled,
    )
    return config
