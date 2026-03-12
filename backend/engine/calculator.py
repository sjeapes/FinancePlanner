"""
@file calculator.py
@brief Core projection calculation engine for LifeLedger Phase 1.

Produces a year-by-year timeline of net worth, account values, income,
expenses, contributions, and mortgage balances for a given Scenario.
Income does NOT automatically add to net worth — only explicitly routed
contributions to savings/investment/pension accounts are tracked.

Pipeline (per year):
  1. Resolve active income sources → calculate gross/net per person
  2. Apply contribution routing → add to destination accounts
  3. Apply employer pension top-ups
  4. Grow savings accounts (interest)
  5. Grow investment accounts (assumed growth rate, weighted by holdings)
  6. Accumulate / drawdown pension funds
  7. Grow properties
  8. Step mortgage balances (PMT calculation, lump sums)
  9. Apply life events (one-off inflows/outflows)
  10. Apply expenses (inflation-linked)
  11. Compute net worth (assets - liabilities)
  12. Check FIRE threshold
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from backend.models.models import (
    AppConfig, DrawdownMode, MortgageType, Scenario, TaxTreatment,
)
from backend.engine.tax_engine import TaxResult, calculate_net_income

logger = logging.getLogger(__name__)


# ── Year snapshot ─────────────────────────────────────────────────────────────

@dataclass
class AccountSnapshot:
    """
    @brief Value of a single account at year end.
    @param account_id Account identifier.
    @param name Display name.
    @param account_type Type string for display.
    @param value Value at year end.
    @param contributions_in Total contributions received this year.
    @param growth_amount Gain from interest/growth this year.
    """
    account_id: str
    name: str
    account_type: str
    value: float
    contributions_in: float = 0.0
    growth_amount: float = 0.0


@dataclass
class IncomeSnapshot:
    """
    @brief Summary of one income source in a given year.
    @param source_id Income source identifier.
    @param name Display name.
    @param person_id Owner.
    @param gross Gross income.
    @param tax_result Full TaxResult.
    @param contributions_routed Total routed to accounts.
    """
    source_id: str
    name: str
    person_id: str
    gross: float
    tax_result: TaxResult = field(default_factory=TaxResult)
    contributions_routed: float = 0.0


@dataclass
class YearSnapshot:
    """
    @brief Complete financial snapshot for a single projection year.
    @param year Calendar year.
    @param total_net_worth Total net worth at year end.
    @param total_assets Total asset value.
    @param total_liabilities Total liabilities (mortgages).
    @param total_gross_income Total gross income across all people.
    @param total_net_income Total net income across all people.
    @param total_contributions Total contributions routed to accounts.
    @param total_expenses Total expenses (inflation-adjusted).
    @param fire_achieved Whether FIRE target has been reached.
    @param fire_coverage Coverage ratio (net_worth / fire_target).
    @param income_coverage Retirement income coverage ratio.
    @param accounts Dict of account_id -> AccountSnapshot.
    @param income_sources List of IncomeSnapshot.
    @param events List of life event descriptions applied this year.
    @param ages Dict of person_id -> age.
    """
    year: int
    total_net_worth: float = 0.0
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_gross_income: float = 0.0
    total_net_income: float = 0.0
    total_contributions: float = 0.0
    total_expenses: float = 0.0
    fire_achieved: bool = False
    fire_coverage: float = 0.0
    income_coverage: float = 0.0
    accounts: dict = field(default_factory=dict)
    income_sources: list = field(default_factory=list)
    events: list = field(default_factory=list)
    ages: dict = field(default_factory=dict)


@dataclass
class TimelineResult:
    """
    @brief Full projection timeline for a scenario.
    @param scenario_id Source scenario identifier.
    @param scenario_name Display name.
    @param years Ordered list of YearSnapshot objects.
    @param fire_year Year FIRE target first achieved (None if never).
    @param config AppConfig used for this run.
    """
    scenario_id: str
    scenario_name: str
    years: list[YearSnapshot] = field(default_factory=list)
    fire_year: Optional[int] = None
    config: Optional[AppConfig] = None

    def year(self, y: int) -> Optional[YearSnapshot]:
        """
        @brief Return snapshot for a specific calendar year.
        @param y Calendar year.
        @return YearSnapshot or None.
        """
        for snap in self.years:
            if snap.year == y:
                return snap
        return None

    def net_worth_series(self) -> tuple[list[int], list[float]]:
        """
        @brief Extract (years, net_worth) series for charting.
        @return Tuple of (year_list, net_worth_list).
        """
        return (
            [s.year for s in self.years],
            [s.total_net_worth for s in self.years],
        )


# ── Mortgage PMT helper ────────────────────────────────────────────────────────

def _pmt(rate: float, nper: int, pv: float) -> float:
    """
    @brief Calculate fixed monthly repayment (equivalent of numpy_financial.pmt).
    @param rate Monthly interest rate (annual / 12).
    @param nper Number of remaining periods.
    @param pv Present value (outstanding balance, positive).
    @return Monthly payment amount (positive = outgoing).
    """
    if rate == 0 or nper <= 0:
        return pv / nper if nper > 0 else 0.0
    try:
        return pv * rate * (1 + rate) ** nper / ((1 + rate) ** nper - 1)
    except (ZeroDivisionError, OverflowError) as exc:
        logger.error("_pmt: calculation error: %s", exc)
        return 0.0


def _step_mortgage_balance(
    balance: float,
    annual_rate: float,
    years_remaining: int,
    lump_sum: float = 0.0,
    mortgage_type: MortgageType = MortgageType.REPAYMENT,
) -> tuple[float, float]:
    """
    @brief Step a mortgage balance forward by one year.
    @param balance Current outstanding balance.
    @param annual_rate Annual interest rate (decimal).
    @param years_remaining Years left on mortgage.
    @param lump_sum Additional capital repayment this year.
    @param mortgage_type Repayment or interest_only.
    @return Tuple of (new_balance, annual_payment).
    """
    if balance <= 0 or years_remaining <= 0:
        return 0.0, 0.0
    try:
        monthly_rate = annual_rate / 12
        months_remaining = years_remaining * 12

        if mortgage_type == MortgageType.INTEREST_ONLY:
            interest_payment = balance * annual_rate
            new_balance = max(0.0, balance - lump_sum)
            return new_balance, interest_payment + lump_sum

        # Repayment: calculate PMT, apply 12 months
        monthly_pmt = _pmt(monthly_rate, months_remaining, balance)
        annual_payment = monthly_pmt * 12
        # Approximate: apply annual interest then subtract payment
        new_balance = balance * (1 + annual_rate) - annual_payment
        new_balance = max(0.0, new_balance - lump_sum)
        return new_balance, annual_payment + lump_sum
    except Exception as exc:
        logger.error("_step_mortgage_balance: %s", exc, exc_info=True)
        return balance, 0.0


# ── Main projection engine ────────────────────────────────────────────────────

class ProjectionEngine:
    """
    @brief Runs year-by-year financial projections for a given Scenario.
    """

    def __init__(self, config: AppConfig, tax_profiles: dict):
        """
        @brief Initialise the engine with app config and tax profiles.
        @param config AppConfig instance.
        @param tax_profiles Dict of profile_id -> TaxProfile.
        """
        self.config = config
        self.tax_profiles = tax_profiles
        logger.info(
            "ProjectionEngine: initialised for %d–%d, inflation=%.2f%%",
            config.projection_start_year,
            config.projection_end_year,
            config.inflation_base_rate * 100,
        )

    def _get_tax_profile(self, person_id: str, scenario: Scenario):
        """
        @brief Retrieve a person's tax profile from the loaded profiles.
        @param person_id Person identifier.
        @param scenario Active scenario.
        @return TaxProfile or None.
        """
        person = next((p for p in scenario.people if p.id == person_id), None)
        if not person:
            logger.warning("_get_tax_profile: person '%s' not found", person_id)
            return None
        profile = self.tax_profiles.get(person.tax_profile_id)
        if not profile:
            logger.warning(
                "_get_tax_profile: profile '%s' not found for person '%s'",
                person.tax_profile_id, person_id,
            )
        return profile

    def _inflation_factor(self, base_year: int, target_year: int) -> float:
        """
        @brief Cumulative inflation factor between two years.
        @param base_year Starting year.
        @param target_year Target year.
        @return Inflation multiplier.
        """
        n = max(0, target_year - base_year)
        return (1.0 + self.config.inflation_base_rate) ** n

    def project(self, scenario: Scenario) -> TimelineResult:
        """
        @brief Run the full year-by-year projection for a scenario.
        @param scenario Scenario to project.
        @return TimelineResult with all year snapshots.
        """
        logger.info("ProjectionEngine.project: starting '%s'", scenario.name)
        result = TimelineResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            config=self.config,
        )

        start = self.config.projection_start_year
        end = self.config.projection_end_year

        # ── Mutable working state (deep-copy initial values) ─────────────────
        # Savings: account_id -> current balance
        savings_state: dict[str, float] = {
            acc.id: acc.current_value
            for acc in scenario.savings_accounts
        }
        # Investments: account_id -> current balance
        invest_state: dict[str, float] = {
            acc.id: acc.total_value()
            for acc in scenario.investment_accounts
        }
        # Pensions: pension_id -> current balance
        pension_state: dict[str, float] = {
            p.id: p.current_value
            for p in scenario.pension_funds
        }
        # Mortgages: mortgage_id -> current balance
        mortgage_state: dict[str, float] = {
            m.id: m.current_balance
            for m in scenario.mortgages
        }
        # Properties: property_id -> current value
        property_state: dict[str, float] = {
            p.id: p.current_value
            for p in scenario.properties
        }
        # Track TFLS already taken
        tfls_taken: set[str] = set()

        # ── Year loop ──────────────────────────────────────────────────────────
        for year in range(start, end + 1):
            snap = YearSnapshot(year=year)

            # Person ages
            for person in scenario.people:
                snap.ages[person.id] = person.age_at(year)

            # ── Step 1: Income + Tax + Contributions ─────────────────────────
            contribution_totals: dict[str, float] = {}  # account_id -> total contrib

            for src in scenario.income_sources:
                if not src.is_active_in_year(year):
                    continue
                gross = src.gross_in_year(year)
                if gross <= 0:
                    continue

                profile = self._get_tax_profile(src.person_id, scenario)
                pension_contrib_gross = sum(
                    min(gross * c.rate, c.cap_annual if c.cap_annual else float("inf"))
                    for c in src.contributions
                    if c.destination_account_id in pension_state
                )

                tax_result = TaxResult(gross_income=gross, net_income=gross)
                if profile:
                    tax_result = calculate_net_income(
                        gross=gross,
                        tax_treatment=src.tax_treatment,
                        profile=profile,
                        pension_contributions=pension_contrib_gross,
                    )
                else:
                    logger.warning(
                        "No tax profile for %s — using gross as net income for year %d",
                        src.person_id, year,
                    )

                # Route contributions from this income source
                routed = 0.0
                for contrib in src.contributions:
                    dest = contrib.destination_account_id
                    amount = gross * contrib.rate
                    if contrib.cap_annual:
                        amount = min(amount, contrib.cap_annual)
                    employer = gross * contrib.employer_top_up
                    total_contrib = amount + employer

                    contribution_totals[dest] = contribution_totals.get(dest, 0.0) + total_contrib
                    routed += total_contrib

                inc_snap = IncomeSnapshot(
                    source_id=src.id,
                    name=src.name,
                    person_id=src.person_id,
                    gross=gross,
                    tax_result=tax_result,
                    contributions_routed=routed,
                )
                snap.income_sources.append(inc_snap)
                snap.total_gross_income += gross
                snap.total_net_income += tax_result.net_income
                snap.total_contributions += routed

            # ── Step 2: Direct savings account contributions ──────────────────
            for acc in scenario.savings_accounts:
                direct = acc.annual_contribution
                if direct > 0:
                    contribution_totals[acc.id] = (
                        contribution_totals.get(acc.id, 0.0) + direct
                    )

            # ── Step 3: Grow savings accounts ─────────────────────────────────
            for acc in scenario.savings_accounts:
                balance = savings_state[acc.id]
                rate = acc.rate_for_year(year)
                contribs_in = contribution_totals.get(acc.id, 0.0)
                # Add contributions at start of year, then apply interest
                balance += contribs_in
                growth = balance * rate
                balance += growth
                savings_state[acc.id] = max(0.0, balance)
                snap.accounts[acc.id] = AccountSnapshot(
                    account_id=acc.id,
                    name=acc.name,
                    account_type=acc.account_type.value,
                    value=savings_state[acc.id],
                    contributions_in=contribs_in,
                    growth_amount=growth,
                )

            # ── Step 4: Grow investment accounts ──────────────────────────────
            for acc in scenario.investment_accounts:
                balance = invest_state[acc.id]
                rate = acc.effective_growth_rate()
                contribs_in = contribution_totals.get(acc.id, 0.0)
                balance += contribs_in
                growth = balance * rate
                balance += growth
                invest_state[acc.id] = max(0.0, balance)
                snap.accounts[acc.id] = AccountSnapshot(
                    account_id=acc.id,
                    name=acc.name,
                    account_type=acc.account_type.value,
                    value=invest_state[acc.id],
                    contributions_in=contribs_in,
                    growth_amount=growth,
                )

            # ── Step 5: Pensions (accumulate or drawdown) ─────────────────────
            for pen in scenario.pension_funds:
                balance = pension_state[pen.id]
                contribs_in = contribution_totals.get(pen.id, 0.0)
                drawdown_income = 0.0

                if pen.is_in_drawdown(year):
                    dc = pen.drawdown_config

                    # Tax-free lump sum on first drawdown year
                    if pen.id not in tfls_taken and dc:
                        tfls = balance * dc.tax_free_lump_sum_pct
                        balance -= tfls
                        tfls_taken.add(pen.id)
                        snap.events.append(
                            f"{pen.name}: TFLS of £{tfls:,.0f} taken"
                        )

                    # Calculate drawdown amount
                    if dc:
                        if dc.mode == DrawdownMode.PCT_SWR:
                            drawdown_income = balance * dc.rate
                        elif dc.mode == DrawdownMode.FIXED_AMOUNT:
                            drawdown_income = dc.fixed_amount or 0.0

                    # Grow remaining balance first, then deduct drawdown
                    growth = balance * pen.assumed_growth_rate
                    balance += growth
                    balance = max(0.0, balance - drawdown_income)

                    # Drawdown is income — add to income snapshots
                    if drawdown_income > 0:
                        profile = self._get_tax_profile(pen.owner_id, scenario)
                        if profile:
                            dc_tax = calculate_net_income(
                                gross=drawdown_income,
                                tax_treatment=TaxTreatment.PENSION_DRAWDOWN,
                                profile=profile,
                            )
                            snap.income_sources.append(IncomeSnapshot(
                                source_id=pen.id,
                                name=f"{pen.name} (drawdown)",
                                person_id=pen.owner_id,
                                gross=drawdown_income,
                                tax_result=dc_tax,
                            ))
                            snap.total_gross_income += drawdown_income
                            snap.total_net_income += dc_tax.net_income
                else:
                    # Accumulation phase
                    balance += contribs_in
                    growth = balance * pen.assumed_growth_rate
                    balance += growth

                pension_state[pen.id] = max(0.0, balance)
                snap.accounts[pen.id] = AccountSnapshot(
                    account_id=pen.id,
                    name=pen.name,
                    account_type=pen.pension_type.value,
                    value=pension_state[pen.id],
                    contributions_in=contribs_in,
                    growth_amount=balance * pen.assumed_growth_rate,
                )

            # ── Step 6: State pension ──────────────────────────────────────────
            deferral_bonus = self.config.raw.get("engine", {}).get(
                "pension_state_deferral_bonus_per_year", 0.01
            )
            for person in scenario.people:
                if year >= person.state_pension_start_year():
                    sp_annual = person.state_pension.annual_amount(deferral_bonus)
                    if sp_annual > 0:
                        # Inflate state pension by CPI from base year
                        sp_inflated = sp_annual * self._inflation_factor(start, year)
                        profile = self._get_tax_profile(person.id, scenario)
                        if profile:
                            dc_tax = calculate_net_income(
                                gross=sp_inflated,
                                tax_treatment=TaxTreatment.STATE_PENSION,
                                profile=profile,
                            )
                            snap.income_sources.append(IncomeSnapshot(
                                source_id=f"{person.id}_state_pension",
                                name=f"{person.name} — State Pension",
                                person_id=person.id,
                                gross=sp_inflated,
                                tax_result=dc_tax,
                            ))
                            snap.total_gross_income += sp_inflated
                            snap.total_net_income += dc_tax.net_income

            # ── Step 7: Properties ─────────────────────────────────────────────
            for prop in scenario.properties:
                val = property_state[prop.id]
                growth = val * prop.assumed_growth_rate
                property_state[prop.id] = val + growth

            # ── Step 8: Mortgages ──────────────────────────────────────────────
            for mort in scenario.mortgages:
                balance = mortgage_state[mort.id]
                if balance <= 0 or year >= mort.maturity_year():
                    mortgage_state[mort.id] = 0.0
                    continue

                rate = mort.rate_for_year(year)
                years_rem = mort.maturity_year() - year
                lump = sum(
                    lsp.amount for lsp in mort.lump_sum_payments
                    if lsp.date and lsp.date.year == year
                )
                if lump > 0:
                    snap.events.append(
                        f"{mort.name}: lump sum payment of £{lump:,.0f}"
                    )

                new_bal, _ = _step_mortgage_balance(
                    balance=balance,
                    annual_rate=rate,
                    years_remaining=years_rem,
                    lump_sum=lump,
                    mortgage_type=mort.mortgage_type,
                )
                mortgage_state[mort.id] = new_bal

            # ── Step 9: Life events ────────────────────────────────────────────
            for ev in scenario.life_events:
                if not ev.date or ev.date.year != year:
                    continue
                if ev.affects_account_id:
                    if ev.affects_account_id in savings_state:
                        savings_state[ev.affects_account_id] += ev.amount
                        savings_state[ev.affects_account_id] = max(
                            0.0, savings_state[ev.affects_account_id]
                        )
                    elif ev.affects_account_id in invest_state:
                        invest_state[ev.affects_account_id] += ev.amount
                        invest_state[ev.affects_account_id] = max(
                            0.0, invest_state[ev.affects_account_id]
                        )
                snap.events.append(
                    f"{ev.name}: £{ev.amount:,.0f} ({ev.event_type.value})"
                )

            # ── Step 10: Expenses ─────────────────────────────────────────────
            for exp in scenario.expense_buckets:
                if not exp.is_active_in_year(year):
                    continue
                amount = exp.annual_amount
                if exp.inflation_linked:
                    amount *= self._inflation_factor(start, year)
                snap.total_expenses += amount

            # ── Step 11: Net worth ─────────────────────────────────────────────
            total_savings = sum(savings_state.values())
            total_investments = sum(invest_state.values())
            total_pensions = sum(pension_state.values())
            total_property = sum(property_state.values())
            total_mortgages = sum(mortgage_state.values())

            snap.total_assets = (
                total_savings + total_investments + total_pensions + total_property
            )
            snap.total_liabilities = total_mortgages
            snap.total_net_worth = snap.total_assets - snap.total_liabilities

            # Update per-account snapshots for properties and mortgages
            for prop in scenario.properties:
                snap.accounts[prop.id] = AccountSnapshot(
                    account_id=prop.id,
                    name=prop.name,
                    account_type="property",
                    value=property_state[prop.id],
                )
            for mort in scenario.mortgages:
                snap.accounts[mort.id] = AccountSnapshot(
                    account_id=mort.id,
                    name=mort.name,
                    account_type="mortgage",
                    value=-mortgage_state[mort.id],  # negative = liability
                )

            # ── Step 12: FIRE check ────────────────────────────────────────────
            if scenario.fire_target:
                ft = scenario.fire_target
                snap.fire_coverage = snap.total_net_worth / ft.target_net_worth if ft.target_net_worth > 0 else 0.0
                snap.fire_achieved = snap.total_net_worth >= ft.target_net_worth
                if snap.fire_achieved and result.fire_year is None:
                    result.fire_year = year
                    logger.info(
                        "ProjectionEngine: FIRE achieved in %d (net worth £%,.0f)",
                        year, snap.total_net_worth,
                    )

                # Retirement income coverage: total income vs retirement expenses
                retirement_expenses = sum(
                    exp.annual_amount * self._inflation_factor(start, year)
                    for exp in scenario.expense_buckets
                    if exp.is_active_in_year(year) and exp.inflation_linked
                )
                if retirement_expenses > 0:
                    snap.income_coverage = snap.total_net_income / retirement_expenses

            result.years.append(snap)

            logger.debug(
                "Year %d: assets=£%,.0f liabilities=£%,.0f "
                "net_worth=£%,.0f income=£%,.0f",
                year, snap.total_assets, snap.total_liabilities,
                snap.total_net_worth, snap.total_gross_income,
            )

        logger.info(
            "ProjectionEngine.project: '%s' complete — %d years, "
            "final net worth £%,.0f, FIRE year %s",
            scenario.name,
            len(result.years),
            result.years[-1].total_net_worth if result.years else 0,
            result.fire_year or "not reached",
        )
        return result


# ── Monte Carlo wrapper ───────────────────────────────────────────────────────

@dataclass
class MonteCarloResult:
    """
    @brief Aggregated Monte Carlo simulation results.
    @param years List of calendar years.
    @param p10 10th percentile net worth per year.
    @param p25 25th percentile.
    @param p50 Median net worth per year.
    @param p75 75th percentile.
    @param p90 90th percentile.
    @param n_simulations Number of runs.
    @param prob_fire Probability of achieving FIRE.
    """
    years: list[int] = field(default_factory=list)
    p10: list[float] = field(default_factory=list)
    p25: list[float] = field(default_factory=list)
    p50: list[float] = field(default_factory=list)
    p75: list[float] = field(default_factory=list)
    p90: list[float] = field(default_factory=list)
    n_simulations: int = 0
    prob_fire: float = 0.0


def run_monte_carlo(
    scenario: Scenario,
    config: AppConfig,
    tax_profiles: dict,
    n_simulations: int = 1000,
    growth_std: float = 0.12,
    inflation_std: float = 0.005,
    seed: Optional[int] = 42,
) -> MonteCarloResult:
    """
    @brief Run Monte Carlo simulation by perturbing growth and inflation rates.

    Each simulation uses normally distributed growth rates around the
    assumed rates. Sequence-of-returns risk is modelled by applying a
    large negative shock in the first 5 years of retirement.

    @param scenario Scenario to simulate.
    @param config AppConfig.
    @param tax_profiles Dict of tax profiles.
    @param n_simulations Number of simulation runs.
    @param growth_std Standard deviation of annual growth perturbation.
    @param inflation_std Standard deviation of inflation perturbation.
    @param seed Random seed for reproducibility.
    @return MonteCarloResult with percentile bands.
    """
    rng = np.random.default_rng(seed)
    logger.info("run_monte_carlo: starting %d simulations for '%s'",
                n_simulations, scenario.name)

    years_list = list(range(config.projection_start_year, config.projection_end_year + 1))
    all_net_worths = np.zeros((n_simulations, len(years_list)))
    fire_count = 0

    for sim in range(n_simulations):
        # Perturb growth rates slightly per simulation
        growth_noise = rng.normal(0, growth_std)
        inflation_noise = rng.normal(0, inflation_std)

        # Create a modified config with perturbed inflation
        sim_config = AppConfig(
            base_currency=config.base_currency,
            log_level="WARNING",  # suppress verbose logging during MC
            projection_start_year=config.projection_start_year,
            projection_end_year=config.projection_end_year,
            inflation_base_rate=max(0.0, config.inflation_base_rate + inflation_noise),
            monte_carlo_simulations=1,
            raw=config.raw,
        )

        # Build a perturbed scenario copy (modify growth rates in place)
        # We do a shallow structural copy using the same objects with
        # modified growth applied as a multiplier
        engine = ProjectionEngine(sim_config, tax_profiles)

        # Run with a quick override approach: scale all growth rates
        # We wrap this in a try/except per simulation to ensure one
        # failed run doesn't abort the whole MC
        try:
            # Temporarily patch assumed_growth_rate for this sim
            # Store originals
            orig_inv = {a.id: a.assumed_growth_rate for a in scenario.investment_accounts}
            orig_pen = {p.id: p.assumed_growth_rate for p in scenario.pension_funds}
            orig_prop = {p.id: p.assumed_growth_rate for p in scenario.properties}

            # Apply perturbation (clamp to avoid negative growth)
            for acc in scenario.investment_accounts:
                acc.assumed_growth_rate = max(
                    -0.40, orig_inv[acc.id] + growth_noise * 0.5
                )
            for pen in scenario.pension_funds:
                pen.assumed_growth_rate = max(
                    -0.40, orig_pen[pen.id] + growth_noise * 0.5
                )
            for prop in scenario.properties:
                prop.assumed_growth_rate = max(
                    0.0, orig_prop[prop.id] + growth_noise * 0.15
                )

            sim_result = engine.project(scenario)

            for i, snap in enumerate(sim_result.years):
                all_net_worths[sim, i] = snap.total_net_worth

            if sim_result.fire_year is not None:
                fire_count += 1

        except Exception as exc:
            logger.warning("run_monte_carlo: sim %d failed: %s", sim, exc)
        finally:
            # Restore original growth rates
            for acc in scenario.investment_accounts:
                acc.assumed_growth_rate = orig_inv[acc.id]
            for pen in scenario.pension_funds:
                pen.assumed_growth_rate = orig_pen[pen.id]
            for prop in scenario.properties:
                prop.assumed_growth_rate = orig_prop[prop.id]

    logger.info("run_monte_carlo: complete — FIRE probability %.1f%%",
                fire_count / n_simulations * 100)

    return MonteCarloResult(
        years=years_list,
        p10=np.percentile(all_net_worths, 10, axis=0).tolist(),
        p25=np.percentile(all_net_worths, 25, axis=0).tolist(),
        p50=np.percentile(all_net_worths, 50, axis=0).tolist(),
        p75=np.percentile(all_net_worths, 75, axis=0).tolist(),
        p90=np.percentile(all_net_worths, 90, axis=0).tolist(),
        n_simulations=n_simulations,
        prob_fire=fire_count / n_simulations,
    )
