"""
@file retirement_engine.py
@brief Retirement planning engine for LifeLedger Phase 4.

Provides five analysis modules that together constitute a comprehensive
retirement health dashboard:

  1. **Income Coverage** — Year-by-year comparison of projected retirement
     income (pension drawdown, annuities, state pension, rental, part-time)
     against inflation-adjusted expenses. Returns a coverage ratio and
     surplus/shortfall per year, with red/amber/green status flags.

  2. **Drawdown Order Optimisation** — Compares ISA-first, SIPP-first,
     GIA-first, and optimised drawdown strategies.  Calculates the lifetime
     income tax saving between strategies and recommends the most tax-efficient
     order for a given income profile.

  3. **Annuity vs Drawdown Comparison** — For any pension pot, computes
     level, inflation-linked, and joint-life annuity income streams and
     compares them to a 4 % SWR drawdown.  Finds the break-even age and
     lifetime income at key ages.

  4. **State Pension Tracker** — Projects NI qualifying year accumulation,
     identifies gaps, costs voluntary Class 3 top-ups, calculates their ROI,
     and models deferral bonuses.

  5. **Emergency Fund Monitor** — Sums accessible liquid cash across savings
     accounts, computes months of expenses covered, and recommends a top-up
     if below the configured threshold.

All methods accept a ``Scenario`` and optionally a ``TimelineResult``
(already computed projection) to avoid redundant re-calculation.

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import yaml

from backend.models.models import (
    AccountType, DrawdownMode, PensionType,
    Scenario, StatePension, TaxTreatment,
)
from backend.engine.calculator import TimelineResult, YearSnapshot

logger = logging.getLogger("lifeledger.retirement")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RetirementConfig:
    """
    @brief Configuration for the retirement engine.

    @param default_drawdown_order     Default strategy: 'isa_first' | 'sipp_first'
                                      | 'gia_first' | 'optimised'.
    @param annuity_rate_level         Annual income per £100,000 converted — level
                                      (e.g. 5200 = £5,200/yr per £100k → 5.2%).
    @param annuity_rate_inflation     Annual income per £100k — inflation-linked.
    @param annuity_rate_joint_life    Annual income per £100k — joint life (50%).
    @param annuity_inflation_rate     Annual escalation on inflation-linked annuity.
    @param annuity_joint_survivor_pct Fraction paid to surviving partner.
    @param annuity_guarantee_years    Guarantee period (pays estate on early death).
    @param drawdown_swr               Safe withdrawal rate as a decimal.
    @param income_coverage_target     Coverage ratio below which a shortfall is
                                      flagged (1.0 = expenses fully covered).
    @param income_coverage_amber      Coverage ratio at which amber warning fires.
    @param triple_lock_rate           Annual uprating for state pension (triple lock).
    @param ni_class3_weekly_rate      Cost per week of voluntary Class 3 NI top-up.
    @param ni_full_qualifying_years   NI years needed for full state pension.
    @param state_pension_weekly_full  Full new State Pension weekly amount (2024/25).
    @param deferral_bonus_per_week    Weekly increase per week of deferral (1/9 %).
    @param emergency_fund_target_months  Target months of expenses in liquid cash.
    @param emergency_fund_amber_months   Amber warning threshold.
    @param liquid_account_types       Account types counted as liquid emergency fund.
    @param retirement_income_tax_treatments  Tax treatments counted as retirement income.
    @param isa_annual_drawdown_tax_rate  Tax rate on ISA drawdown (0 = tax-free).
    @param basic_rate_band_limit      Income tax basic rate upper limit.
    @param basic_rate                 Basic income tax rate.
    @param higher_rate                Higher income tax rate.
    @param personal_allowance         Income tax personal allowance.
    @param enabled                    False to skip retirement engine entirely.
    @param notes                      Free-text notes.
    """

    default_drawdown_order: str = "isa_first"
    annuity_rate_level: float = 5200.0
    annuity_rate_inflation: float = 4200.0
    annuity_rate_joint_life: float = 4600.0
    annuity_inflation_rate: float = 0.025
    annuity_joint_survivor_pct: float = 0.50
    annuity_guarantee_years: int = 5
    drawdown_swr: float = 0.04
    income_coverage_target: float = 1.0
    income_coverage_amber: float = 0.80
    triple_lock_rate: float = 0.025
    ni_class3_weekly_rate: float = 17.45
    ni_full_qualifying_years: int = 35
    state_pension_weekly_full: float = 221.20
    deferral_bonus_per_week: float = 1.0 / 9.0 / 100.0
    emergency_fund_target_months: float = 6.0
    emergency_fund_amber_months: float = 3.0
    liquid_account_types: list[str] = field(default_factory=lambda: [
        "ISA", "cash_ISA", "LISA", "general"
    ])
    retirement_income_tax_treatments: list[str] = field(default_factory=lambda: [
        "pension_drawdown", "state_pension", "rental", "other"
    ])
    isa_annual_drawdown_tax_rate: float = 0.0
    basic_rate_band_limit: float = 50270.0
    basic_rate: float = 0.20
    higher_rate: float = 0.40
    personal_allowance: float = 12570.0
    enabled: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# 1. Income Coverage
# ---------------------------------------------------------------------------


@dataclass
class IncomeSource:
    """
    @brief One retirement income source in a specific year.

    @param label         Display label.
    @param source_type   'pension_drawdown' | 'state_pension' | 'annuity' |
                         'isa_withdrawal' | 'part_time' | 'rental' | 'other'.
    @param annual_gross  Gross annual amount.
    @param is_taxable    True if subject to income tax.
    @param person_id     FK to person.
    """

    label: str
    source_type: str
    annual_gross: float
    is_taxable: bool = True
    person_id: str = ""


@dataclass
class IncomeCoverageRow:
    """
    @brief One year of retirement income vs expenses analysis.

    @param year              Calendar year.
    @param total_income      Total gross retirement income.
    @param total_expenses    Total inflation-adjusted expenses.
    @param coverage_ratio    total_income / total_expenses (1.0 = fully covered).
    @param surplus_deficit   total_income - total_expenses (positive = surplus).
    @param income_breakdown  List of IncomeSource objects.
    @param status            'covered' | 'amber' | 'shortfall'.
    @param months_funded     How many months of expenses are covered.
    """

    year: int
    total_income: float
    total_expenses: float
    coverage_ratio: float
    surplus_deficit: float
    income_breakdown: list[IncomeSource]
    status: str
    months_funded: float


@dataclass
class IncomeCoverageReport:
    """
    @brief Full income coverage report across all retirement years.

    @param years                 List of IncomeCoverageRow.
    @param first_shortfall_year  First year where status == 'shortfall' (None if never).
    @param worst_coverage_year   Year with lowest coverage_ratio.
    @param worst_coverage_ratio  Lowest coverage_ratio seen.
    @param avg_coverage_ratio    Average coverage ratio across all years.
    @param total_surplus         Cumulative surplus over the period.
    @param total_shortfall       Cumulative shortfall over the period (positive number).
    @param warnings              Warning strings.
    """

    years: list[IncomeCoverageRow]
    first_shortfall_year: Optional[int]
    worst_coverage_year: int
    worst_coverage_ratio: float
    avg_coverage_ratio: float
    total_surplus: float
    total_shortfall: float
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. Drawdown Order Optimisation
# ---------------------------------------------------------------------------


DRAWDOWN_STRATEGIES = {
    "isa_first":  ["ISA", "cash_ISA", "LISA", "GIA", "SIPP", "pension"],
    "sipp_first": ["SIPP", "pension", "GIA", "ISA", "cash_ISA", "LISA"],
    "gia_first":  ["GIA", "ISA", "cash_ISA", "LISA", "SIPP", "pension"],
    "optimised":  ["ISA", "cash_ISA", "LISA", "GIA", "SIPP", "pension"],
}


@dataclass
class DrawdownYearRow:
    """
    @brief One year of drawdown order comparison.

    @param year          Calendar year.
    @param income_needed Target income needed from investments.
    @param strategy_a_tax  Income tax under strategy A.
    @param strategy_b_tax  Income tax under strategy B.
    @param tax_saving      strategy_b_tax - strategy_a_tax (positive = A better).
    """

    year: int
    income_needed: float
    strategy_a_tax: float
    strategy_b_tax: float
    tax_saving: float


@dataclass
class DrawdownOrderResult:
    """
    @brief Comparison of two drawdown strategies.

    @param strategy_a_id         Strategy A identifier.
    @param strategy_a_label      Strategy A display label.
    @param strategy_b_id         Strategy B identifier.
    @param strategy_b_label      Strategy B display label.
    @param year_rows             Per-year comparison.
    @param lifetime_tax_a        Total income tax under strategy A.
    @param lifetime_tax_b        Total income tax under strategy B.
    @param lifetime_tax_saving   Tax saved by choosing A over B (A - B).
    @param recommended_strategy  ID of the recommended strategy.
    @param recommendation_notes  Explanation of the recommendation.
    @param warnings              Warning strings.
    """

    strategy_a_id: str
    strategy_a_label: str
    strategy_b_id: str
    strategy_b_label: str
    year_rows: list[DrawdownYearRow]
    lifetime_tax_a: float
    lifetime_tax_b: float
    lifetime_tax_saving: float
    recommended_strategy: str
    recommendation_notes: str
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 3. Annuity vs Drawdown
# ---------------------------------------------------------------------------


@dataclass
class AnnuityOption:
    """
    @brief One annuity quote.

    @param annuity_type       'level' | 'inflation_linked' | 'joint_life'.
    @param label              Display label.
    @param fund_at_conversion Fund value at the point of conversion.
    @param annual_income_yr1  Annual income in year 1.
    @param inflation_rate     Annual income escalation (0 for level).
    @param survivor_fraction  Survivor income fraction (0 for non-joint).
    @param guarantee_years    Guarantee period.
    @param income_at_ages     Dict mapping age -> cumulative income to that age.
    @param break_even_age     Age at which cumulative annuity > cumulative drawdown.
    """

    annuity_type: str
    label: str
    fund_at_conversion: float
    annual_income_yr1: float
    inflation_rate: float
    survivor_fraction: float
    guarantee_years: int
    income_at_ages: dict[int, float]
    break_even_age: Optional[int]


@dataclass
class DrawdownProjection:
    """
    @brief Drawdown income projection at a fixed SWR.

    @param swr              Safe withdrawal rate (e.g. 0.04 = 4%).
    @param fund_at_start    Fund value at drawdown start.
    @param income_yr1       Year-1 income (fund * SWR).
    @param income_at_ages   Dict mapping age -> cumulative income to that age.
    @param exhaustion_age   Age at which fund reaches zero (None if never).
    """

    swr: float
    fund_at_start: float
    income_yr1: float
    income_at_ages: dict[int, float]
    exhaustion_age: Optional[int]


@dataclass
class AnnuityVsDrawdownResult:
    """
    @brief Full annuity vs drawdown comparison for a pension pot.

    @param pension_id        Pension fund identifier.
    @param conversion_age    Age at conversion.
    @param fund_value        Estimated fund value at conversion.
    @param drawdown          DrawdownProjection.
    @param annuity_level     Level annuity option.
    @param annuity_inflation Inflation-linked annuity option.
    @param annuity_joint     Joint-life annuity option.
    @param notes             Contextual notes.
    """

    pension_id: str
    conversion_age: int
    fund_value: float
    drawdown: DrawdownProjection
    annuity_level: AnnuityOption
    annuity_inflation: AnnuityOption
    annuity_joint: AnnuityOption
    notes: str = ""


# ---------------------------------------------------------------------------
# 4. State Pension Tracker
# ---------------------------------------------------------------------------


@dataclass
class NiTopUpOption:
    """
    @brief One voluntary NI Class 3 top-up option.

    @param tax_year          Tax year the gap relates to (e.g. '2019/20').
    @param cost_gbp          One-off cost to fill the gap.
    @param weekly_pension_gain Weekly pension increase from filling this gap.
    @param annual_pension_gain Annual pension increase.
    @param years_to_recoup   Years to recover the top-up cost from increased pension.
    @param roi_10yr_pct      10-year return on investment as a percentage.
    """

    tax_year: str
    cost_gbp: float
    weekly_pension_gain: float
    annual_pension_gain: float
    years_to_recoup: float
    roi_10yr_pct: float


@dataclass
class DeferralOption:
    """
    @brief One state pension deferral scenario.

    @param claim_age                  Age at which pension is claimed.
    @param weeks_deferred             Weeks deferred from State Pension Age.
    @param annual_bonus_pct           Annual bonus applied.
    @param weekly_pension_with_bonus  Weekly pension including deferral uplift.
    @param annual_pension_with_bonus  Annual pension including deferral uplift.
    @param break_even_years           Years to recoup delayed claiming.
    """

    claim_age: int
    weeks_deferred: int
    annual_bonus_pct: float
    weekly_pension_with_bonus: float
    annual_pension_with_bonus: float
    break_even_years: float


@dataclass
class StatePensionProjection:
    """
    @brief State pension projection for one person.

    @param person_id             Person identifier.
    @param person_name           Display name.
    @param current_ni_years      NI qualifying years already accrued.
    @param ni_years_needed       Years needed for full pension.
    @param gap_years             Years short of full entitlement.
    @param projected_start_year  Year state pension begins.
    @param full_weekly_amount    Full state pension weekly amount.
    @param projected_weekly      Projected weekly amount based on current NI years.
    @param projected_annual      Projected annual amount.
    @param triple_lock_at_ages   Annual amounts after triple-lock uprating at key ages.
    @param top_up_options        List of voluntary top-up options.
    @param deferral_options      List of deferral scenarios.
    @param total_top_up_cost     Total cost to fill all gaps.
    @param max_pension_if_filled Full pension amount if all gaps filled.
    @param warnings              Warning strings.
    """

    person_id: str
    person_name: str
    current_ni_years: int
    ni_years_needed: int
    gap_years: int
    projected_start_year: int
    full_weekly_amount: float
    projected_weekly: float
    projected_annual: float
    triple_lock_at_ages: dict[int, float]
    top_up_options: list[NiTopUpOption]
    deferral_options: list[DeferralOption]
    total_top_up_cost: float
    max_pension_if_filled: float
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 5. Emergency Fund
# ---------------------------------------------------------------------------


@dataclass
class EmergencyFundStatus:
    """
    @brief Emergency fund health summary.

    @param total_liquid_cash     Sum of all liquid accessible cash accounts.
    @param monthly_expenses      Average monthly expenses (annual / 12).
    @param months_covered        total_liquid_cash / monthly_expenses.
    @param target_months         Configured target (default 6).
    @param amber_months          Configured amber threshold (default 3).
    @param status                'adequate' | 'amber' | 'critical'.
    @param recommended_top_up    Cash needed to reach target_months.
    @param liquid_accounts       Dict of account_id -> balance.
    @param warnings              Warning strings.
    """

    total_liquid_cash: float
    monthly_expenses: float
    months_covered: float
    target_months: float
    amber_months: float
    status: str
    recommended_top_up: float
    liquid_accounts: dict[str, float]
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Master result
# ---------------------------------------------------------------------------


@dataclass
class RetirementReport:
    """
    @brief Full Phase 4 retirement analysis report.

    @param scenario_id           Source scenario identifier.
    @param income_coverage       IncomeCoverageReport across all retirement years.
    @param drawdown_comparison   DrawdownOrderResult comparing default vs alternatives.
    @param annuity_comparisons   List of AnnuityVsDrawdownResult, one per pension pot.
    @param state_pension_projections  List of StatePensionProjection, one per person.
    @param emergency_fund        EmergencyFundStatus.
    @param retirement_start_year Earliest retirement year detected in the scenario.
    @param notes                 Free-text notes.
    @param warnings              Aggregated warnings from all sub-analyses.
    """

    scenario_id: str
    income_coverage: IncomeCoverageReport
    drawdown_comparison: DrawdownOrderResult
    annuity_comparisons: list[AnnuityVsDrawdownResult]
    state_pension_projections: list[StatePensionProjection]
    emergency_fund: EmergencyFundStatus
    retirement_start_year: int
    notes: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RetirementEngine:
    """
    @brief Phase 4 retirement planning engine.

    Consumes a ``Scenario`` (and optionally a pre-computed ``TimelineResult``)
    and produces a ``RetirementReport`` covering income coverage, drawdown
    order optimisation, annuity comparison, state pension tracking, and
    emergency fund monitoring.

    Usage::

        engine = RetirementEngine(config)
        report = engine.analyse(scenario, timeline_result)
    """

    def __init__(self, config: RetirementConfig) -> None:
        """
        @brief Initialise the engine with its configuration.

        @param config  RetirementConfig loaded from YAML.
        """
        self._cfg = config
        logger.info(
            "RetirementEngine initialised: drawdown_order=%s SWR=%.1f%% "
            "annuity_level=£%.0f/100k emergency_target=%.0fmo",
            config.default_drawdown_order,
            config.drawdown_swr * 100,
            config.annuity_rate_level,
            config.emergency_fund_target_months,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(
        self,
        scenario: Scenario,
        timeline: Optional[TimelineResult] = None,
    ) -> RetirementReport:
        """
        @brief Run all five retirement analyses and return a full report.

        @param scenario   The Scenario to analyse.
        @param timeline   Optional pre-computed TimelineResult.  If None,
                          the coverage analysis uses scenario data directly.
        @return           RetirementReport.
        """
        if not self._cfg.enabled:
            logger.warning("RetirementEngine disabled in config.")
            return self._empty_report(scenario.id)

        logger.info("RetirementEngine.analyse: scenario='%s'", scenario.id)
        warnings: list[str] = []

        retire_year = self._retirement_start_year(scenario)
        logger.info("Detected retirement start year: %d", retire_year)

        coverage = self._income_coverage(scenario, timeline, retire_year)
        warnings.extend(coverage.warnings)

        drawdown_cmp = self._drawdown_order_comparison(
            scenario, retire_year,
            self._cfg.default_drawdown_order, "sipp_first",
        )
        warnings.extend(drawdown_cmp.warnings)

        annuity_cmps = self._annuity_comparisons(scenario, retire_year)

        sp_projections = self._state_pension_projections(scenario)
        for sp in sp_projections:
            warnings.extend(sp.warnings)

        ef = self._emergency_fund(scenario, timeline)
        warnings.extend(ef.warnings)

        logger.info(
            "RetirementEngine.analyse complete: coverage_avg=%.1f%% "
            "shortfalls=%d ef_status=%s",
            coverage.avg_coverage_ratio * 100,
            sum(1 for r in coverage.years if r.status == "shortfall"),
            ef.status,
        )

        return RetirementReport(
            scenario_id=scenario.id,
            income_coverage=coverage,
            drawdown_comparison=drawdown_cmp,
            annuity_comparisons=annuity_cmps,
            state_pension_projections=sp_projections,
            emergency_fund=ef,
            retirement_start_year=retire_year,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # 1. Income Coverage
    # ------------------------------------------------------------------

    def _income_coverage(
        self,
        scenario: Scenario,
        timeline: Optional[TimelineResult],
        retire_year: int,
    ) -> IncomeCoverageReport:
        """
        @brief Compute year-by-year retirement income coverage.

        Pulls retirement income from the timeline's IncomeSnapshot list
        (pension_drawdown, state_pension, rental, other) and compares to
        the scenario's active expense buckets each year.

        @param scenario     Source scenario.
        @param timeline     Pre-computed timeline (used for income/expenses).
        @param retire_year  First retirement year.
        @return             IncomeCoverageReport.
        """
        rows: list[IncomeCoverageRow] = []
        warnings: list[str] = []
        cfg = self._cfg

        retirement_tx = set(cfg.retirement_income_tax_treatments)

        # Determine projection years after retirement
        end_year = getattr(scenario, "_end_year", None)
        if timeline:
            years_to_check = [s.year for s in timeline.years if s.year >= retire_year]
        else:
            years_to_check = list(range(retire_year, retire_year + 40))

        for year in years_to_check:
            snap: Optional[YearSnapshot] = timeline.year(year) if timeline else None

            # Collect income sources
            income_sources: list[IncomeSource] = []
            total_income = 0.0

            if snap:
                for isrc in snap.income_sources:
                    tx = getattr(isrc, "tax_treatment", "")
                    if hasattr(isrc, "gross"):
                        gross = isrc.gross
                    else:
                        gross = getattr(isrc, "gross_annual", 0.0)
                    is_taxable = (tx not in ("ISA_withdrawal",))
                    src = IncomeSource(
                        label=getattr(isrc, "name", str(getattr(isrc, "source_id", ""))),
                        source_type=tx or "other",
                        annual_gross=round(float(gross), 2),
                        is_taxable=is_taxable,
                        person_id=getattr(isrc, "person_id", ""),
                    )
                    income_sources.append(src)
                    total_income += src.annual_gross
            else:
                # Fallback: sum retirement income sources from scenario directly
                for isrc in scenario.income_sources:
                    if not self._is_active(isrc, year):
                        continue
                    tx = getattr(isrc, "tax_treatment", None)
                    if tx and hasattr(tx, "value"):
                        tx = tx.value
                    if tx in retirement_tx:
                        gross = getattr(isrc, "gross_annual", 0.0)
                        src = IncomeSource(
                            label=getattr(isrc, "name", ""),
                            source_type=str(tx),
                            annual_gross=round(float(gross), 2),
                            is_taxable=(str(tx) != "state_pension"),
                            person_id=getattr(isrc, "person_id", ""),
                        )
                        income_sources.append(src)
                        total_income += gross

            # Expenses
            if snap:
                total_expenses = float(snap.total_expenses or 0.0)
            else:
                total_expenses = self._active_expenses(scenario, year)

            # Coverage metrics
            if total_expenses > 0:
                ratio = round(total_income / total_expenses, 4)
            else:
                ratio = 1.0
            surplus = round(total_income - total_expenses, 2)
            months = round((total_income / 12) / max(total_expenses / 12, 1), 2)

            if ratio >= cfg.income_coverage_target:
                status = "covered"
            elif ratio >= cfg.income_coverage_amber:
                status = "amber"
            else:
                status = "shortfall"

            rows.append(IncomeCoverageRow(
                year=year,
                total_income=round(total_income, 2),
                total_expenses=round(total_expenses, 2),
                coverage_ratio=ratio,
                surplus_deficit=surplus,
                income_breakdown=income_sources,
                status=status,
                months_funded=months,
            ))

        if not rows:
            warnings.append("No retirement years found in projection range.")
            return IncomeCoverageReport(
                years=[], first_shortfall_year=None,
                worst_coverage_year=retire_year, worst_coverage_ratio=0.0,
                avg_coverage_ratio=0.0, total_surplus=0.0, total_shortfall=0.0,
                warnings=warnings,
            )

        shortfall_years = [r.year for r in rows if r.status == "shortfall"]
        worst = min(rows, key=lambda r: r.coverage_ratio)
        avg = round(sum(r.coverage_ratio for r in rows) / len(rows), 4)
        total_surplus = round(sum(max(0.0, r.surplus_deficit) for r in rows), 2)
        total_shortfall = round(sum(abs(min(0.0, r.surplus_deficit)) for r in rows), 2)

        if shortfall_years:
            warnings.append(
                f"Income shortfall detected in {len(shortfall_years)} retirement year(s). "
                f"First: {shortfall_years[0]}. Consider increasing contributions, "
                f"deferring state pension, or reducing target expenses."
            )

        logger.info(
            "_income_coverage: %d years analysed, avg=%.1f%%, shortfalls=%d",
            len(rows), avg * 100, len(shortfall_years),
        )

        return IncomeCoverageReport(
            years=rows,
            first_shortfall_year=shortfall_years[0] if shortfall_years else None,
            worst_coverage_year=worst.year,
            worst_coverage_ratio=worst.coverage_ratio,
            avg_coverage_ratio=avg,
            total_surplus=total_surplus,
            total_shortfall=total_shortfall,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # 2. Drawdown Order Optimisation
    # ------------------------------------------------------------------

    def _drawdown_order_comparison(
        self,
        scenario: Scenario,
        retire_year: int,
        strategy_a_id: str,
        strategy_b_id: str,
    ) -> DrawdownOrderResult:
        """
        @brief Compare two drawdown strategies over a 20-year retirement window.

        Estimates income tax under each strategy by assuming the income needed
        from investments each year is £40,000 (configurable; uses scenario's
        fire_target annual_expenses_target if available) and computing the
        marginal tax on that income depending on whether it comes from a
        tax-free (ISA) or taxable (SIPP) source.

        @param scenario       Source scenario.
        @param retire_year    First retirement year.
        @param strategy_a_id  Primary strategy ID.
        @param strategy_b_id  Comparison strategy ID.
        @return               DrawdownOrderResult.
        """
        warnings: list[str] = []
        cfg = self._cfg

        # Annual income needed from investments
        fire_target = getattr(scenario, "fire_target", None)
        if fire_target and getattr(fire_target, "annual_expenses_target", 0):
            income_needed = float(fire_target.annual_expenses_target)
        else:
            income_needed = 40_000.0

        # State pension offsets the amount needed from investments
        state_pension_annual = self._total_state_pension(scenario, retire_year)
        investment_income_needed = max(0.0, income_needed - state_pension_annual)

        year_rows: list[DrawdownYearRow] = []
        total_tax_a = 0.0
        total_tax_b = 0.0

        for offset in range(20):
            year = retire_year + offset
            # Inflate income needed slightly each year
            inf = (1 + cfg.annuity_inflation_rate) ** offset
            needed = round(investment_income_needed * inf, 2)

            tax_a = self._estimate_tax_for_strategy(
                strategy_a_id, needed, cfg
            )
            tax_b = self._estimate_tax_for_strategy(
                strategy_b_id, needed, cfg
            )
            total_tax_a += tax_a
            total_tax_b += tax_b

            year_rows.append(DrawdownYearRow(
                year=year,
                income_needed=needed,
                strategy_a_tax=round(tax_a, 2),
                strategy_b_tax=round(tax_b, 2),
                tax_saving=round(tax_b - tax_a, 2),
            ))

        lifetime_saving = round(total_tax_b - total_tax_a, 2)

        if lifetime_saving > 0:
            recommended = strategy_a_id
            notes = (
                f"'{strategy_a_id}' saves approximately £{lifetime_saving:,.0f} "
                f"in income tax over 20 years compared to '{strategy_b_id}'. "
                f"This is because ISA and other tax-free withdrawals avoid the "
                f"{cfg.basic_rate:.0%} basic-rate charge on SIPP income."
            )
        elif lifetime_saving < 0:
            recommended = strategy_b_id
            notes = (
                f"'{strategy_b_id}' saves approximately £{abs(lifetime_saving):,.0f} "
                f"over 20 years. Consider reviewing which accounts have the "
                f"largest balances and tax positions."
            )
        else:
            recommended = strategy_a_id
            notes = "Both strategies produce equivalent lifetime tax. Choose based on IHT position."

        if investment_income_needed < income_needed:
            notes += (
                f" Note: state pension of £{state_pension_annual:,.0f}/yr reduces "
                f"the amount needed from investments."
            )

        logger.info(
            "_drawdown_order_comparison: %s vs %s lifetime_saving=£%.0f recommended=%s",
            strategy_a_id, strategy_b_id, lifetime_saving, recommended,
        )

        return DrawdownOrderResult(
            strategy_a_id=strategy_a_id,
            strategy_a_label=strategy_a_id.replace("_", " ").title(),
            strategy_b_id=strategy_b_id,
            strategy_b_label=strategy_b_id.replace("_", " ").title(),
            year_rows=year_rows,
            lifetime_tax_a=round(total_tax_a, 2),
            lifetime_tax_b=round(total_tax_b, 2),
            lifetime_tax_saving=lifetime_saving,
            recommended_strategy=recommended,
            recommendation_notes=notes,
            warnings=warnings,
        )

    def _estimate_tax_for_strategy(
        self,
        strategy_id: str,
        income_needed: float,
        cfg: RetirementConfig,
    ) -> float:
        """
        @brief Estimate income tax for a given drawdown strategy and income level.

        ISA-first: income is tax-free → zero tax.
        SIPP-first: income is taxable above personal allowance.
        GIA-first: capital withdrawals not taxed; only growth element taxed.
        Optimised: same as ISA-first (fills tax-free first).

        @param strategy_id   Strategy identifier string.
        @param income_needed Annual investment income needed.
        @param cfg           RetirementConfig.
        @return              Estimated income tax payable.
        """
        if strategy_id in ("isa_first", "optimised"):
            # Assume ISA covers the full need — tax-free
            return 0.0
        elif strategy_id == "sipp_first":
            # SIPP income taxed above personal allowance at basic rate
            taxable = max(0.0, income_needed - cfg.personal_allowance)
            if taxable <= (cfg.basic_rate_band_limit - cfg.personal_allowance):
                return round(taxable * cfg.basic_rate, 2)
            else:
                basic = (cfg.basic_rate_band_limit - cfg.personal_allowance) * cfg.basic_rate
                higher = (taxable - (cfg.basic_rate_band_limit - cfg.personal_allowance)) * cfg.higher_rate
                return round(basic + higher, 2)
        elif strategy_id == "gia_first":
            # Assume 40% of GIA withdrawal is gain — CGT at 10% basic
            gain_fraction = 0.40
            gain = income_needed * gain_fraction
            cgt = gain * 0.10   # simplified — basic-rate CGT
            return round(cgt, 2)
        else:
            return 0.0

    # ------------------------------------------------------------------
    # 3. Annuity vs Drawdown
    # ------------------------------------------------------------------

    def _annuity_comparisons(
        self,
        scenario: Scenario,
        retire_year: int,
    ) -> list[AnnuityVsDrawdownResult]:
        """
        @brief Run annuity vs drawdown comparison for each SIPP/DC pension.

        @param scenario     Source scenario.
        @param retire_year  Retirement start year.
        @return             List of AnnuityVsDrawdownResult.
        """
        results: list[AnnuityVsDrawdownResult] = []
        cfg = self._cfg

        for pf in scenario.pension_funds:
            ptype = getattr(pf, "pension_type", None)
            if ptype and hasattr(ptype, "value"):
                ptype = ptype.value
            if ptype in ("DB", "STATE"):
                continue   # DB / state pensions not converted to annuity

            fund_now = float(getattr(pf, "current_value", 0))
            if fund_now <= 0:
                continue

            # Estimate fund at retirement using assumed growth rate
            growth = float(getattr(pf, "assumed_growth_rate", 0.05))
            current_year = date.today().year
            years_to_retire = max(0, retire_year - current_year)
            fund_at_retire = round(fund_now * (1 + growth) ** years_to_retire, 2)

            # Owner age at retirement
            owner_id = getattr(pf, "owner_id", getattr(pf, "person_id", ""))
            owner_age = self._person_age_at_year(scenario, owner_id, retire_year)

            # Drawdown projection (4% SWR, 30 years)
            drawdown = self._project_drawdown(fund_at_retire, owner_age, cfg)

            # Annuity options
            ann_level = self._compute_annuity(
                fund_at_retire, owner_age, "level",
                "Level Annuity", 0.0, 0.0, cfg, drawdown,
            )
            ann_inf = self._compute_annuity(
                fund_at_retire, owner_age, "inflation_linked",
                "Inflation-Linked Annuity", cfg.annuity_inflation_rate, 0.0, cfg, drawdown,
            )
            ann_jl = self._compute_annuity(
                fund_at_retire, owner_age, "joint_life",
                f"Joint Life ({cfg.annuity_joint_survivor_pct:.0%}) Annuity",
                0.0, cfg.annuity_joint_survivor_pct, cfg, drawdown,
            )

            results.append(AnnuityVsDrawdownResult(
                pension_id=getattr(pf, "id", "unknown"),
                conversion_age=owner_age,
                fund_value=fund_at_retire,
                drawdown=drawdown,
                annuity_level=ann_level,
                annuity_inflation=ann_inf,
                annuity_joint=ann_jl,
                notes=(
                    f"Fund projected from £{fund_now:,.0f} at {growth:.1%}/yr "
                    f"growth over {years_to_retire} years to £{fund_at_retire:,.0f}."
                ),
            ))
            logger.info(
                "_annuity_comparisons: pension_id=%s fund=£%.0f "
                "level_income=£%.0f/yr drawdown_income=£%.0f/yr",
                getattr(pf, "id", "?"), fund_at_retire,
                ann_level.annual_income_yr1, drawdown.income_yr1,
            )

        return results

    def _project_drawdown(
        self,
        fund: float,
        start_age: int,
        cfg: RetirementConfig,
    ) -> DrawdownProjection:
        """
        @brief Project a drawdown portfolio at a fixed SWR for 35 years.

        Models the fund growing at 4.5% and withdrawals at the SWR.  In each
        year the fund grows, then the withdrawal is taken.

        @param fund       Starting fund value.
        @param start_age  Age at drawdown start.
        @param cfg        RetirementConfig.
        @return           DrawdownProjection.
        """
        swr = cfg.drawdown_swr
        income_yr1 = round(fund * swr, 2)
        growth_rate = 0.045    # conservative nominal growth in drawdown

        balance = fund
        cum_income: dict[int, float] = {}
        cumulative = 0.0
        exhaustion_age: Optional[int] = None

        for yr in range(35):
            age = start_age + yr
            balance = balance * (1 + growth_rate)
            withdrawal = min(fund * swr, balance)  # SWR based on original fund
            balance = max(0.0, balance - withdrawal)
            cumulative += withdrawal
            cum_income[age] = round(cumulative, 2)
            if balance <= 0 and exhaustion_age is None:
                exhaustion_age = age

        return DrawdownProjection(
            swr=swr,
            fund_at_start=round(fund, 2),
            income_yr1=income_yr1,
            income_at_ages=cum_income,
            exhaustion_age=exhaustion_age,
        )

    def _compute_annuity(
        self,
        fund: float,
        start_age: int,
        annuity_type: str,
        label: str,
        inflation: float,
        survivor_fraction: float,
        cfg: RetirementConfig,
        drawdown: DrawdownProjection,
    ) -> AnnuityOption:
        """
        @brief Compute one annuity option and its break-even vs drawdown.

        @param fund              Fund at conversion.
        @param start_age         Age at conversion.
        @param annuity_type      'level' | 'inflation_linked' | 'joint_life'.
        @param label             Display label.
        @param inflation         Annual income escalation.
        @param survivor_fraction Survivor income fraction.
        @param cfg               RetirementConfig.
        @param drawdown          Pre-computed drawdown for break-even comparison.
        @return                  AnnuityOption.
        """
        rate_map = {
            "level":            cfg.annuity_rate_level,
            "inflation_linked": cfg.annuity_rate_inflation,
            "joint_life":       cfg.annuity_rate_joint_life,
        }
        rate_per_100k = rate_map.get(annuity_type, cfg.annuity_rate_level)
        income_yr1 = round(fund / 100_000 * rate_per_100k, 2)

        cum_income: dict[int, float] = {}
        cumulative = 0.0
        break_even_age: Optional[int] = None

        for yr in range(35):
            age = start_age + yr
            annual = income_yr1 * (1 + inflation) ** yr
            cumulative += annual
            cum_income[age] = round(cumulative, 2)

            # Check break-even against drawdown
            dd_cumulative = drawdown.income_at_ages.get(age, 0.0)
            if break_even_age is None and cumulative >= dd_cumulative and yr > 0:
                break_even_age = age

        return AnnuityOption(
            annuity_type=annuity_type,
            label=label,
            fund_at_conversion=round(fund, 2),
            annual_income_yr1=income_yr1,
            inflation_rate=inflation,
            survivor_fraction=survivor_fraction,
            guarantee_years=cfg.annuity_guarantee_years,
            income_at_ages=cum_income,
            break_even_age=break_even_age,
        )

    # ------------------------------------------------------------------
    # 4. State Pension Tracker
    # ------------------------------------------------------------------

    def _state_pension_projections(
        self, scenario: Scenario
    ) -> list[StatePensionProjection]:
        """
        @brief Generate state pension projections for all eligible people.

        @param scenario  Source scenario.
        @return          List of StatePensionProjection.
        """
        results: list[StatePensionProjection] = []
        cfg = self._cfg

        for person in scenario.people:
            sp: Optional[StatePension] = getattr(person, "state_pension", None)
            if sp is None or not getattr(sp, "eligible", True):
                continue

            name = getattr(person, "name", getattr(person, "id", "unknown"))
            person_id = getattr(person, "id", name)
            dob = getattr(person, "dob", None)
            current_year = date.today().year
            current_ni = int(getattr(sp, "qualifying_years", 0))
            full_years = int(getattr(sp, "full_qualifying_years", cfg.ni_full_qualifying_years))
            start_age = int(getattr(sp, "expected_start_age", 67))
            weekly_full = float(getattr(sp, "weekly_amount", cfg.state_pension_weekly_full))
            deferral_years = int(getattr(sp, "deferral_years", 0))

            gap_years = max(0, full_years - current_ni)

            # Projected start year
            if dob:
                birth_year = dob.year if hasattr(dob, "year") else int(str(dob)[:4])
                start_year = birth_year + start_age + deferral_years
            else:
                start_year = current_year + max(0, start_age - 45)

            # Proportional weekly amount based on current NI years
            proportion = min(current_ni / full_years, 1.0) if full_years > 0 else 1.0
            projected_weekly = round(weekly_full * proportion, 2)
            projected_annual = round(projected_weekly * 52, 2)

            # Triple-lock uprating at key ages
            years_to_start = max(0, start_year - current_year)
            tripled = projected_annual * (1 + cfg.triple_lock_rate) ** years_to_start
            triple_lock: dict[int, float] = {}
            for extra_years in [0, 5, 10, 15, 20]:
                age_key = start_age + extra_years
                triple_lock[age_key] = round(
                    tripled * (1 + cfg.triple_lock_rate) ** extra_years, 2
                )

            # Voluntary top-up options
            top_ups: list[NiTopUpOption] = []
            class3_annual = cfg.ni_class3_weekly_rate * 52
            gain_per_year = round(weekly_full / full_years, 4) if full_years > 0 else 0
            annual_gain = round(gain_per_year * 52, 2)
            years_to_recoup = (
                round(class3_annual / annual_gain, 1) if annual_gain > 0 else 99.0
            )
            roi_10yr = round(
                ((annual_gain * 10 - class3_annual) / class3_annual * 100), 1
            ) if class3_annual > 0 else 0.0

            for gap_idx in range(gap_years):
                tax_year = f"{current_year - gap_idx - 1}/{str(current_year - gap_idx)[-2:]}"
                top_ups.append(NiTopUpOption(
                    tax_year=tax_year,
                    cost_gbp=round(class3_annual, 2),
                    weekly_pension_gain=round(gain_per_year, 4),
                    annual_pension_gain=round(annual_gain, 2),
                    years_to_recoup=years_to_recoup,
                    roi_10yr_pct=roi_10yr,
                ))

            # Deferral options
            deferral_opts: list[DeferralOption] = []
            for defer_weeks in [0, 52, 104, 208]:
                claim_age = start_age + defer_weeks // 52
                bonus_pct = defer_weeks * cfg.deferral_bonus_per_week
                weekly_with_bonus = round(projected_weekly * (1 + bonus_pct), 2)
                annual_with_bonus = round(weekly_with_bonus * 52, 2)
                income_lost = projected_annual * (defer_weeks / 52)
                extra_per_year = annual_with_bonus - projected_annual
                break_even = round(income_lost / extra_per_year, 1) if extra_per_year > 0 else 99.0
                deferral_opts.append(DeferralOption(
                    claim_age=claim_age,
                    weeks_deferred=defer_weeks,
                    annual_bonus_pct=round(bonus_pct * 100, 2),
                    weekly_pension_with_bonus=weekly_with_bonus,
                    annual_pension_with_bonus=annual_with_bonus,
                    break_even_years=break_even,
                ))

            sp_warnings: list[str] = []
            if gap_years > 0:
                sp_warnings.append(
                    f"{name}: {gap_years} NI year gap(s). "
                    f"Total top-up cost: £{gap_years * class3_annual:,.0f}. "
                    f"ROI: {roi_10yr:.1f}% over 10 years."
                )

            results.append(StatePensionProjection(
                person_id=person_id,
                person_name=name,
                current_ni_years=current_ni,
                ni_years_needed=full_years,
                gap_years=gap_years,
                projected_start_year=start_year,
                full_weekly_amount=weekly_full,
                projected_weekly=projected_weekly,
                projected_annual=projected_annual,
                triple_lock_at_ages=triple_lock,
                top_up_options=top_ups,
                deferral_options=deferral_opts,
                total_top_up_cost=round(gap_years * class3_annual, 2),
                max_pension_if_filled=round(weekly_full * 52, 2),
                warnings=sp_warnings,
            ))
            logger.info(
                "_state_pension: person=%s NI=%d/%d projected_annual=£%.0f gap=%d",
                person_id, current_ni, full_years, projected_annual, gap_years,
            )

        return results

    # ------------------------------------------------------------------
    # 5. Emergency Fund
    # ------------------------------------------------------------------

    def _emergency_fund(
        self,
        scenario: Scenario,
        timeline: Optional[TimelineResult],
    ) -> EmergencyFundStatus:
        """
        @brief Compute emergency fund status from liquid account balances.

        @param scenario   Source scenario.
        @param timeline   Optional timeline (uses first-year account snapshots).
        @return           EmergencyFundStatus.
        """
        cfg = self._cfg
        warnings: list[str] = []
        liquid_accounts: dict[str, float] = {}

        # Collect liquid account balances
        if timeline and timeline.years:
            snap = timeline.years[0]
            for acc_id, acc_snap in snap.accounts.items():
                atype = str(getattr(acc_snap, "account_type", ""))
                if atype in cfg.liquid_account_types:
                    liquid_accounts[acc_id] = round(float(acc_snap.value), 2)
        else:
            # Fallback: scan savings accounts
            for acc in scenario.savings_accounts:
                atype = getattr(acc, "account_type", None)
                if atype and hasattr(atype, "value"):
                    atype = atype.value
                if str(atype) in cfg.liquid_account_types:
                    bal = float(getattr(acc, "current_balance", 0))
                    liquid_accounts[getattr(acc, "id", "?")] = bal

        total_liquid = round(sum(liquid_accounts.values()), 2)

        # Monthly expenses
        annual_expenses = sum(
            float(getattr(b, "annual_amount", 0))
            for b in scenario.expense_buckets
            if self._is_active(b, date.today().year)
        )
        monthly_expenses = round(annual_expenses / 12, 2)
        months_covered = (
            round(total_liquid / monthly_expenses, 1) if monthly_expenses > 0 else 99.0
        )

        if months_covered >= cfg.emergency_fund_target_months:
            status = "adequate"
        elif months_covered >= cfg.emergency_fund_amber_months:
            status = "amber"
        else:
            status = "critical"

        top_up_needed = max(0.0, (cfg.emergency_fund_target_months * monthly_expenses) - total_liquid)

        if status != "adequate":
            warnings.append(
                f"Emergency fund {status}: {months_covered:.1f} months covered "
                f"(target: {cfg.emergency_fund_target_months:.0f} months). "
                f"Recommended top-up: £{top_up_needed:,.0f}."
            )

        logger.info(
            "_emergency_fund: liquid=£%.0f monthly_exp=£%.0f months=%.1f status=%s",
            total_liquid, monthly_expenses, months_covered, status,
        )

        return EmergencyFundStatus(
            total_liquid_cash=total_liquid,
            monthly_expenses=monthly_expenses,
            months_covered=months_covered,
            target_months=cfg.emergency_fund_target_months,
            amber_months=cfg.emergency_fund_amber_months,
            status=status,
            recommended_top_up=round(top_up_needed, 2),
            liquid_accounts=liquid_accounts,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _retirement_start_year(self, scenario: Scenario) -> int:
        """
        @brief Find the earliest retirement year from income source end dates.

        Uses the end_date of PAYE income sources as a proxy for retirement.
        Falls back to current year + 20.

        @param scenario  Source scenario.
        @return          Calendar year of retirement.
        """
        current_year = date.today().year
        earliest = current_year + 20

        for isrc in scenario.income_sources:
            tx = getattr(isrc, "tax_treatment", None)
            if tx and hasattr(tx, "value"):
                tx = tx.value
            if tx in ("PAYE", "self_employed"):
                end = getattr(isrc, "end_date", None)
                if end:
                    year = end.year if hasattr(end, "year") else int(str(end)[:4])
                    earliest = min(earliest, year)

        return earliest

    def _total_state_pension(self, scenario: Scenario, year: int) -> float:
        """
        @brief Sum projected state pension for all people in a given year.

        @param scenario  Source scenario.
        @param year      Calendar year.
        @return          Total annual state pension income.
        """
        total = 0.0
        for person in scenario.people:
            sp = getattr(person, "state_pension", None)
            if not sp or not getattr(sp, "eligible", True):
                continue
            dob = getattr(person, "dob", None)
            if dob:
                birth_year = dob.year if hasattr(dob, "year") else int(str(dob)[:4])
                start_age = int(getattr(sp, "expected_start_age", 67))
                start_year = birth_year + start_age
            else:
                start_year = year   # assume already started
            if year >= start_year:
                total += float(sp.annual_amount() if callable(getattr(sp, "annual_amount", None)) else
                               getattr(sp, "weekly_amount", 221.20) * 52)
        return round(total, 2)

    def _person_age_at_year(
        self, scenario: Scenario, person_id: str, year: int
    ) -> int:
        """
        @brief Return a person's age at the end of a given year.

        @param scenario   Source scenario.
        @param person_id  Person identifier.
        @param year       Target calendar year.
        @return           Integer age (defaults to 60 if DOB unknown).
        """
        for person in scenario.people:
            if getattr(person, "id", None) == person_id:
                dob = getattr(person, "dob", None)
                if dob:
                    byr = dob.year if hasattr(dob, "year") else int(str(dob)[:4])
                    return year - byr
        return 60

    def _is_active(self, obj, year: int) -> bool:
        """
        @brief Check if an object with start_date/end_date is active in a year.

        @param obj   Any object with optional start_date and end_date.
        @param year  Calendar year to check.
        @return      True if active.
        """
        start = getattr(obj, "start_date", None)
        end = getattr(obj, "end_date", None)
        if start:
            syr = start.year if hasattr(start, "year") else int(str(start)[:4])
            if year < syr:
                return False
        if end:
            eyr = end.year if hasattr(end, "year") else int(str(end)[:4])
            if year > eyr:
                return False
        return True

    def _active_expenses(self, scenario: Scenario, year: int) -> float:
        """
        @brief Sum active expense buckets for a given year.

        @param scenario  Source scenario.
        @param year      Calendar year.
        @return          Total annual expenses.
        """
        total = 0.0
        for bucket in scenario.expense_buckets:
            if self._is_active(bucket, year):
                total += float(getattr(bucket, "annual_amount", 0))
        return total

    def _empty_report(self, scenario_id: str) -> RetirementReport:
        """
        @brief Return a minimal empty report (used when engine is disabled).

        @param scenario_id  Scenario identifier.
        @return             Empty RetirementReport.
        """
        empty_cov = IncomeCoverageReport(
            years=[], first_shortfall_year=None,
            worst_coverage_year=0, worst_coverage_ratio=0.0,
            avg_coverage_ratio=0.0, total_surplus=0.0, total_shortfall=0.0,
        )
        empty_dd = DrawdownOrderResult(
            strategy_a_id="isa_first", strategy_a_label="ISA First",
            strategy_b_id="sipp_first", strategy_b_label="SIPP First",
            year_rows=[], lifetime_tax_a=0.0, lifetime_tax_b=0.0,
            lifetime_tax_saving=0.0, recommended_strategy="isa_first",
            recommendation_notes="Engine disabled.",
        )
        empty_ef = EmergencyFundStatus(
            total_liquid_cash=0.0, monthly_expenses=0.0, months_covered=0.0,
            target_months=6.0, amber_months=3.0, status="critical",
            recommended_top_up=0.0, liquid_accounts={},
        )
        return RetirementReport(
            scenario_id=scenario_id,
            income_coverage=empty_cov,
            drawdown_comparison=empty_dd,
            annuity_comparisons=[],
            state_pension_projections=[],
            emergency_fund=empty_ef,
            retirement_start_year=0,
            warnings=["RetirementEngine disabled in config."],
        )


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def load_retirement_config(path: str) -> RetirementConfig:
    """
    @brief Load a RetirementConfig from a YAML file.

    Expected top-level key: ``retirement``.

    @param path  Filesystem path to the YAML config file.
    @return      Populated RetirementConfig.
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file is not valid YAML.
    """
    logger.info("Loading retirement config from: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Retirement config not found: %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise

    if not isinstance(raw, dict) or "retirement" not in raw:
        raise ValueError(f"YAML '{path}' must have a top-level 'retirement' key.")

    r = raw["retirement"]
    return RetirementConfig(
        default_drawdown_order=str(r.get("default_drawdown_order", "isa_first")),
        annuity_rate_level=float(r.get("annuity_rate_level", 5200.0)),
        annuity_rate_inflation=float(r.get("annuity_rate_inflation", 4200.0)),
        annuity_rate_joint_life=float(r.get("annuity_rate_joint_life", 4600.0)),
        annuity_inflation_rate=float(r.get("annuity_inflation_rate", 0.025)),
        annuity_joint_survivor_pct=float(r.get("annuity_joint_survivor_pct", 0.50)),
        annuity_guarantee_years=int(r.get("annuity_guarantee_years", 5)),
        drawdown_swr=float(r.get("drawdown_swr", 0.04)),
        income_coverage_target=float(r.get("income_coverage_target", 1.0)),
        income_coverage_amber=float(r.get("income_coverage_amber", 0.80)),
        triple_lock_rate=float(r.get("triple_lock_rate", 0.025)),
        ni_class3_weekly_rate=float(r.get("ni_class3_weekly_rate", 17.45)),
        ni_full_qualifying_years=int(r.get("ni_full_qualifying_years", 35)),
        state_pension_weekly_full=float(r.get("state_pension_weekly_full", 221.20)),
        deferral_bonus_per_week=float(r.get("deferral_bonus_per_week", 1.0 / 9.0 / 100.0)),
        emergency_fund_target_months=float(r.get("emergency_fund_target_months", 6.0)),
        emergency_fund_amber_months=float(r.get("emergency_fund_amber_months", 3.0)),
        liquid_account_types=list(r.get("liquid_account_types", ["ISA", "cash_ISA", "LISA", "general"])),
        retirement_income_tax_treatments=list(r.get("retirement_income_tax_treatments",
            ["pension_drawdown", "state_pension", "rental", "other"])),
        isa_annual_drawdown_tax_rate=float(r.get("isa_annual_drawdown_tax_rate", 0.0)),
        basic_rate_band_limit=float(r.get("basic_rate_band_limit", 50270.0)),
        basic_rate=float(r.get("basic_rate", 0.20)),
        higher_rate=float(r.get("higher_rate", 0.40)),
        personal_allowance=float(r.get("personal_allowance", 12570.0)),
        enabled=bool(r.get("enabled", True)),
        notes=str(r.get("notes", "")),
    )
