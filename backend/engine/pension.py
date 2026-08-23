"""
@file pension.py
@brief Pension calculation engine for LifeLedger.

Models the full lifecycle of a pension pot across three phases:

  1. **Accumulation** — contributions (employee + employer) compound at a
     configurable growth rate, respecting annual allowance limits and
     carry-forward relief.  Fee drag is applied annually.

  2. **Drawdown** — from the drawdown_start_date the pot declines as income
     is taken.  Supports three drawdown modes:
       - ``percentage``  — a fixed Safe Withdrawal Rate (SWR) applied to the
                           remaining fund each year.
       - ``fixed_amount`` — a constant annual income in nominal terms.
       - ``fixed_real``   — a constant annual income in real terms (inflated
                           each year to preserve purchasing power).
     The 25 % UK tax-free cash (PCLS) is applied in the first drawdown year.
     US Required Minimum Distributions (RMDs) are computed from age 73 per
     IRS Uniform Lifetime Table approximation.

  3. **Annuity** — the remaining fund (or a specified fraction) is converted
     to a guaranteed income stream on a given date.  Level, inflation-linked,
     and joint-life variants are supported.  The fund value drops to zero on
     conversion; the resulting income is reported as a separate series.

Produces both a year-by-year schedule and annual summaries for the projection
engine.  All monetary values are in the base currency defined by the config.

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

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("lifeledger.pension")


# ---------------------------------------------------------------------------
# Configuration dataclasses (mirror YAML schema)
# ---------------------------------------------------------------------------


@dataclass
class ContributionPeriod:
    """
    @brief One employee + employer contribution period.

    Contributions can change over time (e.g. salary increases, employer
    matching tier changes) by supplying multiple periods.

    @param label                  Human-readable label.
    @param start_date             First date this period applies.
    @param end_date               Last date this period applies, or None if
                                  open-ended until drawdown start.
    @param employee_annual        Employee gross annual contribution (£/$).
    @param employer_annual        Employer annual contribution (£/$).
                                  Set 0 if no employer scheme.
    @param employee_relief_rate   Income-tax relief rate applied to employee
                                  contributions at source (0.20 = basic rate).
                                  Used only for reporting; actual relief is
                                  applied by the tax engine.
    @param notes                  Free-text notes.
    """

    label: str
    start_date: date
    end_date: Optional[date]
    employee_annual: float
    employer_annual: float = 0.0
    employee_relief_rate: float = 0.20
    notes: str = ""


@dataclass
class GrowthPeriod:
    """
    @brief One assumed-growth-rate period for the pension fund.

    Allows the assumed return to change over time, e.g. a glide path from
    aggressive equities toward bonds as retirement approaches.

    @param label        Human-readable label.
    @param start_date   First year this rate applies.
    @param end_date     Last year this rate applies, or None (open-ended).
    @param annual_rate  Gross annual growth rate as a decimal (0.07 = 7 %).
    @param notes        Free-text notes.
    """

    label: str
    start_date: date
    end_date: Optional[date]
    annual_rate: float
    notes: str = ""


@dataclass
class DrawdownConfig:
    """
    @brief Configuration for the drawdown phase.

    @param mode                   'percentage' | 'fixed_amount' | 'fixed_real'.
    @param annual_drawdown_rate   SWR as a decimal (0.04 = 4 %).
                                  Used when mode == 'percentage'.
    @param annual_drawdown_amount Fixed annual income in nominal currency.
                                  Used when mode == 'fixed_amount' or
                                  'fixed_real'.
    @param inflation_rate         Annual inflation rate for real-terms
                                  uplifts (mode == 'fixed_real').
    @param apply_pcls             True to take the 25 % UK tax-free lump sum
                                  in the first drawdown year.
    @param pcls_fraction          Fraction of fund taken as PCLS (default 0.25).
                                  Some people take less than the maximum.
    @param drawdown_start_date    Date drawdown begins.
    @param drawdown_end_date      Date drawdown ends (e.g. conversion to
                                  annuity), or None to run until fund is
                                  exhausted or projection end.
    @param min_balance            Stop drawdown if fund falls below this value
                                  (safety floor, default 0).
    @param notes                  Free-text notes.
    """

    mode: str = "percentage"                     # 'percentage' | 'fixed_amount' | 'fixed_real'
    annual_drawdown_rate: float = 0.04           # SWR for 'percentage' mode
    annual_drawdown_amount: float = 0.0          # for 'fixed_amount' / 'fixed_real'
    inflation_rate: float = 0.025                # for 'fixed_real' uplifts
    apply_pcls: bool = True                      # UK 25% tax-free cash
    pcls_fraction: float = 0.25                  # fraction of fund taken as PCLS
    drawdown_start_date: Optional[date] = None
    drawdown_end_date: Optional[date] = None
    min_balance: float = 0.0
    notes: str = ""


@dataclass
class AnnuityConfig:
    """
    @brief Configuration for annuity conversion.

    @param enabled                True to model an annuity conversion.
    @param conversion_date        Date the fund (or fraction) is converted.
    @param conversion_fraction    Fraction of remaining fund converted (0–1).
                                  1.0 = full conversion.
    @param annuity_rate_per_100k  Annual income per £100,000 of fund converted
                                  (e.g. 5200 = £5,200/yr per £100k → 5.2 %).
    @param annuity_type           'level' | 'inflation_linked' | 'joint_life'.
    @param inflation_rate         Annual escalation if annuity_type ==
                                  'inflation_linked'.
    @param joint_life_fraction    Fraction paid to surviving partner after
                                  first death (e.g. 0.50).  Only for
                                  'joint_life'.
    @param guarantee_years        Guarantee period in years (annuity pays
                                  estate if annuitant dies early).
    @param notes                  Free-text notes.
    """

    enabled: bool = False
    conversion_date: Optional[date] = None
    conversion_fraction: float = 1.0
    annuity_rate_per_100k: float = 5200.0        # £/yr per £100k
    annuity_type: str = "level"                  # 'level' | 'inflation_linked' | 'joint_life'
    inflation_rate: float = 0.025
    joint_life_fraction: float = 0.50
    guarantee_years: int = 5
    notes: str = ""


@dataclass
class AllowanceConfig:
    """
    @brief Annual allowance and carry-forward settings.

    @param jurisdiction           'uk' | 'us' | 'ireland' | 'generic'.
    @param annual_allowance       Maximum gross contribution per year before
                                  a tax charge (UK 2024: £60,000).
    @param money_purchase_annual_allowance  UK MPAA that kicks in once
                                  flexible drawdown has started (£10,000).
    @param carry_forward_years    Number of prior years available for
                                  carry-forward relief (UK: 3).
    @param prior_year_unused      Dict of {year: unused_allowance} for
                                  carry-forward calculation.
    @param rmd_start_age          Age at which US RMDs begin (73 post-SECURE 2.0).
    @param rmd_table              'uniform_lifetime' | 'joint_life'.
                                  Determines which IRS table is used.
    @param enabled                Set False to skip allowance checking
                                  (non-UK/US pensions, or already exceeded).
    @param notes                  Free-text notes.
    """

    jurisdiction: str = "uk"
    annual_allowance: float = 60_000.0
    money_purchase_annual_allowance: float = 10_000.0
    carry_forward_years: int = 3
    prior_year_unused: dict = field(default_factory=dict)  # {year_int: float}
    rmd_start_age: int = 73
    rmd_table: str = "uniform_lifetime"
    enabled: bool = True
    notes: str = ""


@dataclass
class PensionConfig:
    """
    @brief Root configuration for a single pension pot, loaded from YAML.

    @param pension_id             Unique identifier string.
    @param label                  Display name.
    @param person_id              FK to the Person this pension belongs to.
    @param pension_type           'sipp' | 'workplace' | '401k' | 'ira_traditional'
                                  | 'ira_roth' | 'db' | 'generic'.
    @param current_value          Current fund value in base currency.
    @param valuation_date         Date current_value was recorded.
    @param currency               ISO 4217 code.
    @param annual_fee_rate        Platform/fund annual management charge as a
                                  decimal (0.0015 = 0.15 %).  Applied before
                                  growth each year.
    @param person_dob             Date of birth of the pension holder.  Used
                                  for age-based RMD and MPAA logic.
    @param contribution_periods   Ordered list of ContributionPeriod objects.
    @param growth_periods         Ordered list of GrowthPeriod objects.
    @param drawdown_config        DrawdownConfig settings.
    @param annuity_config         AnnuityConfig settings.
    @param allowance_config       AllowanceConfig settings.
    @param inside_estate          Whether the pension counts toward the estate
                                  for IHT (UK SIPPs are typically outside).
    @param enabled                Set False to exclude without deleting config.
    @param notes                  Free-text notes.
    """

    pension_id: str
    label: str
    person_id: str
    pension_type: str                           # 'sipp' | 'workplace' | '401k' | ...
    current_value: float
    valuation_date: date
    currency: str = "GBP"
    annual_fee_rate: float = 0.0015            # 0.15% AMC default
    person_dob: Optional[date] = None
    contribution_periods: list[ContributionPeriod] = field(default_factory=list)
    growth_periods: list[GrowthPeriod] = field(default_factory=list)
    drawdown_config: DrawdownConfig = field(default_factory=DrawdownConfig)
    annuity_config: AnnuityConfig = field(default_factory=AnnuityConfig)
    allowance_config: AllowanceConfig = field(default_factory=AllowanceConfig)
    inside_estate: bool = False
    enabled: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PensionYearRow:
    """
    @brief One year of the pension projection.

    @param year                   Calendar year.
    @param age                    Holder's age at end of year (None if no DOB).
    @param phase                  'accumulation' | 'drawdown' | 'annuity' | 'exhausted'.
    @param opening_value          Fund value at start of year.
    @param employee_contribution  Employee contribution in the year.
    @param employer_contribution  Employer contribution in the year.
    @param total_contribution     employee + employer.
    @param allowance_used         Gross contributions counted against allowance.
    @param allowance_available    Total allowance available this year
                                  (including carry-forward).
    @param allowance_breached     True if total_contribution > allowance_available.
    @param gross_growth           Investment return before fees.
    @param fee_charge             Annual management charge deducted.
    @param net_growth             gross_growth minus fee_charge.
    @param pcls_taken             Tax-free lump sum taken (drawdown year 1 only).
    @param drawdown_income        Gross income drawn from the pot.
    @param taxable_drawdown       Portion of drawdown subject to income tax.
    @param annuity_income         Annual income from annuity conversion (if any).
    @param rmd_required           US RMD amount required this year (0 if N/A).
    @param closing_value          Fund value at end of year.
    @param growth_rate            Growth rate applied this year.
    @param annual_fee_rate        Fee rate applied this year.
    """

    year: int
    age: Optional[int]
    phase: str
    opening_value: float
    employee_contribution: float
    employer_contribution: float
    total_contribution: float
    allowance_used: float
    allowance_available: float
    allowance_breached: bool
    gross_growth: float
    fee_charge: float
    net_growth: float
    pcls_taken: float
    drawdown_income: float
    taxable_drawdown: float
    annuity_income: float
    rmd_required: float
    closing_value: float
    growth_rate: float
    annual_fee_rate: float


@dataclass
class AnnuityStream:
    """
    @brief The resulting income stream after annuity conversion.

    @param start_date             Date annuity income begins.
    @param annual_income_base     Annual income in the first year.
    @param annuity_type           Mirrors AnnuityConfig.annuity_type.
    @param inflation_rate         Annual escalation rate (0 for level).
    @param joint_life_fraction    Survivor fraction (0 if not joint).
    @param guarantee_years        Guarantee period.
    @param fund_converted         Fund value at point of conversion.
    """

    start_date: date
    annual_income_base: float
    annuity_type: str
    inflation_rate: float
    joint_life_fraction: float
    guarantee_years: int
    fund_converted: float


@dataclass
class PensionResult:
    """
    @brief Top-level result from PensionEngine.run().

    @param pension_id             Mirrors PensionConfig.pension_id.
    @param schedule               Year-by-year projection rows.
    @param total_contributions    Total paid in over projection horizon.
    @param total_employer_contributions  Total employer paid in.
    @param total_growth           Total net growth over horizon.
    @param total_fees             Total fees paid over horizon.
    @param total_pcls             Total tax-free cash taken.
    @param total_drawdown_income  Total gross drawdown income taken.
    @param total_annuity_income   Total annuity income over projection.
    @param peak_value             Highest fund value reached.
    @param peak_value_year        Year in which peak_value occurred.
    @param exhaustion_year        Year the fund hits zero (None if never).
    @param annuity_stream         AnnuityStream if conversion occurred, else None.
    @param allowance_breaches     List of years where annual allowance was breached.
    @param warnings               General warning strings.
    """

    pension_id: str
    schedule: list[PensionYearRow]
    total_contributions: float
    total_employer_contributions: float
    total_growth: float
    total_fees: float
    total_pcls: float
    total_drawdown_income: float
    total_annuity_income: float
    peak_value: float
    peak_value_year: int
    exhaustion_year: Optional[int]
    annuity_stream: Optional[AnnuityStream]
    allowance_breaches: list[int]
    warnings: list[str]


# ---------------------------------------------------------------------------
# IRS Uniform Lifetime Table (simplified — distribution period by age)
# Used for RMD calculation.  Ages 72-120.
# ---------------------------------------------------------------------------

_ULT: dict[int, float] = {
    72: 27.4, 73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9,
    78: 22.0, 79: 21.1, 80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7,
    84: 16.8, 85: 16.0, 86: 15.2, 87: 14.4, 88: 13.7, 89: 12.9,
    90: 12.2, 91: 11.5, 92: 10.8, 93: 10.1, 94:  9.5, 95:  8.9,
    96:  8.4, 97:  7.8, 98:  7.3, 99:  6.8, 100:  6.4,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PensionEngine:
    """
    @brief Core pension projection engine.

    Runs a year-by-year simulation of a pension pot from a given start year
    through a given end year, handling accumulation, drawdown, annuity
    conversion, annual allowance checking, and RMD enforcement.

    Usage::

        engine = PensionEngine(config, start_year=2025, end_year=2070)
        result = engine.run()
    """

    def __init__(
        self,
        config: PensionConfig,
        start_year: int,
        end_year: int,
    ) -> None:
        """
        @brief Initialise the engine.

        @param config      Populated PensionConfig.
        @param start_year  First calendar year to project (inclusive).
        @param end_year    Last calendar year to project (inclusive).
        @raises ValueError If config fails basic validation.
        """
        self._cfg = config
        self._start_year = start_year
        self._end_year = end_year
        self._validate_config()
        logger.info(
            "PensionEngine initialised: id=%s type=%s value=%.2f years=%d-%d",
            config.pension_id,
            config.pension_type,
            config.current_value,
            start_year,
            end_year,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> PensionResult:
        """
        @brief Execute the full pension projection.

        Iterates year by year from start_year to end_year, transitioning
        between accumulation, drawdown, and annuity phases automatically
        based on configured dates.

        @return PensionResult with schedule, summaries, and metadata.
        """
        logger.info("Running pension projection for id=%s", self._cfg.pension_id)

        schedule: list[PensionYearRow] = []
        warnings: list[str] = []
        allowance_breaches: list[int] = []

        fund = self._cfg.current_value
        annuity_stream: Optional[AnnuityStream] = None
        annuity_income_base: float = 0.0
        pcls_taken_total: float = 0.0
        pcls_applied: bool = False
        real_drawdown_amount: float = self._cfg.drawdown_config.annual_drawdown_amount
        exhaustion_year: Optional[int] = None
        peak_value: float = fund
        peak_year: int = self._start_year

        # Carry-forward pool — initialise from prior_year_unused
        carry_forward_pool: dict[int, float] = dict(
            self._cfg.allowance_config.prior_year_unused
        )

        for year in range(self._start_year, self._end_year + 1):
            if fund < 0.001 and exhaustion_year is None and self._phase(year) != "accumulation":
                exhaustion_year = year
                logger.info("Pension %s exhausted in %d", self._cfg.pension_id, year)

            age = self._age_at_year_end(year)
            phase = self._phase(year)
            growth_rate = self._growth_rate_for_year(year)
            fee_rate = self._cfg.annual_fee_rate

            opening_value = max(0.0, fund)

            # ── Accumulation ──────────────────────────────────────────────
            emp_contrib = 0.0
            er_contrib = 0.0
            allowance_used = 0.0
            allowance_available = 0.0
            breached = False

            if phase == "accumulation":
                emp_contrib, er_contrib = self._contributions_for_year(year)
                total_contrib = emp_contrib + er_contrib

                # Allowance check
                if self._cfg.allowance_config.enabled:
                    allowance_available, carry_forward_pool = self._allowance_available(
                        year, carry_forward_pool
                    )
                    allowance_used = total_contrib
                    if allowance_used > allowance_available:
                        msg = (
                            f"Year {year}: contributions £{allowance_used:,.0f} exceed "
                            f"available allowance £{allowance_available:,.0f} "
                            f"(including carry-forward). Excess is subject to annual "
                            f"allowance charge."
                        )
                        logger.warning(msg)
                        warnings.append(msg)
                        allowance_breaches.append(year)
                        breached = True

                    # Record unused allowance for future carry-forward
                    unused = max(0.0, allowance_available - allowance_used)
                    carry_forward_pool[year] = unused

                fund += total_contrib

            # ── Growth (applied in all phases while fund > 0) ─────────────
            gross_growth = 0.0
            fee_charge = 0.0
            net_growth = 0.0
            if fund > 0:
                gross_growth = round(fund * growth_rate, 2)
                fee_charge = round(fund * fee_rate, 2)
                net_growth = gross_growth - fee_charge
                fund += net_growth

            # ── PCLS (first drawdown year) ─────────────────────────────────
            pcls_taken = 0.0
            if (
                phase == "drawdown"
                and not pcls_applied
                and self._cfg.drawdown_config.apply_pcls
                and self._cfg.pension_type in ("sipp", "workplace", "generic")
            ):
                pcls_fraction = self._cfg.drawdown_config.pcls_fraction
                pcls_taken = round(fund * pcls_fraction, 2)
                fund = max(0.0, fund - pcls_taken)
                pcls_taken_total += pcls_taken
                pcls_applied = True
                logger.info(
                    "PCLS taken in %d: £%.2f (fraction=%.0f%%)",
                    year, pcls_taken, pcls_fraction * 100,
                )

            # ── Drawdown income ────────────────────────────────────────────
            drawdown_income = 0.0
            taxable_drawdown = 0.0
            rmd_required = 0.0

            if phase == "drawdown" and fund > self._cfg.drawdown_config.min_balance:
                mode = self._cfg.drawdown_config.mode
                dc = self._cfg.drawdown_config

                if mode == "percentage":
                    drawdown_income = round(fund * dc.annual_drawdown_rate, 2)
                elif mode == "fixed_amount":
                    drawdown_income = dc.annual_drawdown_amount
                elif mode == "fixed_real":
                    # Inflate the real amount each year from drawdown start
                    years_in_drawdown = year - dc.drawdown_start_date.year
                    real_drawdown_amount = round(
                        dc.annual_drawdown_amount
                        * (1 + dc.inflation_rate) ** max(0, years_in_drawdown),
                        2,
                    )
                    drawdown_income = real_drawdown_amount
                else:
                    logger.warning("Unknown drawdown mode '%s' — defaulting to 0", mode)

                # US RMD enforcement
                if (
                    self._cfg.pension_type in ("401k", "ira_traditional")
                    and age is not None
                    and age >= self._cfg.allowance_config.rmd_start_age
                ):
                    rmd_required = self._rmd_amount(fund, age)
                    if drawdown_income < rmd_required:
                        logger.debug(
                            "Year %d: drawdown £%.2f below RMD £%.2f — uplifting",
                            year, drawdown_income, rmd_required,
                        )
                        drawdown_income = rmd_required

                # Cap drawdown at fund floor
                drawdown_income = min(
                    drawdown_income,
                    max(0.0, fund - self._cfg.drawdown_config.min_balance),
                )
                taxable_drawdown = drawdown_income   # PCLS already excluded
                fund = max(0.0, fund - drawdown_income)

            # ── Annuity conversion ─────────────────────────────────────────
            annuity_income_this_year = 0.0
            ac = self._cfg.annuity_config

            if (
                ac.enabled
                and annuity_stream is None
                and ac.conversion_date is not None
                and year == ac.conversion_date.year
                and fund > 0
            ):
                fund_converted = round(fund * ac.conversion_fraction, 2)
                fund = max(0.0, fund - fund_converted)
                income_base = round(
                    fund_converted / 100_000.0 * ac.annuity_rate_per_100k, 2
                )
                annuity_stream = AnnuityStream(
                    start_date=ac.conversion_date,
                    annual_income_base=income_base,
                    annuity_type=ac.annuity_type,
                    inflation_rate=ac.inflation_rate if ac.annuity_type == "inflation_linked" else 0.0,
                    joint_life_fraction=ac.joint_life_fraction,
                    guarantee_years=ac.guarantee_years,
                    fund_converted=fund_converted,
                )
                logger.info(
                    "Annuity conversion in %d: fund=£%.2f income=£%.2f/yr type=%s",
                    year, fund_converted, income_base, ac.annuity_type,
                )

            if annuity_stream is not None:
                years_since_conversion = year - annuity_stream.start_date.year
                annuity_income_this_year = round(
                    annuity_stream.annual_income_base
                    * (1 + annuity_stream.inflation_rate) ** max(0, years_since_conversion),
                    2,
                )

            # ── Closing value & peak tracking ──────────────────────────────
            closing_value = round(max(0.0, fund), 2)
            if closing_value > peak_value:
                peak_value = closing_value
                peak_year = year

            row = PensionYearRow(
                year=year,
                age=age,
                phase=phase if fund > 0 or phase == "accumulation" else "exhausted",
                opening_value=round(opening_value, 2),
                employee_contribution=round(emp_contrib, 2),
                employer_contribution=round(er_contrib, 2),
                total_contribution=round(emp_contrib + er_contrib, 2),
                allowance_used=round(allowance_used, 2),
                allowance_available=round(allowance_available, 2),
                allowance_breached=breached,
                gross_growth=round(gross_growth, 2),
                fee_charge=round(fee_charge, 2),
                net_growth=round(net_growth, 2),
                pcls_taken=round(pcls_taken, 2),
                drawdown_income=round(drawdown_income, 2),
                taxable_drawdown=round(taxable_drawdown, 2),
                annuity_income=round(annuity_income_this_year, 2),
                rmd_required=round(rmd_required, 2),
                closing_value=closing_value,
                growth_rate=growth_rate,
                annual_fee_rate=fee_rate,
            )
            schedule.append(row)
            fund = closing_value

        # ── Aggregate metrics ──────────────────────────────────────────────
        total_contributions = round(sum(r.employee_contribution for r in schedule), 2)
        total_employer     = round(sum(r.employer_contribution for r in schedule), 2)
        total_growth       = round(sum(r.net_growth for r in schedule), 2)
        total_fees         = round(sum(r.fee_charge for r in schedule), 2)
        total_drawdown     = round(sum(r.drawdown_income for r in schedule), 2)
        total_annuity      = round(sum(r.annuity_income for r in schedule), 2)

        logger.info(
            "Pension projection complete: id=%s periods=%d peak=%.2f in %d "
            "total_contrib=%.2f total_drawdown=%.2f",
            self._cfg.pension_id,
            len(schedule),
            peak_value,
            peak_year,
            total_contributions + total_employer,
            total_drawdown,
        )

        return PensionResult(
            pension_id=self._cfg.pension_id,
            schedule=schedule,
            total_contributions=total_contributions,
            total_employer_contributions=total_employer,
            total_growth=total_growth,
            total_fees=total_fees,
            total_pcls=pcls_taken_total,
            total_drawdown_income=total_drawdown,
            total_annuity_income=total_annuity,
            peak_value=round(peak_value, 2),
            peak_value_year=peak_year,
            exhaustion_year=exhaustion_year,
            annuity_stream=annuity_stream,
            allowance_breaches=allowance_breaches,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_config(self) -> None:
        """
        @brief Sanity-check the PensionConfig before running.

        @raises ValueError On any fatal configuration error.
        """
        cfg = self._cfg
        errors: list[str] = []

        if cfg.current_value < 0:
            errors.append(f"current_value must be >= 0, got {cfg.current_value}")
        if cfg.annual_fee_rate < 0 or cfg.annual_fee_rate > 0.05:
            errors.append(
                f"annual_fee_rate {cfg.annual_fee_rate} looks unreasonable "
                f"(expected 0–0.05).  Check config."
            )
        if not cfg.growth_periods:
            errors.append("growth_periods must contain at least one entry.")

        dc = cfg.drawdown_config
        if dc.mode not in ("percentage", "fixed_amount", "fixed_real"):
            errors.append(f"drawdown_config.mode '{dc.mode}' is not recognised.")
        if dc.mode == "percentage" and not (0 < dc.annual_drawdown_rate <= 1):
            errors.append(
                f"drawdown_config.annual_drawdown_rate {dc.annual_drawdown_rate} "
                f"must be in (0, 1]."
            )
        if dc.pcls_fraction < 0 or dc.pcls_fraction > 0.25:
            errors.append(
                f"drawdown_config.pcls_fraction {dc.pcls_fraction} must be in [0, 0.25]."
            )
        if cfg.allowance_config.annual_allowance <= 0:
            errors.append("allowance_config.annual_allowance must be > 0.")
        if self._start_year > self._end_year:
            errors.append(f"start_year {self._start_year} > end_year {self._end_year}.")

        if errors:
            msg = (
                f"PensionConfig validation failed for '{cfg.pension_id}': "
                + "; ".join(errors)
            )
            logger.error(msg)
            raise ValueError(msg)

    def _phase(self, year: int) -> str:
        """
        @brief Determine the lifecycle phase for a given calendar year.

        @param year  Calendar year being evaluated.
        @return      'accumulation' | 'drawdown' | 'annuity'.
        """
        ac = self._cfg.annuity_config
        dc = self._cfg.drawdown_config

        if ac.enabled and ac.conversion_date and year >= ac.conversion_date.year:
            return "annuity"
        if dc.drawdown_start_date and year >= dc.drawdown_start_date.year:
            if dc.drawdown_end_date and year > dc.drawdown_end_date.year:
                return "annuity"
            return "drawdown"
        return "accumulation"

    def _age_at_year_end(self, year: int) -> Optional[int]:
        """
        @brief Compute the holder's age on 31 December of a given year.

        @param year  Calendar year.
        @return      Integer age, or None if person_dob is not set.
        """
        if self._cfg.person_dob is None:
            return None
        return year - self._cfg.person_dob.year

    def _growth_rate_for_year(self, year: int) -> float:
        """
        @brief Resolve the assumed annual growth rate for a given calendar year.

        Iterates growth_periods in order; last matching period wins.  Falls
        back to the final period if no period explicitly covers the year.

        @param year  Calendar year.
        @return      Annual growth rate as a decimal.
        """
        applicable: Optional[GrowthPeriod] = None
        ref_date = date(year, 6, 30)   # mid-year reference

        for gp in self._cfg.growth_periods:
            if gp.start_date <= ref_date:
                if gp.end_date is None or gp.end_date >= ref_date:
                    applicable = gp

        if applicable is None:
            applicable = self._cfg.growth_periods[-1]
            logger.debug(
                "No growth period matched year %d; falling back to '%s'",
                year,
                applicable.label,
            )
        return applicable.annual_rate

    def _contributions_for_year(self, year: int) -> tuple[float, float]:
        """
        @brief Return (employee, employer) annual contributions for a year.

        Finds the last ContributionPeriod whose start_date falls before or on
        the mid-year reference date and whose end_date covers it.

        @param year  Calendar year.
        @return      (employee_annual, employer_annual) tuple; (0, 0) if no
                     matching period or outside accumulation.
        """
        ref_date = date(year, 6, 30)
        applicable: Optional[ContributionPeriod] = None

        for cp in self._cfg.contribution_periods:
            if cp.start_date <= ref_date:
                if cp.end_date is None or cp.end_date >= ref_date:
                    applicable = cp

        if applicable is None:
            return 0.0, 0.0
        return applicable.employee_annual, applicable.employer_annual

    def _allowance_available(
        self,
        year: int,
        carry_forward_pool: dict[int, float],
    ) -> tuple[float, dict[int, float]]:
        """
        @brief Compute the total pension allowance available for a year.

        Sums the current-year annual allowance with unused allowances from
        the previous carry_forward_years, then purges years too old to use.

        @param year               Current calendar year.
        @param carry_forward_pool Dict of {year: unused_allowance}.
        @return                   Tuple of (total_allowance, updated_pool).
        """
        ac = self._cfg.allowance_config
        base = ac.annual_allowance
        cf_window = ac.carry_forward_years

        # Sum carry-forward from eligible prior years
        carry = sum(
            v for y, v in carry_forward_pool.items()
            if 0 < (year - y) <= cf_window
        )
        total = base + carry

        # Purge years now outside the window
        updated_pool = {
            y: v for y, v in carry_forward_pool.items()
            if (year - y) <= cf_window
        }

        logger.debug(
            "Year %d allowance: base=%.0f carry=%.0f total=%.0f",
            year, base, carry, total,
        )
        return round(total, 2), updated_pool

    def _rmd_amount(self, fund: float, age: int) -> float:
        """
        @brief Compute the IRS Required Minimum Distribution for a given age.

        Uses the Uniform Lifetime Table (IRS Pub. 590-B).  For ages beyond the
        table, a distribution period of 6.1 is assumed (age 100+ entry).

        @param fund  Fund value at start of year.
        @param age   Holder's age at end of year.
        @return      RMD amount in currency units.
        """
        distribution_period = _ULT.get(age, 6.1)
        rmd = round(fund / distribution_period, 2)
        logger.debug("RMD age=%d fund=%.2f period=%.1f rmd=%.2f", age, fund, distribution_period, rmd)
        return rmd


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def _parse_date(value) -> date:
    """
    @brief Coerce a YAML value to a Python date.

    @param value  Raw value from YAML (date, datetime, or ISO string).
    @return       Python date.
    @raises ValueError If unparseable.
    """
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"Cannot parse date from '{value}': {exc}") from exc


def load_pension_config_from_yaml(path: str) -> PensionConfig:
    """
    @brief Load a PensionConfig from a YAML file.

    Expected top-level key: ``pension``.

    @param path  Filesystem path to the YAML config file.
    @return      Populated PensionConfig dataclass.
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file contains invalid YAML.
    @raises ValueError         If required keys are missing or invalid.
    """
    logger.info("Loading pension config from: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Pension config file not found: %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise

    if "pension" not in raw:
        raise ValueError(f"YAML '{path}' must have a top-level 'pension' key.")

    p = raw["pension"]

    # Contribution periods
    contribution_periods: list[ContributionPeriod] = []
    for cp_raw in p.get("contribution_periods", []):
        contribution_periods.append(ContributionPeriod(
            label=cp_raw.get("label", ""),
            start_date=_parse_date(cp_raw["start_date"]),
            end_date=_parse_date(cp_raw["end_date"]) if cp_raw.get("end_date") else None,
            employee_annual=float(cp_raw.get("employee_annual", 0)),
            employer_annual=float(cp_raw.get("employer_annual", 0)),
            employee_relief_rate=float(cp_raw.get("employee_relief_rate", 0.20)),
            notes=cp_raw.get("notes", ""),
        ))

    # Growth periods
    growth_periods: list[GrowthPeriod] = []
    for gp_raw in p.get("growth_periods", []):
        growth_periods.append(GrowthPeriod(
            label=gp_raw.get("label", ""),
            start_date=_parse_date(gp_raw["start_date"]),
            end_date=_parse_date(gp_raw["end_date"]) if gp_raw.get("end_date") else None,
            annual_rate=float(gp_raw["annual_rate"]),
            notes=gp_raw.get("notes", ""),
        ))

    # Drawdown config
    dc_raw = p.get("drawdown_config", {})
    drawdown_cfg = DrawdownConfig(
        mode=dc_raw.get("mode", "percentage"),
        annual_drawdown_rate=float(dc_raw.get("annual_drawdown_rate", 0.04)),
        annual_drawdown_amount=float(dc_raw.get("annual_drawdown_amount", 0.0)),
        inflation_rate=float(dc_raw.get("inflation_rate", 0.025)),
        apply_pcls=bool(dc_raw.get("apply_pcls", True)),
        pcls_fraction=float(dc_raw.get("pcls_fraction", 0.25)),
        drawdown_start_date=_parse_date(dc_raw["drawdown_start_date"]) if dc_raw.get("drawdown_start_date") else None,
        drawdown_end_date=_parse_date(dc_raw["drawdown_end_date"]) if dc_raw.get("drawdown_end_date") else None,
        min_balance=float(dc_raw.get("min_balance", 0.0)),
        notes=dc_raw.get("notes", ""),
    )

    # Annuity config
    ac_raw = p.get("annuity_config", {})
    annuity_cfg = AnnuityConfig(
        enabled=bool(ac_raw.get("enabled", False)),
        conversion_date=_parse_date(ac_raw["conversion_date"]) if ac_raw.get("conversion_date") else None,
        conversion_fraction=float(ac_raw.get("conversion_fraction", 1.0)),
        annuity_rate_per_100k=float(ac_raw.get("annuity_rate_per_100k", 5200.0)),
        annuity_type=ac_raw.get("annuity_type", "level"),
        inflation_rate=float(ac_raw.get("inflation_rate", 0.025)),
        joint_life_fraction=float(ac_raw.get("joint_life_fraction", 0.50)),
        guarantee_years=int(ac_raw.get("guarantee_years", 5)),
        notes=ac_raw.get("notes", ""),
    )

    # Allowance config
    al_raw = p.get("allowance_config", {})
    allowance_cfg = AllowanceConfig(
        jurisdiction=al_raw.get("jurisdiction", "uk"),
        annual_allowance=float(al_raw.get("annual_allowance", 60_000)),
        money_purchase_annual_allowance=float(al_raw.get("money_purchase_annual_allowance", 10_000)),
        carry_forward_years=int(al_raw.get("carry_forward_years", 3)),
        prior_year_unused={int(k): float(v) for k, v in al_raw.get("prior_year_unused", {}).items()},
        rmd_start_age=int(al_raw.get("rmd_start_age", 73)),
        rmd_table=al_raw.get("rmd_table", "uniform_lifetime"),
        enabled=bool(al_raw.get("enabled", True)),
        notes=al_raw.get("notes", ""),
    )

    cfg = PensionConfig(
        pension_id=p["pension_id"],
        label=p["label"],
        person_id=p["person_id"],
        pension_type=p["pension_type"],
        current_value=float(p["current_value"]),
        valuation_date=_parse_date(p["valuation_date"]),
        currency=p.get("currency", "GBP"),
        annual_fee_rate=float(p.get("annual_fee_rate", 0.0015)),
        person_dob=_parse_date(p["person_dob"]) if p.get("person_dob") else None,
        contribution_periods=contribution_periods,
        growth_periods=growth_periods,
        drawdown_config=drawdown_cfg,
        annuity_config=annuity_cfg,
        allowance_config=allowance_cfg,
        inside_estate=bool(p.get("inside_estate", False)),
        enabled=bool(p.get("enabled", True)),
        notes=p.get("notes", ""),
    )

    logger.info(
        "Loaded pension '%s' (type=%s value=%.2f contrib_periods=%d growth_periods=%d)",
        cfg.pension_id,
        cfg.pension_type,
        cfg.current_value,
        len(contribution_periods),
        len(growth_periods),
    )
    return cfg
