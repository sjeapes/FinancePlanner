"""
@file country_comparison_engine.py
@brief Phase 7 UK vs US country comparison engine for LifeLedger.

Runs two parallel financial projections — one for each country path — and
produces a comparison matrix showing the delta at key ages, along with a
break-even analysis (when does the UK path overtake the US path in common
currency) and an estate comparison.

Architecture:
  ``CountryProjectionEngine.run_path()`` — one country's full projection
  ``CountryComparisonEngine.compare()``  — runs both and computes deltas

Key validation targets (mid scenario, from spec):
  US retirement wealth at 2044:    ~$12.9M
  UK retirement wealth at 2044:    ~£5.5M
  Annual housing cost 2029:         $98,433/yr (US) vs £29,280/yr (UK)
  Hannah university (parental mid): $134k (US) vs £98k (UK)
  ACA bridge healthcare 62–65:      $26k/yr (US) vs £0 (UK NHS)

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from backend.engine.generational_engine import (
    GenerationalMacro,
    calculate_uk_tax,
    calculate_us_tax,
    load_generational_config,
)

logger = logging.getLogger("lifeledger.country_comparison")


# ─────────────────────────────────────────────────────────────────────────────
# Country path configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ParentPhaseConfig:
    """
    @brief One working phase in a country path (e.g. US 2026–2028).

    @param start_year         First year of this phase.
    @param end_year           Last year of this phase (None = ongoing).
    @param country            'uk' | 'us'.
    @param gross_income       Combined household gross income (in native currency).
    @param pension_rate_employee  Employee pension/401k contribution rate.
    @param pension_employer_match  Employer match rate.
    @param annual_living_cost     Annual household living expenditure.
    @param state_tax_rate        US state income tax rate (0.0 for WA).
    @param housing_cost_annual   Mortgage or rent per year.
    @param currency              'GBP' | 'USD'.
    """
    start_year: int
    country: str
    gross_income: float
    pension_rate_employee: float
    pension_employer_match: float
    annual_living_cost: float
    housing_cost_annual: float
    currency: str
    end_year: Optional[int] = None
    state_tax_rate: float = 0.0


@dataclass
class CountryPathConfig:
    """
    @brief Full configuration for one country path.

    @param path_id         Unique identifier (e.g. 'uk_path').
    @param label           Display label.
    @param country         'uk' | 'us'.
    @param start_year      First projection year.
    @param retire_year     Year of retirement.
    @param death_year      Assumed death year (last survivor).
    @param starting_wealth_gbp   Starting portfolio in GBP.
    @param starting_pension_gbp  Starting pension in GBP.
    @param starting_property_gbp  Property value in GBP.
    @param starting_mortgage_gbp  Mortgage balance in GBP.
    @param phases          List of working phases in order.
    @param state_pension_annual_gbp  UK state pension or US SS equivalent in GBP.
    @param state_pension_start_year  Year state pension / SS begins.
    @param fx_rate         GBP/USD rate (used for comparison in common currency).
    """
    path_id: str
    label: str
    country: str
    start_year: int
    retire_year: int
    death_year: int
    starting_wealth_gbp: float
    starting_pension_gbp: float
    starting_property_gbp: float
    starting_mortgage_gbp: float
    phases: list[ParentPhaseConfig]
    state_pension_annual_gbp: float
    state_pension_start_year: int
    fx_rate: float = 1.27


# ─────────────────────────────────────────────────────────────────────────────
# Country path projection result
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CountryYearSnapshot:
    """
    @brief Financial state in one year for one country path.

    @param year               Calendar year.
    @param age_primary        Primary person's age.
    @param country            'uk' | 'us'.
    @param gross_income       Household gross income (native currency).
    @param income_tax         Total income tax (native currency).
    @param pension_contrib    Pension/401k contribution (native currency).
    @param net_income         Take-home pay (native currency).
    @param living_cost        Annual living expenditure.
    @param housing_cost       Mortgage or rent payment.
    @param healthcare_cost    Healthcare expenditure.
    @param savings            Net savings (net_income - living - housing - healthcare).
    @param portfolio_value    Total investable portfolio value.
    @param pension_value      Pension / 401k value.
    @param property_value     Property value.
    @param total_wealth       Portfolio + pension + property - mortgage.
    @param total_wealth_gbp   Converted to GBP for comparison.
    @param fire_coverage      Total wealth / FIRE target.
    @param state_pension_income  State pension / SS income (0 before start_year).
    @param phase              'working' | 'retired'.
    """
    year: int
    age_primary: int
    country: str
    gross_income: float
    income_tax: float
    pension_contrib: float
    net_income: float
    living_cost: float
    housing_cost: float
    healthcare_cost: float
    savings: float
    portfolio_value: float
    pension_value: float
    property_value: float
    total_wealth: float
    total_wealth_gbp: float
    fire_coverage: float
    state_pension_income: float
    phase: str


@dataclass
class CountryPathResult:
    """
    @brief Full projection result for one country path.

    @param path_id           Path identifier.
    @param label             Display label.
    @param country           'uk' | 'us'.
    @param years             Year-by-year snapshots.
    @param retire_year       Configured retirement year.
    @param fire_year         Year FIRE target is met (may equal retire_year).
    @param wealth_at_retirement  Total wealth at retire_year.
    @param wealth_at_death       Total wealth at death_year.
    @param lifetime_income_tax   Total income tax paid over working life.
    @param lifetime_healthcare   Total healthcare cost over full life.
    @param total_housing_cost    Total housing costs over full life.
    @param currency          Native currency symbol.
    @param fx_rate           GBP/USD used for common-currency comparison.
    """
    path_id: str
    label: str
    country: str
    years: list[CountryYearSnapshot]
    retire_year: int
    fire_year: Optional[int]
    wealth_at_retirement: float
    wealth_at_death: float
    lifetime_income_tax: float
    lifetime_healthcare: float
    total_housing_cost: float
    currency: str
    fx_rate: float

    def year(self, yr: int) -> Optional[CountryYearSnapshot]:
        """@brief Return snapshot for a specific year or None."""
        for s in self.years:
            if s.year == yr:
                return s
        return None

    def wealth_gbp(self, yr: int) -> float:
        """@brief Total wealth in GBP at a given year."""
        s = self.year(yr)
        return s.total_wealth_gbp if s else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Comparison result
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ComparisonKeyAge:
    """
    @brief Metrics at one key age for both paths.

    @param year              Calendar year.
    @param age               Parent age.
    @param uk_wealth_gbp     UK path total wealth in GBP.
    @param us_wealth_gbp     US path total wealth in GBP.
    @param delta_gbp         US minus UK in GBP (positive = US richer).
    @param uk_annual_tax     UK income tax that year.
    @param us_annual_tax_gbp US income tax converted to GBP.
    @param uk_healthcare     UK healthcare cost (usually £0).
    @param us_healthcare_gbp US healthcare cost in GBP.
    """
    year: int
    age: int
    uk_wealth_gbp: float
    us_wealth_gbp: float
    delta_gbp: float
    uk_annual_tax: float
    us_annual_tax_gbp: float
    uk_healthcare: float
    us_healthcare_gbp: float


@dataclass
class BreakEvenResult:
    """
    @brief Year at which one path overtakes the other in common currency.

    @param break_even_year    Year when paths cross (None if no crossover).
    @param leading_path_early Path that leads in wealth before break-even.
    @param leading_path_late  Path that leads after break-even.
    @param uk_wealth_at_bey   UK wealth at break-even year.
    @param us_wealth_at_bey   US wealth at break-even year (in GBP).
    """
    break_even_year: Optional[int]
    leading_path_early: str
    leading_path_late: str
    uk_wealth_at_bey: float
    us_wealth_at_bey: float


@dataclass
class CountryComparisonResult:
    """
    @brief Full UK vs US comparison output.

    @param uk_path            UK path projection result.
    @param us_path            US path projection result.
    @param key_ages           ComparisonKeyAge at ages 45, 50, 55, 60, 65, 70, 80.
    @param break_even         BreakEvenResult.
    @param uk_estate_gbp      UK net estate to offspring (after IHT).
    @param us_estate_gbp      US net estate to offspring (converted to GBP).
    @param us_advantage_at_retirement_gbp  US minus UK wealth at retirement in GBP.
    @param lifetime_tax_delta_gbp  US lifetime tax minus UK lifetime tax (GBP).
    @param lifetime_healthcare_delta_gbp  US minus UK healthcare (GBP).
    @param warnings           Warning strings.
    """
    uk_path: CountryPathResult
    us_path: CountryPathResult
    key_ages: list[ComparisonKeyAge]
    break_even: BreakEvenResult
    uk_estate_gbp: float
    us_estate_gbp: float
    us_advantage_at_retirement_gbp: float
    lifetime_tax_delta_gbp: float
    lifetime_healthcare_delta_gbp: float
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Country path projection engine
# ─────────────────────────────────────────────────────────────────────────────


class CountryProjectionEngine:
    """
    @brief Projects one country path for parents from start_year to death_year.

    Handles multi-phase careers (e.g. US 2026–2028 then UK 2029+),
    pension accumulation and drawdown, healthcare costs, and state pension income.
    """

    # FIRE target: £5M for UK, $12M for US (matching spec validation targets)
    _FIRE_TARGET_GBP = 5_000_000.0
    _FIRE_TARGET_USD = 12_000_000.0

    def __init__(self, macro: GenerationalMacro) -> None:
        """
        @brief Initialise with macro assumptions.

        @param macro  GenerationalMacro for the projected country.
        """
        self._macro = macro

    def run_path(self, cfg: CountryPathConfig) -> CountryPathResult:
        """
        @brief Run the full country path projection.

        @param cfg  CountryPathConfig.
        @return     CountryPathResult.
        """
        macro = self._macro

        # Initialise account balances
        portfolio  = cfg.starting_wealth_gbp
        pension    = cfg.starting_pension_gbp
        property_v = cfg.starting_property_gbp
        mortgage   = cfg.starting_mortgage_gbp

        # Convert to USD if the path is US (working in native currency)
        if cfg.country == "us":
            portfolio  = portfolio  * cfg.fx_rate
            pension    = pension    * cfg.fx_rate
            property_v = property_v * cfg.fx_rate
            mortgage   = mortgage   * cfg.fx_rate

        birth_year = cfg.start_year - 44   # approximate: primary person aged 44 in 2026
        retire_year = cfg.retire_year
        fire_target = (self._FIRE_TARGET_GBP if cfg.country == "uk"
                       else self._FIRE_TARGET_USD)

        fire_year: Optional[int] = None
        lifetime_tax = 0.0
        lifetime_healthcare = 0.0
        total_housing = 0.0
        snapshots: list[CountryYearSnapshot] = []

        # Growth rates (nominal = real + inflation)
        eq_growth  = macro.nominal_equity_return
        pen_growth = macro.nominal_equity_return
        prop_growth = macro.inflation + 0.01  # property real growth ~1%

        for yr in range(cfg.start_year, cfg.death_year + 1):
            age = yr - birth_year
            phase = "working" if yr < retire_year else "retired"

            # Find active working phase
            active_phase: Optional[ParentPhaseConfig] = None
            for ph in cfg.phases:
                if ph.start_year <= yr and (ph.end_year is None or yr <= ph.end_year):
                    active_phase = ph
                    break

            gross = 0.0
            income_tax = 0.0
            pension_contrib = 0.0
            healthcare = 0.0
            living = 0.0
            housing = active_phase.housing_cost_annual if active_phase else 0.0

            if phase == "working" and active_phase:
                # Apply real salary growth each year
                yrs_in_phase = yr - active_phase.start_year
                gross = active_phase.gross_income * (
                    (1 + macro.salary_real_growth + macro.inflation) ** yrs_in_phase
                )

                if cfg.country == "uk":
                    tax_gbp, ni = calculate_uk_tax(gross, active_phase.pension_rate_employee)
                    income_tax = tax_gbp + ni
                    pension_contrib = gross * (
                        active_phase.pension_rate_employee + active_phase.pension_employer_match
                    )
                    net = gross - income_tax - pension_contrib
                    healthcare = 0.0   # NHS
                else:
                    k401 = min(gross * active_phase.pension_rate_employee, 23_500)
                    fed, fica, st = calculate_us_tax(
                        gross, pretax_401k=k401,
                        state_rate=active_phase.state_tax_rate,
                    )
                    income_tax = fed + fica + st
                    pension_contrib = k401 + gross * active_phase.pension_employer_match
                    net = gross - fed - fica - st - k401
                    healthcare = macro.healthcare_annual

                living = active_phase.annual_living_cost * (
                    (1 + macro.inflation) ** (yr - cfg.start_year)
                )
                savings = max(0.0, net - living - housing - healthcare)

                # Route savings and pension to accounts
                portfolio  = (portfolio  + savings)            * (1 + eq_growth)
                pension    = (pension    + pension_contrib)    * (1 + pen_growth)
                property_v = property_v * (1 + prop_growth)
                mortgage   = max(0.0, mortgage * 0.975)  # ~2.5% principal reduction/yr (approximate)

            elif phase == "retired":
                # Drawdown: spend from portfolio
                gross = cfg.state_pension_annual_gbp if yr >= cfg.state_pension_start_year else 0.0
                if cfg.country == "us":
                    gross = gross * cfg.fx_rate

                # Healthcare in retirement
                if cfg.country == "us":
                    if age < 62:
                        healthcare = macro.healthcare_annual
                    elif age <= 64:
                        healthcare = macro.healthcare_aca_bridge
                    elif age <= 79:
                        healthcare = macro.healthcare_medicare
                    else:
                        healthcare = macro.healthcare_late_life

                living = (active_phase.annual_living_cost if active_phase
                          else (40_000 if cfg.country == "uk" else 70_000))
                living = living * (1 + macro.inflation) ** (yr - cfg.start_year)

                # Drawdown from portfolio (FIRE income – state pension)
                target_drawdown = max(0.0, living + housing + healthcare - gross)
                portfolio  = max(0.0, portfolio - target_drawdown) * (1 + eq_growth * 0.7)
                pension    = pension  * (1 + pen_growth * 0.7)
                property_v = property_v * (1 + prop_growth)
                mortgage   = max(0.0, mortgage - target_drawdown * 0.1)

            lifetime_tax       += income_tax
            lifetime_healthcare += healthcare
            total_housing      += housing

            total_wealth = portfolio + pension + property_v - mortgage
            total_wealth_gbp = (total_wealth if cfg.country == "uk"
                                else total_wealth / cfg.fx_rate)

            if fire_year is None and total_wealth >= fire_target and phase == "working":
                fire_year = yr
                logger.debug("%s FIRE in %d: total_wealth=%.0f target=%.0f",
                             cfg.path_id, yr, total_wealth, fire_target)

            snapshots.append(CountryYearSnapshot(
                year=yr, age_primary=age, country=cfg.country,
                gross_income=round(gross, 2),
                income_tax=round(income_tax, 2),
                pension_contrib=round(pension_contrib, 2),
                net_income=round(max(0.0, gross - income_tax - pension_contrib), 2),
                living_cost=round(living, 2),
                housing_cost=round(housing, 2),
                healthcare_cost=round(healthcare, 2),
                savings=round(max(0.0, gross - income_tax - pension_contrib - living - housing - healthcare), 2),
                portfolio_value=round(portfolio, 2),
                pension_value=round(pension, 2),
                property_value=round(property_v, 2),
                total_wealth=round(total_wealth, 2),
                total_wealth_gbp=round(total_wealth_gbp, 2),
                fire_coverage=round(total_wealth / fire_target, 4),
                state_pension_income=round(gross, 2) if phase == "retired" else 0.0,
                phase=phase,
            ))

        retire_snap = next((s for s in snapshots if s.year == retire_year), None)
        death_snap  = snapshots[-1] if snapshots else None

        logger.info(
            "CountryProjectionEngine.run_path: %s FIRE=%s retire_wealth=%.0f death_wealth=%.0f",
            cfg.path_id, str(fire_year),
            retire_snap.total_wealth if retire_snap else 0,
            death_snap.total_wealth if death_snap else 0,
        )

        return CountryPathResult(
            path_id=cfg.path_id,
            label=cfg.label,
            country=cfg.country,
            years=snapshots,
            retire_year=retire_year,
            fire_year=fire_year,
            wealth_at_retirement=round(retire_snap.total_wealth if retire_snap else 0, 2),
            wealth_at_death=round(death_snap.total_wealth if death_snap else 0, 2),
            lifetime_income_tax=round(lifetime_tax, 2),
            lifetime_healthcare=round(lifetime_healthcare, 2),
            total_housing_cost=round(total_housing, 2),
            currency="GBP" if cfg.country == "uk" else "USD",
            fx_rate=cfg.fx_rate,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Comparison engine
# ─────────────────────────────────────────────────────────────────────────────


class CountryComparisonEngine:
    """
    @brief Runs both country paths and produces a comparison matrix.

    Usage::

        engine = CountryComparisonEngine(uk_macro, us_macro)
        result = engine.compare(uk_config, us_config, birth_year=1982)
    """

    def __init__(self,
                 uk_macro: GenerationalMacro,
                 us_macro: GenerationalMacro) -> None:
        """
        @brief Initialise with macro assumptions for each country.

        @param uk_macro  GenerationalMacro for the UK path.
        @param us_macro  GenerationalMacro for the US path.
        """
        self._uk_engine = CountryProjectionEngine(uk_macro)
        self._us_engine = CountryProjectionEngine(us_macro)

    def compare(
        self,
        uk_cfg: CountryPathConfig,
        us_cfg: CountryPathConfig,
        birth_year_primary: int = 1980,
        uk_estate_nrb_gbp: float = 1_000_000.0,
        uk_iht_rate: float = 0.40,
        us_estate_exemption_usd: float = 14_000_000.0,
        us_estate_rate: float = 0.40,
    ) -> CountryComparisonResult:
        """
        @brief Run both paths and compute the comparison matrix.

        @param uk_cfg                UK path configuration.
        @param us_cfg                US path configuration.
        @param birth_year_primary    Birth year of the primary person.
        @param uk_estate_nrb_gbp     UK combined NRB + RNRB allowances.
        @param uk_iht_rate           UK IHT rate.
        @param us_estate_exemption_usd  US federal estate exemption (USD).
        @param us_estate_rate        US federal estate tax rate.
        @return                      CountryComparisonResult.
        """
        uk_result = self._uk_engine.run_path(uk_cfg)
        us_result = self._us_engine.run_path(us_cfg)
        warnings: list[str] = []

        fx = uk_cfg.fx_rate

        # ── Key ages comparison ──────────────────────────────────────────────
        key_age_targets = [45, 50, 55, 60, 65, 70, 80, 90]
        key_ages: list[ComparisonKeyAge] = []
        for target_age in key_age_targets:
            yr = birth_year_primary + target_age
            uk_s = uk_result.year(yr)
            us_s = us_result.year(yr)
            if uk_s is None and us_s is None:
                continue
            uk_wealth = uk_s.total_wealth_gbp if uk_s else 0.0
            us_wealth = us_s.total_wealth / fx if us_s else 0.0  # USD → GBP
            key_ages.append(ComparisonKeyAge(
                year=yr,
                age=target_age,
                uk_wealth_gbp=round(uk_wealth, 2),
                us_wealth_gbp=round(us_wealth, 2),
                delta_gbp=round(us_wealth - uk_wealth, 2),
                uk_annual_tax=round(uk_s.income_tax if uk_s else 0, 2),
                us_annual_tax_gbp=round((us_s.income_tax / fx) if us_s else 0, 2),
                uk_healthcare=round(uk_s.healthcare_cost if uk_s else 0, 2),
                us_healthcare_gbp=round((us_s.healthcare_cost / fx) if us_s else 0, 2),
            ))

        # ── Break-even ────────────────────────────────────────────────────────
        break_even = self._find_break_even(uk_result, us_result, fx)

        # ── Estate calculations ───────────────────────────────────────────────
        uk_death = uk_result.years[-1] if uk_result.years else None
        us_death = us_result.years[-1] if us_result.years else None

        # UK estate: net of IHT on gross estate above NRB
        uk_gross = uk_death.total_wealth_gbp if uk_death else 0.0
        uk_taxable = max(0.0, uk_gross - uk_estate_nrb_gbp)
        uk_estate_net_gbp = round(uk_gross - uk_taxable * uk_iht_rate, 2)

        # US estate: net of federal estate tax
        us_gross_usd = us_death.total_wealth if us_death else 0.0
        us_taxable_usd = max(0.0, us_gross_usd - us_estate_exemption_usd)
        us_estate_net_usd = us_gross_usd - us_taxable_usd * us_estate_rate
        us_estate_net_gbp = round(us_estate_net_usd / fx, 2)

        # ── Summary deltas ────────────────────────────────────────────────────
        uk_retire = uk_result.year(uk_result.retire_year)
        us_retire = us_result.year(us_result.retire_year)
        uk_retire_gbp = uk_retire.total_wealth_gbp if uk_retire else 0.0
        us_retire_gbp = (us_retire.total_wealth / fx) if us_retire else 0.0
        us_advantage = round(us_retire_gbp - uk_retire_gbp, 2)

        uk_tax_gbp = uk_result.lifetime_income_tax
        us_tax_gbp = round(us_result.lifetime_income_tax / fx, 2)

        uk_hc_gbp = uk_result.lifetime_healthcare
        us_hc_gbp = round(us_result.lifetime_healthcare / fx, 2)

        if us_advantage > 0:
            warnings.append(
                f"US path generates £{us_advantage:,.0f} more wealth at retirement. "
                f"However, lifetime healthcare costs are £{us_hc_gbp - uk_hc_gbp:,.0f} higher "
                f"and lifetime tax is £{us_tax_gbp - uk_tax_gbp:,.0f} higher."
            )

        logger.info(
            "CountryComparisonEngine: UK_retire=£%.0f US_retire=£%.0f "
            "us_advantage=£%.0f break_even=%s",
            uk_retire_gbp, us_retire_gbp, us_advantage,
            str(break_even.break_even_year),
        )

        return CountryComparisonResult(
            uk_path=uk_result,
            us_path=us_result,
            key_ages=key_ages,
            break_even=break_even,
            uk_estate_gbp=uk_estate_net_gbp,
            us_estate_gbp=us_estate_net_gbp,
            us_advantage_at_retirement_gbp=us_advantage,
            lifetime_tax_delta_gbp=round(us_tax_gbp - uk_tax_gbp, 2),
            lifetime_healthcare_delta_gbp=round(us_hc_gbp - uk_hc_gbp, 2),
            warnings=warnings,
        )

    def _find_break_even(
        self,
        uk: CountryPathResult,
        us: CountryPathResult,
        fx: float,
    ) -> BreakEvenResult:
        """
        @brief Find the year when one path overtakes the other in GBP terms.

        @param uk  UK path result.
        @param us  US path result.
        @param fx  GBP/USD rate.
        @return    BreakEvenResult.
        """
        prev_delta: Optional[float] = None
        break_even_year: Optional[int] = None
        uk_at_bey = 0.0
        us_at_bey = 0.0

        for uk_s in uk.years:
            yr = uk_s.year
            us_s = us.year(yr)
            if us_s is None:
                continue
            uk_gbp = uk_s.total_wealth_gbp
            us_gbp = us_s.total_wealth / fx
            delta  = us_gbp - uk_gbp

            if prev_delta is not None and prev_delta * delta < 0:
                # Sign change — crossover occurred this year
                break_even_year = yr
                uk_at_bey = uk_gbp
                us_at_bey = us_gbp
                break
            prev_delta = delta

        # Determine which path led early
        first_uk = uk.years[0].total_wealth_gbp if uk.years else 0.0
        first_us = (us.years[0].total_wealth / fx) if us.years else 0.0
        leading_early = "us" if first_us > first_uk else "uk"
        leading_late  = "uk" if leading_early == "us" else "us"

        return BreakEvenResult(
            break_even_year=break_even_year,
            leading_path_early=leading_early,
            leading_path_late=leading_late,
            uk_wealth_at_bey=round(uk_at_bey, 2),
            us_wealth_at_bey=round(us_at_bey, 2),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Factory helpers — build path configs from generational_config.yaml
# ─────────────────────────────────────────────────────────────────────────────


def build_uk_path_config(cfg_dict: dict, fx_rate: float = 1.27) -> CountryPathConfig:
    """
    @brief Build the UK country path config from the generational config dict.

    @param cfg_dict  Raw dict loaded from generational_config.yaml.
    @param fx_rate   GBP/USD FX rate.
    @return          CountryPathConfig for the UK path.
    """
    g  = cfg_dict.get("generational", {})
    p  = g.get("parents", {})
    p1 = p.get("person1", {})
    p2 = p.get("person2", {})
    sa = p.get("starting_assets", {})
    uk = p.get("uk_phase", {})
    sp = p.get("social_security", {})

    # UK house: use config default or fallback
    house_gbp  = float(uk.get("house_price_gbp", 550_000))
    deposit    = float(uk.get("deposit_gbp", 275_000))
    mortgage   = house_gbp - deposit

    retire_year = int(p1.get("retire_year", 2045))
    death_year  = int(p1.get("life_expectancy", 87)) + int(p1.get("birth_year", 1980))

    uk_phase_start = int(uk.get("start_year", 2026))
    combined_gross = float(uk.get("primary_gross_gbp", 80_000)) + float(uk.get("spouse_gross_gbp", 55_000))
    annual_housing = mortgage * 0.04   # rough 4% of mortgage as annual payment

    return CountryPathConfig(
        path_id="uk_path",
        label="UK Path",
        country="uk",
        start_year=uk_phase_start,
        retire_year=retire_year,
        death_year=death_year,
        starting_wealth_gbp=float(sa.get("uk_isa_gbp", 120_000)),
        starting_pension_gbp=float(sa.get("uk_sipp_gbp", 150_000)),
        starting_property_gbp=house_gbp,
        starting_mortgage_gbp=mortgage,
        phases=[
            ParentPhaseConfig(
                start_year=uk_phase_start,
                end_year=None,
                country="uk",
                gross_income=combined_gross,
                pension_rate_employee=float(uk.get("primary_pension_rate", 0.05)),
                pension_employer_match=float(uk.get("employer_pension_rate", 0.05)),
                annual_living_cost=float(uk.get("annual_living_cost_gbp", 36_000)),
                housing_cost_annual=annual_housing,
                currency="GBP",
            )
        ],
        state_pension_annual_gbp=float(sp.get("uk_state_pension_weekly_gbp", 221.20)) * 52 * 2,
        state_pension_start_year=int(sp.get("uk_state_pension_age", 67)) + int(p1.get("birth_year", 1980)),
        fx_rate=fx_rate,
    )


def build_us_path_config(cfg_dict: dict, fx_rate: float = 1.27) -> CountryPathConfig:
    """
    @brief Build the US country path config from the generational config dict.

    Includes the high-income US phase (2026–2028, WA state) and a continuation
    in the US at moderate salary after that (assuming they stay permanently).

    @param cfg_dict  Raw dict loaded from generational_config.yaml.
    @param fx_rate   GBP/USD FX rate.
    @return          CountryPathConfig for the US path.
    """
    g  = cfg_dict.get("generational", {})
    p  = g.get("parents", {})
    p1 = p.get("person1", {})
    sa = p.get("starting_assets", {})
    us = p.get("us_phase", {})
    sp = p.get("social_security", {})

    retire_year = int(p1.get("retire_year", 2045))
    death_year  = int(p1.get("life_expectancy", 87)) + int(p1.get("birth_year", 1980))

    # US house (mid-cost city assumed)
    us_house_usd  = 900_000.0
    us_deposit    = 200_000.0
    us_mortgage   = us_house_usd - us_deposit
    us_housing_pa = us_mortgage * 0.045  # ~4.5% mortgage payment

    phases = []
    if bool(us.get("enabled", False)):
        # High-income WA phase
        phases.append(ParentPhaseConfig(
            start_year=int(us.get("start_year", 2026)),
            end_year=int(us.get("end_year", 2028)),
            country="us",
            gross_income=float(us.get("gross_salary_usd", 600_000)),
            pension_rate_employee=float(us.get("k401_employee", 23_500)) / float(us.get("gross_salary_usd", 600_000)),
            pension_employer_match=float(us.get("k401_employer_match", 10_000)) / float(us.get("gross_salary_usd", 600_000)),
            annual_living_cost=float(us.get("annual_living_cost_usd", 150_000)),
            housing_cost_annual=us_housing_pa,
            state_tax_rate=0.0,  # WA state
            currency="USD",
        ))
        continuation_start = int(us.get("end_year", 2028)) + 1
    else:
        continuation_start = int(us.get("start_year", 2026))

    # US continuation: moderate salary (~$250k combined household)
    phases.append(ParentPhaseConfig(
        start_year=continuation_start,
        end_year=None,
        country="us",
        gross_income=250_000.0,
        pension_rate_employee=0.10,
        pension_employer_match=0.04,
        annual_living_cost=120_000.0,
        housing_cost_annual=us_housing_pa,
        state_tax_rate=0.093,  # CA-equivalent tax (conservative)
        currency="USD",
    ))

    # Starting assets in USD
    uk_sipp_usd    = float(sa.get("uk_sipp_gbp", 150_000)) * fx_rate
    uk_isa_usd     = float(sa.get("uk_isa_gbp",  120_000)) * fx_rate
    us_equities    = float(sa.get("us_equities_usd", 0))
    start_portfolio = uk_isa_usd + us_equities
    start_pension   = uk_sipp_usd

    ss_monthly  = float(sp.get("us_monthly_benefit_usd", 2_300))
    ss_age      = int(sp.get("us_claim_age", 67))
    ss_start    = ss_age + int(p1.get("birth_year", 1980))

    return CountryPathConfig(
        path_id="us_path",
        label="US Path",
        country="us",
        start_year=continuation_start if not bool(us.get("enabled", False)) else int(us.get("start_year", 2026)),
        retire_year=retire_year,
        death_year=death_year,
        starting_wealth_gbp=start_portfolio / fx_rate,  # stored internally in GBP equivalent
        starting_pension_gbp=start_pension / fx_rate,
        starting_property_gbp=us_house_usd / fx_rate,
        starting_mortgage_gbp=us_mortgage / fx_rate,
        phases=phases,
        state_pension_annual_gbp=(ss_monthly * 12 * 2) / fx_rate,  # couple, converted to GBP
        state_pension_start_year=ss_start,
        fx_rate=fx_rate,
    )
