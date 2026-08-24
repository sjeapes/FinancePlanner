"""
@file advanced_planning.py
@brief Phase 5 Advanced Planning Engine for LifeLedger.

Provides four distinct planning modules, each independently callable or
combined via ``AdvancedPlanningEngine.full_report()``:

1. **SurvivorEngine** — models the financial impact of either partner's death.
   Removes the deceased's income sources, applies any survivor pension fraction,
   checks mortgage affordability on single income, calculates the recommended
   life-cover amount to bridge the gap, and returns a modified scenario ready
   for re-projection.

2. **EstateEngine** — UK IHT and US estate tax calculations.
   - UK: nil-rate band (£325k) + residence nil-rate band (£175k), couple
     transferable NRB (combined £1M before IHT), 40% on excess, 7-year
     gift taper relief, annual gifting exemption £3k/yr, SIPP outside estate.
   - US: federal lifetime exemption (~$13.61M), 40% on excess, stepped-up
     basis (no CGT on inherited assets).
   - Gifting tracker with 7-year countdown, taper-relief bands, and ROI.
   - Action list of IHT-reduction strategies.

3. **HealthcareEngine** — year-by-year healthcare cost projection by age phase.
   - UK: NHS (£0 base) + optional private health insurance + care home costs.
   - US: four phases — employer plan (working), ACA bridge (62–65), Medicare
     (65–79), late life / nursing care (80+).
   - All cost phases are configurable with their own inflation rates.

4. **RebalanceEngine** — portfolio drift monitoring and trade recommendation.
   - Per-account or global target allocation (equities / bonds / cash / property).
   - Configurable drift threshold; returns 'ok' | 'amber' | 'rebalance_needed'.
   - Calculates exact £/$ buy/sell amounts to restore target weights.
   - Glide-path: adjusts target allocation by age (reduces equities near retirement).

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

from backend.models.models import Scenario

logger = logging.getLogger("lifeledger.planning")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class SurvivorConfig:
    """
    @brief Configuration for the survivor simulation engine.

    @param household_expense_reduction_pct  Fraction by which household expenses
                                            fall after a partner dies (e.g. 0.25 = 25%).
    @param survivor_pension_fraction        Fraction of deceased's pension income
                                            that continues to the survivor (e.g. 0.50).
    @param mortgage_affordability_threshold Monthly mortgage payment as a fraction
                                            of survivor's net monthly income above
                                            which affordability is flagged (0.35 = 35%).
    @param life_cover_income_multiple       Recommended life cover as a multiple of
                                            the deceased's gross annual income (e.g. 10×).
    @param mortgage_payoff_cover            True to add outstanding mortgage balance to
                                            the recommended life cover amount.
    @param notes                            Free-text notes.
    """

    household_expense_reduction_pct: float = 0.25
    survivor_pension_fraction: float = 0.50
    mortgage_affordability_threshold: float = 0.35
    life_cover_income_multiple: float = 10.0
    mortgage_payoff_cover: bool = True
    notes: str = ""


@dataclass
class EstateConfig:
    """
    @brief Configuration for the estate / IHT engine.

    @param jurisdiction              'uk' | 'us' | 'both'.
    @param uk_nil_rate_band          UK individual NRB (£325,000 in 2024/25).
    @param uk_residence_nil_rate_band  RNRB for main residence to direct descendants.
    @param uk_iht_rate               IHT rate on excess (0.40 = 40%).
    @param uk_iht_reduced_rate       Reduced rate if ≥10% left to charity (0.36).
    @param uk_annual_gift_exemption  Tax-free gifts per donor per year (£3,000).
    @param uk_small_gift_exemption   Per-recipient small gift exemption (£250).
    @param uk_wedding_gift_parent    Gift on marriage: parent to child (£5,000).
    @param uk_sipp_outside_estate    True = SIPP excluded from estate (current rules).
    @param us_federal_exemption      US federal lifetime exemption per person ($13.61M 2024).
    @param us_estate_tax_rate        US federal estate tax rate on excess (0.40).
    @param us_annual_gift_exemption  US annual gift exclusion per recipient ($18,000 2024).
    @param charge_to_charity_pct     Fraction left to charity (triggers reduced IHT rate).
    @param gifts                     List of past gifts dicts: {date, amount, recipient, notes}.
    @param notes                     Free-text notes.
    """

    jurisdiction: str = "uk"
    uk_nil_rate_band: float = 325_000.0
    uk_residence_nil_rate_band: float = 175_000.0
    uk_iht_rate: float = 0.40
    uk_iht_reduced_rate: float = 0.36
    uk_annual_gift_exemption: float = 3_000.0
    uk_small_gift_exemption: float = 250.0
    uk_wedding_gift_parent: float = 5_000.0
    uk_sipp_outside_estate: bool = True
    us_federal_exemption: float = 13_610_000.0
    us_estate_tax_rate: float = 0.40
    us_annual_gift_exemption: float = 18_000.0
    charge_to_charity_pct: float = 0.0
    gifts: list[dict] = field(default_factory=list)
    notes: str = ""


@dataclass
class HealthcarePhase:
    """
    @brief One healthcare cost phase, defined by age range and annual cost.

    @param label              Display label (e.g. 'ACA Bridge', 'NHS + Private').
    @param start_age          Age at which this phase begins.
    @param end_age            Age at which this phase ends (inclusive).
    @param annual_cost        Annual cost in base currency.
    @param inflation_rate     Annual cost inflation (healthcare often > CPI).
    @param applies_to         List of person_ids this phase applies to.
    @param jurisdiction       'uk' | 'us' | 'generic'.
    @param notes              Free-text notes.
    """

    label: str
    start_age: int
    end_age: int
    annual_cost: float
    inflation_rate: float = 0.04
    applies_to: list[str] = field(default_factory=list)
    jurisdiction: str = "uk"
    notes: str = ""


@dataclass
class HealthcareConfig:
    """
    @brief Configuration for the healthcare cost engine.

    @param jurisdiction       Primary jurisdiction: 'uk' | 'us' | 'generic'.
    @param phases             List of HealthcarePhase objects defining costs by age.
    @param include_care_home  True to add a care home scenario in late life.
    @param care_home_start_age  Age at which care home phase begins.
    @param care_home_daily_rate  Daily residential care cost in base currency.
    @param care_home_duration_years  Number of years in care.
    @param care_home_inflation_rate  Annual care cost inflation.
    @param care_home_applies_to  List of person_ids.
    @param notes              Free-text notes.
    """

    jurisdiction: str = "uk"
    phases: list[HealthcarePhase] = field(default_factory=list)
    include_care_home: bool = True
    care_home_start_age: int = 82
    care_home_daily_rate: float = 130.0
    care_home_duration_years: int = 3
    care_home_inflation_rate: float = 0.05
    care_home_applies_to: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class AssetAllocation:
    """
    @brief Target asset allocation for one account or the whole portfolio.

    @param account_id        Account identifier ('global' for whole-portfolio target).
    @param equities_pct      Target equities allocation (0–100).
    @param bonds_pct         Target bonds allocation.
    @param cash_pct          Target cash allocation.
    @param property_pct      Target property allocation.
    @param alternatives_pct  Target alternatives / other allocation.
    @param drift_threshold   Alert threshold — % deviation before flagging.
    @param notes             Free-text notes.
    """

    account_id: str = "global"
    equities_pct: float = 80.0
    bonds_pct: float = 10.0
    cash_pct: float = 5.0
    property_pct: float = 5.0
    alternatives_pct: float = 0.0
    drift_threshold: float = 5.0
    notes: str = ""

    def __post_init__(self):
        """@brief Validate allocations sum to 100."""
        total = (self.equities_pct + self.bonds_pct + self.cash_pct
                 + self.property_pct + self.alternatives_pct)
        if abs(total - 100.0) > 0.5:
            logger.warning(
                "AssetAllocation '%s': components sum to %.1f%% (expected 100%%)",
                self.account_id, total,
            )


@dataclass
class RebalanceConfig:
    """
    @brief Configuration for the rebalancing engine.

    @param enabled               False to skip rebalancing checks.
    @param global_target         Default target allocation (applied to any account
                                  not in account_targets).
    @param account_targets       Per-account target allocations.
    @param glide_path_enabled    True to reduce equities as retirement approaches.
    @param glide_path_start_age  Age at which equity reduction begins.
    @param glide_path_end_age    Age at which target equities reaches the floor.
    @param glide_path_equity_floor  Minimum equity % at glide_path_end_age.
    @param rebalance_frequency   'annual' | 'quarterly' | 'threshold_only'.
    @param notes                 Free-text notes.
    """

    enabled: bool = True
    global_target: AssetAllocation = field(default_factory=AssetAllocation)
    account_targets: list[AssetAllocation] = field(default_factory=list)
    glide_path_enabled: bool = True
    glide_path_start_age: int = 50
    glide_path_end_age: int = 65
    glide_path_equity_floor: float = 40.0
    rebalance_frequency: str = "annual"
    notes: str = ""


@dataclass
class PlanningConfig:
    """
    @brief Root configuration for all Phase 5 advanced planning engines.

    @param survivor    SurvivorConfig.
    @param estate      EstateConfig.
    @param healthcare  HealthcareConfig.
    @param rebalance   RebalanceConfig.
    @param enabled     False to skip all planning analyses.
    @param notes       Free-text notes.
    """

    survivor: SurvivorConfig = field(default_factory=SurvivorConfig)
    estate: EstateConfig = field(default_factory=EstateConfig)
    healthcare: HealthcareConfig = field(default_factory=HealthcareConfig)
    rebalance: RebalanceConfig = field(default_factory=RebalanceConfig)
    enabled: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

# ── 1. Survivor ───────────────────────────────────────────────────────────────


@dataclass
class SurvivorIncomeImpact:
    """
    @brief One income source lost due to partner death.

    @param source_id    Income source identifier.
    @param label        Display label.
    @param annual_gross Annual gross amount lost.
    @param tax_treatment Tax treatment string.
    """
    source_id: str
    label: str
    annual_gross: float
    tax_treatment: str


@dataclass
class MortgageAffordability:
    """
    @brief Mortgage affordability check on single income.

    @param monthly_payment       Current monthly P+I payment.
    @param survivor_net_monthly  Survivor's estimated net monthly income.
    @param affordability_ratio   monthly_payment / survivor_net_monthly.
    @param is_affordable         True if ratio ≤ config threshold.
    @param monthly_shortfall     Payment minus income × threshold (0 if affordable).
    @param outstanding_balance   Current outstanding mortgage balance.
    """
    monthly_payment: float
    survivor_net_monthly: float
    affordability_ratio: float
    is_affordable: bool
    monthly_shortfall: float
    outstanding_balance: float


@dataclass
class SurvivorResult:
    """
    @brief Full survivor simulation result.

    @param deceased_person_id      ID of the deceased partner.
    @param death_year              Year of death.
    @param income_lost             List of SurvivorIncomeImpact.
    @param total_income_lost       Total gross annual income removed.
    @param survivor_gross_income   Survivor's remaining gross annual income.
    @param survivor_pension_income Survivor's continued pension income (incl. fraction).
    @param expense_reduction       Annual expense reduction after death.
    @param mortgage_affordability  MortgageAffordability analysis (None if no mortgage).
    @param recommended_life_cover  Suggested life insurance sum assured.
    @param life_cover_breakdown    Dict explaining the recommended amount.
    @param key_risks               List of identified financial risks.
    @param recommendations         List of recommended actions.
    @param warnings                Warning strings.
    """
    deceased_person_id: str
    death_year: int
    income_lost: list[SurvivorIncomeImpact]
    total_income_lost: float
    survivor_gross_income: float
    survivor_pension_income: float
    expense_reduction: float
    mortgage_affordability: Optional[MortgageAffordability]
    recommended_life_cover: float
    life_cover_breakdown: dict[str, float]
    key_risks: list[str]
    recommendations: list[str]
    warnings: list[str] = field(default_factory=list)


# ── 2. Estate ─────────────────────────────────────────────────────────────────


@dataclass
class GiftRecord:
    """
    @brief One gift made, with 7-year countdown and taper relief.

    @param gift_date          Date the gift was made.
    @param amount             Amount of the gift.
    @param recipient          Recipient name or description.
    @param years_elapsed      Years since the gift was made.
    @param is_outside_estate  True if >7 years ago (fully exempt).
    @param taper_relief_pct   IHT discount applicable (0% <3yr, 20% 3-4yr, …, 80% 6-7yr).
    @param effective_iht_rate Net IHT rate after taper (e.g. 40% × (1 - 0.80) = 8%).
    @param iht_at_risk        IHT that would be payable if donor died today.
    @param years_to_exempt    Years until the gift clears the 7-year rule.
    @param notes              Free-text notes.
    """
    gift_date: date
    amount: float
    recipient: str
    years_elapsed: float
    is_outside_estate: bool
    taper_relief_pct: float
    effective_iht_rate: float
    iht_at_risk: float
    years_to_exempt: float
    notes: str = ""


@dataclass
class EstateResult:
    """
    @brief Full estate / IHT calculation result.

    @param calculation_year       Year the calculation is performed.
    @param gross_estate           Total assets (property + investments + pensions if in estate).
    @param pension_outside_estate SIPP/pension value excluded under current rules.
    @param gifts_outside_estate   Cumulative gifts made >7 years ago.
    @param net_estate             gross_estate - pension_outside_estate - gifts_outside_estate.
    @param nrb_available          Nil-rate band available (individual + any transferred).
    @param rnrb_available         Residence nil-rate band available.
    @param total_allowances       nrb_available + rnrb_available.
    @param taxable_estate         max(0, net_estate - total_allowances).
    @param iht_liability          taxable_estate * iht_rate.
    @param net_to_beneficiaries   net_estate - iht_liability.
    @param effective_iht_rate     iht_liability / gross_estate.
    @param gift_tracker           List of GiftRecord objects.
    @param gift_iht_at_risk       Total IHT at risk from gifts made <7yr ago.
    @param annual_gift_allowance_remaining  Remaining £3k exemption for current year.
    @param iht_reduction_opportunities  List of reduction strategies with estimated saving.
    @param us_estate_tax          US federal estate tax (if jurisdiction includes 'us').
    @param warnings               Warning strings.
    """
    calculation_year: int
    gross_estate: float
    pension_outside_estate: float
    gifts_outside_estate: float
    net_estate: float
    nrb_available: float
    rnrb_available: float
    total_allowances: float
    taxable_estate: float
    iht_liability: float
    net_to_beneficiaries: float
    effective_iht_rate: float
    gift_tracker: list[GiftRecord]
    gift_iht_at_risk: float
    annual_gift_allowance_remaining: float
    iht_reduction_opportunities: list[dict]
    us_estate_tax: float
    warnings: list[str] = field(default_factory=list)


# ── 3. Healthcare ─────────────────────────────────────────────────────────────


@dataclass
class HealthcareYearRow:
    """
    @brief Healthcare costs for one person in one calendar year.

    @param year           Calendar year.
    @param person_id      Person identifier.
    @param age            Person's age.
    @param phase_label    Active healthcare phase label.
    @param annual_cost    Nominal annual cost after inflation.
    @param cumulative     Cumulative cost from the start of projection.
    @param jurisdiction   Jurisdiction for this row.
    """
    year: int
    person_id: str
    age: int
    phase_label: str
    annual_cost: float
    cumulative: float
    jurisdiction: str


@dataclass
class HealthcareResult:
    """
    @brief Full healthcare cost projection.

    @param rows                Year-by-year rows, all people combined.
    @param total_lifetime_cost Total nominal cost over the projection horizon.
    @param peak_year_cost      Highest single-year combined cost.
    @param peak_year           Calendar year of peak_year_cost.
    @param by_person           Dict person_id -> total lifetime cost.
    @param care_home_cost      Total care home scenario cost (if modelled).
    @param nhs_vs_private_saving  UK only: cost of private vs staying NHS-only.
    @param warnings            Warning strings.
    """
    rows: list[HealthcareYearRow]
    total_lifetime_cost: float
    peak_year_cost: float
    peak_year: int
    by_person: dict[str, float]
    care_home_cost: float
    nhs_vs_private_saving: float
    warnings: list[str] = field(default_factory=list)


# ── 4. Rebalancing ────────────────────────────────────────────────────────────


@dataclass
class HoldingClassification:
    """
    @brief Classification of one holding into an asset class.

    @param holding_id    Holding identifier.
    @param holding_name  Display name.
    @param value         Current market value.
    @param asset_class   'equities' | 'bonds' | 'cash' | 'property' | 'alternatives'.
    @param instrument_type  Raw instrument type from the model.
    """
    holding_id: str
    holding_name: str
    value: float
    asset_class: str
    instrument_type: str


@dataclass
class RebalanceAlert:
    """
    @brief Rebalancing alert for one account.

    @param account_id         Account identifier.
    @param account_name       Display name.
    @param total_value        Total account value.
    @param current_allocation Dict: asset_class -> current % of account.
    @param target_allocation  Dict: asset_class -> target %.
    @param drift              Dict: asset_class -> deviation from target (pp).
    @param max_drift          Maximum absolute deviation across all classes.
    @param status             'ok' | 'amber' | 'rebalance_needed'.
    @param trades_needed      Dict: asset_class -> £ amount to buy (positive) or sell (negative).
    @param holdings           List of HoldingClassification.
    @param glide_adjusted     True if target was adjusted by the glide path.
    @param warnings           Warning strings.
    """
    account_id: str
    account_name: str
    total_value: float
    current_allocation: dict[str, float]
    target_allocation: dict[str, float]
    drift: dict[str, float]
    max_drift: float
    status: str
    trades_needed: dict[str, float]
    holdings: list[HoldingClassification]
    glide_adjusted: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class RebalanceResult:
    """
    @brief Full portfolio rebalancing analysis.

    @param alerts               List of RebalanceAlert, one per investment account.
    @param global_allocation    Combined allocation across all accounts.
    @param global_target        Global target allocation (after glide path).
    @param global_drift         Global drift (combined portfolio vs target).
    @param accounts_needing_action  IDs of accounts with status != 'ok'.
    @param total_portfolio_value  Sum of all account values.
    @param warnings             Warning strings.
    """
    alerts: list[RebalanceAlert]
    global_allocation: dict[str, float]
    global_target: dict[str, float]
    global_drift: dict[str, float]
    accounts_needing_action: list[str]
    total_portfolio_value: float
    warnings: list[str] = field(default_factory=list)


# ── Master result ──────────────────────────────────────────────────────────────


@dataclass
class AdvancedPlanningReport:
    """
    @brief Combined Phase 5 report from all four planning engines.

    @param scenario_id       Source scenario identifier.
    @param survivor_james    Survivor result modelling James's death.
    @param survivor_sarah    Survivor result modelling Sarah's death.
    @param estate            Estate / IHT calculation for the current year.
    @param healthcare        Healthcare cost projection.
    @param rebalancing       Portfolio rebalancing analysis.
    @param warnings          Aggregated warnings.
    """
    scenario_id: str
    survivor_james: Optional[SurvivorResult]
    survivor_sarah: Optional[SurvivorResult]
    estate: EstateResult
    healthcare: HealthcareResult
    rebalancing: RebalanceResult
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------


class SurvivorEngine:
    """
    @brief Survivor simulation engine.

    Models the financial impact of either partner's death: removes their
    income, adjusts expenses, checks mortgage affordability, and recommends
    a life-cover amount.
    """

    def __init__(self, config: SurvivorConfig) -> None:
        """
        @brief Initialise the survivor engine.

        @param config  SurvivorConfig.
        """
        self._cfg = config
        logger.info("SurvivorEngine initialised")

    def simulate(
        self,
        scenario: Scenario,
        deceased_person_id: str,
        death_year: int,
    ) -> SurvivorResult:
        """
        @brief Model the death of one partner.

        @param scenario             Full scenario.
        @param deceased_person_id   ID of the person who dies.
        @param death_year           Calendar year of death.
        @return                     SurvivorResult.
        """
        cfg = self._cfg
        warnings: list[str] = []

        # ── Income analysis ──────────────────────────────────────────────────
        income_lost: list[SurvivorIncomeImpact] = []
        survivor_gross = 0.0
        deceased_gross = 0.0

        for isrc in scenario.income_sources:
            pid = getattr(isrc, "person_id", "")
            gross = float(getattr(isrc, "gross_annual", 0))
            tx = getattr(isrc, "tax_treatment", None)
            if tx and hasattr(tx, "value"):
                tx = tx.value

            # Skip if source has already ended before death_year
            end = getattr(isrc, "end_date", None)
            if end:
                eyr = end.year if hasattr(end, "year") else int(str(end)[:4])
                if eyr < death_year:
                    continue

            if pid == deceased_person_id:
                income_lost.append(SurvivorIncomeImpact(
                    source_id=getattr(isrc, "id", ""),
                    label=getattr(isrc, "name", ""),
                    annual_gross=gross,
                    tax_treatment=str(tx or ""),
                ))
                deceased_gross += gross
            else:
                survivor_gross += gross

        # ── Pension continuation (survivor fraction) ─────────────────────────
        survivor_pension = 0.0
        for pf in scenario.pension_funds:
            owner = getattr(pf, "owner_id", "")
            dc = getattr(pf, "drawdown_config", None)
            if owner == deceased_person_id and dc is not None:
                rate = float(getattr(dc, "rate", 0.04))
                val = float(getattr(pf, "current_value", 0))
                income = val * rate
                survivor_pension += income * cfg.survivor_pension_fraction
                logger.debug(
                    "Survivor pension from %s: £%.0f × %.0f%% = £%.0f/yr",
                    getattr(pf, "id", ""), income,
                    cfg.survivor_pension_fraction * 100, income * cfg.survivor_pension_fraction,
                )

        # ── Expense adjustment ───────────────────────────────────────────────
        total_annual_expenses = sum(
            float(getattr(b, "annual_amount", 0))
            for b in scenario.expense_buckets
            if self._is_active(b, death_year)
        )
        expense_reduction = round(total_annual_expenses * cfg.household_expense_reduction_pct, 2)

        # ── Mortgage affordability ───────────────────────────────────────────
        mortgage_aff: Optional[MortgageAffordability] = None
        for mortgage in scenario.mortgages:
            bal = float(getattr(mortgage, "current_balance", 0))
            if bal <= 0:
                continue

            # Estimate monthly P+I using current rate period
            rate_periods = getattr(mortgage, "rate_periods", [])
            annual_rate = 0.05   # fallback
            if rate_periods:
                annual_rate = float(getattr(rate_periods[0], "rate", 0.05))

            orig = float(getattr(mortgage, "original_principal", bal))
            start_d = getattr(mortgage, "start_date", None)
            term_months = 300   # 25yr fallback
            if start_d:
                syr = start_d.year if hasattr(start_d, "year") else 2020
                elapsed = max(0, (death_year - syr) * 12)
                term_months = max(12, 300 - elapsed)

            monthly_rate = annual_rate / 12
            if monthly_rate > 0:
                monthly_payment = bal * monthly_rate * (1 + monthly_rate) ** term_months / \
                                   ((1 + monthly_rate) ** term_months - 1)
            else:
                monthly_payment = bal / term_months

            # Survivor net income estimate (gross × 0.72 rough net)
            survivor_net_monthly = (survivor_gross * 0.72) / 12
            ratio = monthly_payment / survivor_net_monthly if survivor_net_monthly > 0 else 99.0
            affordable = ratio <= cfg.mortgage_affordability_threshold
            shortfall = max(0.0, monthly_payment - survivor_net_monthly * cfg.mortgage_affordability_threshold)

            mortgage_aff = MortgageAffordability(
                monthly_payment=round(monthly_payment, 2),
                survivor_net_monthly=round(survivor_net_monthly, 2),
                affordability_ratio=round(ratio, 3),
                is_affordable=affordable,
                monthly_shortfall=round(shortfall, 2),
                outstanding_balance=round(bal, 2),
            )

            if not affordable:
                warnings.append(
                    f"Mortgage affordability risk: monthly payment £{monthly_payment:,.0f} "
                    f"is {ratio:.0%} of survivor's net income "
                    f"(threshold: {cfg.mortgage_affordability_threshold:.0%}). "
                    f"Consider life cover to repay the mortgage."
                )
            break   # analyse first active mortgage only

        # ── Life cover recommendation ─────────────────────────────────────────
        income_based = deceased_gross * cfg.life_cover_income_multiple
        mortgage_element = (mortgage_aff.outstanding_balance if mortgage_aff and cfg.mortgage_payoff_cover else 0.0)
        recommended_cover = round(income_based + mortgage_element, -3)

        cover_breakdown = {
            "income_replacement": round(income_based, 2),
            "mortgage_payoff":    round(mortgage_element, 2),
            "total_recommended":  recommended_cover,
        }

        # ── Key risks & recommendations ───────────────────────────────────────
        risks: list[str] = []
        recs: list[str] = []

        if not mortgage_aff or not mortgage_aff.is_affordable:
            risks.append("Mortgage may become unaffordable on single income.")
            recs.append(f"Consider life cover of at least £{recommended_cover:,.0f} to repay mortgage.")

        if deceased_gross > 0.5 * (deceased_gross + survivor_gross):
            risks.append("Deceased was the primary earner — significant income drop.")
            recs.append(f"Review spending plan: survivor's net income ≈ £{survivor_gross * 0.72:,.0f}/yr.")

        if survivor_pension > 0:
            recs.append(
                f"Survivor will receive £{survivor_pension:,.0f}/yr from "
                f"deceased's pension ({cfg.survivor_pension_fraction:.0%} fraction)."
            )

        recs.append("Review Lasting Power of Attorney for both partners if not in place.")
        recs.append("Ensure Wills are current and reflect current asset ownership.")

        logger.info(
            "SurvivorEngine: deceased=%s year=%d income_lost=£%.0f "
            "survivor_gross=£%.0f recommended_cover=£%.0f",
            deceased_person_id, death_year, deceased_gross,
            survivor_gross, recommended_cover,
        )

        return SurvivorResult(
            deceased_person_id=deceased_person_id,
            death_year=death_year,
            income_lost=income_lost,
            total_income_lost=round(deceased_gross, 2),
            survivor_gross_income=round(survivor_gross, 2),
            survivor_pension_income=round(survivor_pension, 2),
            expense_reduction=expense_reduction,
            mortgage_affordability=mortgage_aff,
            recommended_life_cover=recommended_cover,
            life_cover_breakdown=cover_breakdown,
            key_risks=risks,
            recommendations=recs,
            warnings=warnings,
        )

    def _is_active(self, obj, year: int) -> bool:
        """
        @brief Check if an object with start/end dates is active in a given year.

        @param obj   Object with optional start_date / end_date attributes.
        @param year  Calendar year.
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


class EstateEngine:
    """
    @brief Estate and IHT calculation engine.

    Computes the IHT liability on the current estate under UK rules
    (and optionally US federal estate tax), tracks gifts and their
    7-year countdown, and lists actionable IHT reduction strategies.
    """

    # UK taper relief bands: {years_from_3: discount_%}
    _TAPER = {3: 0.20, 4: 0.40, 5: 0.60, 6: 0.80}

    def __init__(self, config: EstateConfig) -> None:
        """
        @brief Initialise the estate engine.

        @param config  EstateConfig.
        """
        self._cfg = config
        logger.info("EstateEngine initialised: jurisdiction=%s", config.jurisdiction)

    def calculate(
        self,
        scenario: Scenario,
        projection_year: Optional[int] = None,
        has_surviving_partner: bool = True,
        owns_residence: bool = True,
    ) -> EstateResult:
        """
        @brief Calculate estate value and IHT liability.

        @param scenario              Full scenario.
        @param projection_year       Year for the calculation (default: current year).
        @param has_surviving_partner True if spouse/civil partner is alive (NRB transfer).
        @param owns_residence        True if primary residence passes to direct descendants.
        @return                      EstateResult.
        """
        cfg = self._cfg
        year = projection_year or date.today().year
        warnings: list[str] = []

        # ── Estate valuation ─────────────────────────────────────────────────
        # Properties
        property_value = sum(
            float(getattr(p, "current_value", 0))
            for p in getattr(scenario, "properties", [])
        )
        # Mortgages reduce estate
        mortgage_balance = sum(
            float(getattr(m, "current_balance", 0))
            for m in getattr(scenario, "mortgages", [])
        )
        net_property = max(0.0, property_value - mortgage_balance)

        # Investment accounts + savings
        investments = sum(
            float(getattr(a, "current_value", 0))
            for a in (list(getattr(scenario, "investment_accounts", []))
                      + list(getattr(scenario, "savings_accounts", [])))
        )

        # Pensions
        pension_total = sum(
            float(getattr(pf, "current_value", 0))
            for pf in getattr(scenario, "pension_funds", [])
        )
        pension_excluded = pension_total if cfg.uk_sipp_outside_estate else 0.0

        gross_estate = round(net_property + investments + (pension_total - pension_excluded), 2)

        # ── Gift tracking ─────────────────────────────────────────────────────
        gift_tracker, gifts_outside, gift_at_risk = self._process_gifts(year, cfg)

        net_estate = max(0.0, gross_estate - gifts_outside)

        # ── Nil-rate bands ───────────────────────────────────────────────────
        nrb = cfg.uk_nil_rate_band
        rnrb = cfg.uk_residence_nil_rate_band if owns_residence else 0.0

        # Couple: surviving partner can claim unused NRB + RNRB from deceased
        if has_surviving_partner:
            nrb *= 2        # transferred NRB from deceased spouse
            rnrb *= 2       # transferred RNRB

        # RNRB tapers: £1 reduction per £2 of estate above £2M
        rnrb_taper_threshold = 2_000_000.0
        if net_estate > rnrb_taper_threshold:
            rnrb_taper = min(rnrb, (net_estate - rnrb_taper_threshold) / 2)
            rnrb = max(0.0, rnrb - rnrb_taper)

        total_allowances = nrb + rnrb
        taxable_estate = max(0.0, net_estate - total_allowances)

        # ── IHT calculation ──────────────────────────────────────────────────
        # Reduced 36% rate if ≥10% of net estate left to charity
        iht_rate = cfg.uk_iht_rate
        if cfg.charge_to_charity_pct >= 0.10:
            iht_rate = cfg.uk_iht_reduced_rate

        iht = round(taxable_estate * iht_rate, 2)
        net_to_bens = round(net_estate - iht, 2)
        effective_rate = round(iht / gross_estate, 4) if gross_estate > 0 else 0.0

        # ── Annual gift allowance remaining ──────────────────────────────────
        gifts_this_year = sum(
            float(g.get("amount", 0))
            for g in cfg.gifts
            if self._gift_year(g) == year
        )
        allowance_remaining = max(0.0, cfg.uk_annual_gift_exemption * 2
                                   - gifts_this_year)   # × 2 for couple

        # ── US estate tax ────────────────────────────────────────────────────
        us_tax = 0.0
        if "us" in cfg.jurisdiction.lower():
            us_taxable = max(0.0, gross_estate - cfg.us_federal_exemption)
            us_tax = round(us_taxable * cfg.us_estate_tax_rate, 2)

        # ── IHT reduction opportunities ───────────────────────────────────────
        opportunities = self._reduction_opportunities(
            taxable_estate, iht, pension_total, cfg, owns_residence,
            has_surviving_partner, allowance_remaining,
        )

        if taxable_estate > 0:
            warnings.append(
                f"IHT liability of £{iht:,.0f} on taxable estate of "
                f"£{taxable_estate:,.0f}. "
                f"{len(opportunities)} reduction opportunity(ies) identified."
            )

        logger.info(
            "EstateEngine: year=%d gross=£%.0f pension_excl=£%.0f "
            "allowances=£%.0f taxable=£%.0f iht=£%.0f",
            year, gross_estate, pension_excluded,
            total_allowances, taxable_estate, iht,
        )

        return EstateResult(
            calculation_year=year,
            gross_estate=gross_estate,
            pension_outside_estate=pension_excluded,
            gifts_outside_estate=round(gifts_outside, 2),
            net_estate=round(net_estate, 2),
            nrb_available=round(nrb, 2),
            rnrb_available=round(rnrb, 2),
            total_allowances=round(total_allowances, 2),
            taxable_estate=round(taxable_estate, 2),
            iht_liability=iht,
            net_to_beneficiaries=net_to_bens,
            effective_iht_rate=effective_rate,
            gift_tracker=gift_tracker,
            gift_iht_at_risk=round(gift_at_risk, 2),
            annual_gift_allowance_remaining=round(allowance_remaining, 2),
            iht_reduction_opportunities=opportunities,
            us_estate_tax=us_tax,
            warnings=warnings,
        )

    def _process_gifts(
        self, year: int, cfg: EstateConfig
    ) -> tuple[list[GiftRecord], float, float]:
        """
        @brief Process gifts from config and return tracker, outside-estate total, at-risk total.

        @param year  Reference year for age calculation.
        @param cfg   EstateConfig.
        @return      Tuple (gift_tracker, gifts_outside_estate, iht_at_risk).
        """
        tracker: list[GiftRecord] = []
        outside_total = 0.0
        at_risk_total = 0.0

        for g in cfg.gifts:
            gift_date = g.get("date")
            if isinstance(gift_date, str):
                try:
                    gift_date = date.fromisoformat(gift_date)
                except ValueError:
                    continue
            if gift_date is None:
                continue

            amount = float(g.get("amount", 0))
            recipient = str(g.get("recipient", ""))
            notes = str(g.get("notes", ""))
            years_elapsed = (date(year, 6, 30) - gift_date).days / 365.25

            is_outside = years_elapsed >= 7.0
            years_to_exempt = max(0.0, 7.0 - years_elapsed)

            # Taper relief
            taper = 0.0
            if years_elapsed >= 3 and not is_outside:
                floor_yr = int(years_elapsed)
                taper = self._TAPER.get(floor_yr, 0.80)

            effective_rate = cfg.uk_iht_rate * (1 - taper)
            iht_at_risk = round(amount * effective_rate, 2) if not is_outside else 0.0

            if is_outside:
                outside_total += amount
            else:
                at_risk_total += iht_at_risk

            tracker.append(GiftRecord(
                gift_date=gift_date,
                amount=amount,
                recipient=recipient,
                years_elapsed=round(years_elapsed, 2),
                is_outside_estate=is_outside,
                taper_relief_pct=round(taper * 100, 1),
                effective_iht_rate=round(effective_rate * 100, 2),
                iht_at_risk=iht_at_risk,
                years_to_exempt=round(years_to_exempt, 1),
                notes=notes,
            ))

        return tracker, outside_total, at_risk_total

    def _reduction_opportunities(
        self,
        taxable_estate: float,
        iht: float,
        pension_total: float,
        cfg: EstateConfig,
        owns_residence: bool,
        has_surviving_partner: bool,
        allowance_remaining: float,
    ) -> list[dict]:
        """
        @brief Generate a list of IHT reduction strategies with estimated savings.

        @param taxable_estate       Current taxable estate.
        @param iht                  Current IHT liability.
        @param pension_total        Pension value (already outside estate if SIPP).
        @param cfg                  EstateConfig.
        @param owns_residence       True if residence passes to descendants.
        @param has_surviving_partner  True if NRB already transferred.
        @param allowance_remaining  Remaining annual gift allowance.
        @return                     List of {strategy, estimated_saving, priority, notes}.
        """
        ops: list[dict] = []

        # Annual gifting
        if allowance_remaining > 0:
            saving = round(allowance_remaining * cfg.uk_iht_rate, 0)
            ops.append({
                "strategy": f"Use remaining annual gift allowance (£{allowance_remaining:,.0f})",
                "estimated_saving": saving,
                "priority": "high",
                "notes": "Tax-free each year; use it or lose it (does not carry forward beyond 1 year).",
            })

        # 7-year gifting strategy
        if taxable_estate > 0:
            max_gift = min(taxable_estate, 100_000)
            saving_7yr = round(max_gift * cfg.uk_iht_rate, 0)
            ops.append({
                "strategy": f"Gift £{max_gift:,.0f} now — fully exempt after 7 years",
                "estimated_saving": saving_7yr,
                "priority": "medium",
                "notes": "Taper relief applies at 3–7 years. Seek legal advice on gifts with reservation of benefit.",
            })

        # Charity
        if iht > 0:
            charity_gift = taxable_estate * 0.10
            saving_charity = round(iht - (taxable_estate - charity_gift) * cfg.uk_iht_reduced_rate, 0)
            ops.append({
                "strategy": "Leave ≥10% of net estate to charity",
                "estimated_saving": max(0, saving_charity),
                "priority": "low",
                "notes": f"Reduces IHT rate from 40% to 36% on remaining estate.",
            })

        # Whole-of-life insurance
        if iht > 0:
            ops.append({
                "strategy": f"Whole-of-life policy written in trust (£{iht:,.0f} sum assured)",
                "estimated_saving": iht,
                "priority": "high",
                "notes": "Covers IHT liability without reducing estate. Must be written in trust or it adds to the estate.",
            })

        # ISA → AIM / BPR shares
        if taxable_estate > 50_000:
            ops.append({
                "strategy": "Invest ISA in AIM shares qualifying for Business Property Relief (BPR)",
                "estimated_saving": round(min(taxable_estate, 50_000) * cfg.uk_iht_rate, 0),
                "priority": "medium",
                "notes": "AIM shares held for 2+ years qualify for 100% BPR — exempt from IHT. "
                         "Higher risk: seek advice.",
            })

        return sorted(ops, key=lambda x: -x.get("estimated_saving", 0))

    @staticmethod
    def _gift_year(g: dict) -> Optional[int]:
        """
        @brief Extract the year from a gift dict's date field.

        @param g  Gift dictionary with a 'date' key.
        @return   Integer year or None.
        """
        gift_date = g.get("date")
        if isinstance(gift_date, date):
            return gift_date.year
        if isinstance(gift_date, str):
            try:
                return date.fromisoformat(gift_date).year
            except ValueError:
                return None
        return None


class HealthcareEngine:
    """
    @brief Healthcare cost projection engine.

    Projects year-by-year healthcare costs for all people in the scenario,
    using configurable age-phase cost schedules and care home assumptions.
    """

    _INSTRUMENT_CLASS_MAP = {
        "ETF": "equities", "fund": "equities", "share": "equities",
        "bond": "bonds", "gilt": "bonds", "corporate_bond": "bonds",
        "cash": "cash", "money_market": "cash",
        "property_fund": "property", "reit": "property",
    }

    def __init__(self, config: HealthcareConfig) -> None:
        """
        @brief Initialise the healthcare engine.

        @param config  HealthcareConfig.
        """
        self._cfg = config
        logger.info(
            "HealthcareEngine: jurisdiction=%s phases=%d care_home=%s",
            config.jurisdiction, len(config.phases), config.include_care_home,
        )

    def project(
        self,
        scenario: Scenario,
        start_year: int,
        end_year: int,
    ) -> HealthcareResult:
        """
        @brief Project healthcare costs year by year for all people.

        @param scenario    Full scenario.
        @param start_year  First projection year.
        @param end_year    Last projection year.
        @return            HealthcareResult.
        """
        cfg = self._cfg
        rows: list[HealthcareYearRow] = []
        by_person: dict[str, float] = {}
        warnings: list[str] = []
        care_home_total = 0.0

        for person in scenario.people:
            pid = getattr(person, "id", "")
            pname = getattr(person, "name", pid)
            dob = getattr(person, "dob", None)
            if not dob:
                dob = getattr(person, "date_of_birth", None)

            byr = None
            if dob:
                byr = dob.year if hasattr(dob, "year") else int(str(dob)[:4])

            cumulative = 0.0
            by_person[pid] = 0.0

            for year in range(start_year, end_year + 1):
                age = (year - byr) if byr else 0
                phase = self._active_phase(pid, age)

                if phase is None:
                    continue

                years_since_phase_start = max(0, age - phase.start_age)
                annual_cost = round(
                    phase.annual_cost * (1 + phase.inflation_rate) ** years_since_phase_start, 2
                )
                cumulative += annual_cost
                by_person[pid] += annual_cost

                rows.append(HealthcareYearRow(
                    year=year, person_id=pid, age=age,
                    phase_label=phase.label, annual_cost=annual_cost,
                    cumulative=round(cumulative, 2),
                    jurisdiction=phase.jurisdiction,
                ))

            # Care home scenario
            if cfg.include_care_home and (not cfg.care_home_applies_to or pid in cfg.care_home_applies_to):
                if byr:
                    care_start = byr + cfg.care_home_start_age
                    for offset in range(cfg.care_home_duration_years):
                        care_yr = care_start + offset
                        if start_year <= care_yr <= end_year:
                            daily = cfg.care_home_daily_rate * (1 + cfg.care_home_inflation_rate) ** offset
                            annual = round(daily * 365, 2)
                            care_home_total += annual
                            cumulative += annual
                            by_person[pid] += annual
                            rows.append(HealthcareYearRow(
                                year=care_yr, person_id=pid,
                                age=cfg.care_home_start_age + offset,
                                phase_label="Care Home",
                                annual_cost=annual,
                                cumulative=round(cumulative, 2),
                                jurisdiction=cfg.jurisdiction,
                            ))

        # Aggregate by year for peak calculation
        year_totals: dict[int, float] = {}
        for r in rows:
            year_totals[r.year] = year_totals.get(r.year, 0) + r.annual_cost

        peak_year = max(year_totals, key=year_totals.get) if year_totals else start_year
        peak_cost = year_totals.get(peak_year, 0.0)
        total_cost = round(sum(by_person.values()), 2)

        if cfg.jurisdiction == "us":
            warnings.append(
                "US healthcare costs are highly variable. ACA bridge premiums and "
                "Medicare OOP costs are modelled as averages; actual costs depend on plan, "
                "health status, and location."
            )

        logger.info(
            "HealthcareEngine: years=%d-%d total=£%.0f peak_yr=%d peak=£%.0f",
            start_year, end_year, total_cost, peak_year, peak_cost,
        )

        return HealthcareResult(
            rows=sorted(rows, key=lambda r: (r.year, r.person_id)),
            total_lifetime_cost=total_cost,
            peak_year_cost=round(peak_cost, 2),
            peak_year=peak_year,
            by_person={k: round(v, 2) for k, v in by_person.items()},
            care_home_cost=round(care_home_total, 2),
            nhs_vs_private_saving=0.0,
            warnings=warnings,
        )

    def _active_phase(self, person_id: str, age: int) -> Optional[HealthcarePhase]:
        """
        @brief Find the active healthcare phase for a person at a given age.

        @param person_id  Person identifier.
        @param age        Person's age.
        @return           HealthcarePhase or None.
        """
        for phase in self._cfg.phases:
            applies = (not phase.applies_to) or (person_id in phase.applies_to)
            if applies and phase.start_age <= age <= phase.end_age:
                return phase
        return None


class RebalanceEngine:
    """
    @brief Portfolio rebalancing engine.

    Classifies holdings into asset classes, computes current vs target
    allocation, flags drift, and calculates trade amounts to restore targets.
    Supports a glide-path that reduces equity exposure as retirement approaches.
    """

    _CLASS_MAP: dict[str, str] = {
        "ETF": "equities", "fund": "equities", "share": "equities",
        "equity": "equities", "stock": "equities",
        "bond": "bonds", "gilt": "bonds", "corporate_bond": "bonds",
        "bond_etf": "bonds", "bond_fund": "bonds",
        "cash": "cash", "money_market": "cash", "savings": "cash",
        "property_fund": "property", "reit": "property",
        "alternatives": "alternatives", "commodity": "alternatives",
    }
    _ALL_CLASSES = ["equities", "bonds", "cash", "property", "alternatives"]

    def __init__(self, config: RebalanceConfig) -> None:
        """
        @brief Initialise the rebalancing engine.

        @param config  RebalanceConfig.
        """
        self._cfg = config
        logger.info(
            "RebalanceEngine: drift_threshold=%.1f%% glide_path=%s",
            config.global_target.drift_threshold, config.glide_path_enabled,
        )

    def analyse(
        self,
        scenario: Scenario,
        owner_age: int = 45,
    ) -> RebalanceResult:
        """
        @brief Analyse portfolio drift across all investment accounts.

        @param scenario    Full scenario.
        @param owner_age   Primary holder's age (used for glide-path adjustment).
        @return            RebalanceResult.
        """
        if not self._cfg.enabled:
            return RebalanceResult(
                alerts=[], global_allocation={c: 0.0 for c in self._ALL_CLASSES},
                global_target={c: 0.0 for c in self._ALL_CLASSES},
                global_drift={c: 0.0 for c in self._ALL_CLASSES},
                accounts_needing_action=[], total_portfolio_value=0.0,
                warnings=["Rebalancing disabled in config."],
            )

        alerts: list[RebalanceAlert] = []
        warnings: list[str] = []
        global_values: dict[str, float] = {c: 0.0 for c in self._ALL_CLASSES}
        global_total = 0.0

        for acc in scenario.investment_accounts:
            acc_id = getattr(acc, "id", "")
            acc_name = getattr(acc, "name", acc_id)
            acc_total = float(getattr(acc, "current_value", 0))

            # Classify holdings
            holdings: list[HoldingClassification] = []
            class_values: dict[str, float] = {c: 0.0 for c in self._ALL_CLASSES}

            for h in getattr(acc, "holdings", []):
                h_id = getattr(h, "id", "")
                h_name = getattr(h, "name", h_id)
                itype = str(getattr(h, "instrument_type", "")).lower()
                asset_class = self._CLASS_MAP.get(itype, "equities")

                # Determine holding value
                mode = getattr(h, "tracking_mode", None)
                if mode and hasattr(mode, "value"):
                    mode = mode.value
                if mode == "units":
                    units = float(getattr(h, "units", 0))
                    price = float(getattr(h, "price_per_unit", 0))
                    h_value = units * price
                else:
                    h_value = float(getattr(h, "current_value",
                                            getattr(h, "total_value", 0)))

                class_values[asset_class] = class_values.get(asset_class, 0) + h_value
                holdings.append(HoldingClassification(
                    holding_id=h_id, holding_name=h_name,
                    value=round(h_value, 2), asset_class=asset_class,
                    instrument_type=str(getattr(h, "instrument_type", "")),
                ))

            # If no holdings breakdown, treat whole account as equities
            if not holdings or sum(class_values.values()) < 1:
                atype = str(getattr(acc, "account_type", "ISA"))
                default_class = "cash" if "cash" in atype.lower() else "equities"
                class_values[default_class] = acc_total

            # Current allocation %
            total_classified = sum(class_values.values()) or acc_total or 1
            current_alloc = {c: round(v / total_classified * 100, 2) for c, v in class_values.items()}

            # Target allocation (glide-path adjusted)
            target, glide_adjusted = self._target_for_account(acc_id, owner_age)

            # Drift
            drift = {c: round(current_alloc.get(c, 0) - target.get(c, 0), 2) for c in self._ALL_CLASSES}
            max_drift = max(abs(d) for d in drift.values())

            threshold = self._cfg.global_target.drift_threshold
            if max_drift >= threshold * 1.5:
                status = "rebalance_needed"
            elif max_drift >= threshold * 0.75:
                status = "amber"
            else:
                status = "ok"

            # Trade amounts
            trades = {
                c: round((target.get(c, 0) - current_alloc.get(c, 0)) / 100 * acc_total, 2)
                for c in self._ALL_CLASSES
            }

            # Accumulate global
            for c in self._ALL_CLASSES:
                global_values[c] = global_values.get(c, 0) + class_values.get(c, 0)
            global_total += acc_total

            alerts.append(RebalanceAlert(
                account_id=acc_id, account_name=acc_name,
                total_value=round(acc_total, 2),
                current_allocation=current_alloc,
                target_allocation=target,
                drift=drift, max_drift=round(max_drift, 2),
                status=status, trades_needed=trades,
                holdings=holdings, glide_adjusted=glide_adjusted,
            ))

            logger.debug(
                "Rebalance %s: total=£%.0f status=%s max_drift=%.1f%%",
                acc_id, acc_total, status, max_drift,
            )

        # Global allocation
        global_total_safe = global_total or 1
        global_alloc = {c: round(v / global_total_safe * 100, 2) for c, v in global_values.items()}
        global_tgt, _ = self._target_for_account("global", owner_age)
        global_drift = {c: round(global_alloc.get(c, 0) - global_tgt.get(c, 0), 2) for c in self._ALL_CLASSES}

        needs_action = [a.account_id for a in alerts if a.status != "ok"]

        if needs_action:
            warnings.append(
                f"{len(needs_action)} account(s) need rebalancing: {needs_action}. "
                f"Review trades_needed to restore target allocation."
            )

        logger.info(
            "RebalanceEngine: %d accounts, %d need action, total=£%.0f",
            len(alerts), len(needs_action), global_total,
        )

        return RebalanceResult(
            alerts=alerts,
            global_allocation=global_alloc,
            global_target=global_tgt,
            global_drift=global_drift,
            accounts_needing_action=needs_action,
            total_portfolio_value=round(global_total, 2),
            warnings=warnings,
        )

    def _target_for_account(
        self, account_id: str, owner_age: int
    ) -> tuple[dict[str, float], bool]:
        """
        @brief Return the target allocation dict for an account, adjusted for glide path.

        @param account_id   Account identifier ('global' for the global target).
        @param owner_age    Owner's current age.
        @return             Tuple (allocation_dict, glide_adjusted).
        """
        cfg = self._cfg

        # Find account-specific target or fall back to global
        base: Optional[AssetAllocation] = None
        for at in cfg.account_targets:
            if at.account_id == account_id:
                base = at
                break
        if base is None:
            base = cfg.global_target

        target = {
            "equities":     base.equities_pct,
            "bonds":        base.bonds_pct,
            "cash":         base.cash_pct,
            "property":     base.property_pct,
            "alternatives": base.alternatives_pct,
        }

        glide_adjusted = False

        if cfg.glide_path_enabled and owner_age >= cfg.glide_path_start_age:
            glide_adjusted = True
            start_a = cfg.glide_path_start_age
            end_a = cfg.glide_path_end_age
            floor = cfg.glide_path_equity_floor
            original_eq = target["equities"]

            if owner_age >= end_a:
                target["equities"] = floor
            else:
                progress = (owner_age - start_a) / max(1, end_a - start_a)
                target["equities"] = round(original_eq - (original_eq - floor) * progress, 1)

            # Redirect reduced equity into bonds
            equity_reduction = original_eq - target["equities"]
            target["bonds"] = round(target["bonds"] + equity_reduction, 1)

        return target, glide_adjusted


# ---------------------------------------------------------------------------
# Master engine
# ---------------------------------------------------------------------------


class AdvancedPlanningEngine:
    """
    @brief Combined Phase 5 advanced planning engine.

    Runs all four sub-engines and aggregates the results into a single
    AdvancedPlanningReport.

    Usage::

        engine = AdvancedPlanningEngine(config)
        report = engine.full_report(scenario)
    """

    def __init__(self, config: PlanningConfig) -> None:
        """
        @brief Initialise with the combined planning configuration.

        @param config  PlanningConfig.
        """
        self._cfg = config
        self._survivor = SurvivorEngine(config.survivor)
        self._estate = EstateEngine(config.estate)
        self._healthcare = HealthcareEngine(config.healthcare)
        self._rebalance = RebalanceEngine(config.rebalance)
        logger.info("AdvancedPlanningEngine initialised")

    def full_report(
        self,
        scenario: Scenario,
        projection_year: Optional[int] = None,
        projection_end_year: Optional[int] = None,
    ) -> AdvancedPlanningReport:
        """
        @brief Run all four planning analyses and return a combined report.

        @param scenario             Full scenario.
        @param projection_year      Estate calculation year (default: current year).
        @param projection_end_year  Healthcare projection end year (default: +40yr).
        @return                     AdvancedPlanningReport.
        """
        year = projection_year or date.today().year
        end_year = projection_end_year or (year + 40)
        all_warnings: list[str] = []

        # People IDs
        person_ids = [getattr(p, "id", "") for p in scenario.people]
        p1 = person_ids[0] if len(person_ids) > 0 else "james"
        p2 = person_ids[1] if len(person_ids) > 1 else "sarah"

        # Owner age for rebalancing glide path
        owner_age = 45
        if scenario.people:
            dob = getattr(scenario.people[0], "dob",
                          getattr(scenario.people[0], "date_of_birth", None))
            if dob:
                byr = dob.year if hasattr(dob, "year") else int(str(dob)[:4])
                owner_age = year - byr

        # Survivor simulations (both partners)
        s1 = s2 = None
        if len(person_ids) >= 1:
            s1 = self._survivor.simulate(scenario, p1, year)
            all_warnings.extend(s1.warnings)
        if len(person_ids) >= 2:
            s2 = self._survivor.simulate(scenario, p2, year)
            all_warnings.extend(s2.warnings)

        # Estate
        estate_result = self._estate.calculate(scenario, year)
        all_warnings.extend(estate_result.warnings)

        # Healthcare
        hc_result = self._healthcare.project(scenario, year, end_year)
        all_warnings.extend(hc_result.warnings)

        # Rebalancing
        rb_result = self._rebalance.analyse(scenario, owner_age)
        all_warnings.extend(rb_result.warnings)

        return AdvancedPlanningReport(
            scenario_id=getattr(scenario, "id", "base"),
            survivor_james=s1,
            survivor_sarah=s2,
            estate=estate_result,
            healthcare=hc_result,
            rebalancing=rb_result,
            warnings=all_warnings,
        )


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def load_planning_config(path: str) -> PlanningConfig:
    """
    @brief Load a PlanningConfig from a YAML file.

    Expected top-level key: ``planning``.

    @param path  Filesystem path to the YAML config file.
    @return      Populated PlanningConfig.
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file is not valid YAML.
    """
    logger.info("Loading planning config from: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Planning config not found: %s — using defaults.", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise

    if not isinstance(raw, dict) or "planning" not in raw:
        raise ValueError(f"YAML '{path}' must have a top-level 'planning' key.")

    p = raw["planning"]

    # Survivor
    sv = p.get("survivor", {}) or {}
    survivor_cfg = SurvivorConfig(
        household_expense_reduction_pct=float(sv.get("household_expense_reduction_pct", 0.25)),
        survivor_pension_fraction=float(sv.get("survivor_pension_fraction", 0.50)),
        mortgage_affordability_threshold=float(sv.get("mortgage_affordability_threshold", 0.35)),
        life_cover_income_multiple=float(sv.get("life_cover_income_multiple", 10.0)),
        mortgage_payoff_cover=bool(sv.get("mortgage_payoff_cover", True)),
        notes=str(sv.get("notes", "")),
    )

    # Estate
    es = p.get("estate", {}) or {}
    gifts_raw = es.get("gifts", []) or []
    estate_cfg = EstateConfig(
        jurisdiction=str(es.get("jurisdiction", "uk")),
        uk_nil_rate_band=float(es.get("uk_nil_rate_band", 325_000)),
        uk_residence_nil_rate_band=float(es.get("uk_residence_nil_rate_band", 175_000)),
        uk_iht_rate=float(es.get("uk_iht_rate", 0.40)),
        uk_iht_reduced_rate=float(es.get("uk_iht_reduced_rate", 0.36)),
        uk_annual_gift_exemption=float(es.get("uk_annual_gift_exemption", 3_000)),
        uk_small_gift_exemption=float(es.get("uk_small_gift_exemption", 250)),
        uk_wedding_gift_parent=float(es.get("uk_wedding_gift_parent", 5_000)),
        uk_sipp_outside_estate=bool(es.get("uk_sipp_outside_estate", True)),
        us_federal_exemption=float(es.get("us_federal_exemption", 13_610_000)),
        us_estate_tax_rate=float(es.get("us_estate_tax_rate", 0.40)),
        us_annual_gift_exemption=float(es.get("us_annual_gift_exemption", 18_000)),
        charge_to_charity_pct=float(es.get("charge_to_charity_pct", 0.0)),
        gifts=list(gifts_raw),
        notes=str(es.get("notes", "")),
    )

    # Healthcare
    hc = p.get("healthcare", {}) or {}
    phases: list[HealthcarePhase] = []
    for ph in hc.get("phases", []):
        phases.append(HealthcarePhase(
            label=str(ph.get("label", "")),
            start_age=int(ph.get("start_age", 0)),
            end_age=int(ph.get("end_age", 99)),
            annual_cost=float(ph.get("annual_cost", 0)),
            inflation_rate=float(ph.get("inflation_rate", 0.04)),
            applies_to=list(ph.get("applies_to", [])),
            jurisdiction=str(ph.get("jurisdiction", "uk")),
            notes=str(ph.get("notes", "")),
        ))
    healthcare_cfg = HealthcareConfig(
        jurisdiction=str(hc.get("jurisdiction", "uk")),
        phases=phases,
        include_care_home=bool(hc.get("include_care_home", True)),
        care_home_start_age=int(hc.get("care_home_start_age", 82)),
        care_home_daily_rate=float(hc.get("care_home_daily_rate", 130.0)),
        care_home_duration_years=int(hc.get("care_home_duration_years", 3)),
        care_home_inflation_rate=float(hc.get("care_home_inflation_rate", 0.05)),
        care_home_applies_to=list(hc.get("care_home_applies_to", [])),
        notes=str(hc.get("notes", "")),
    )

    # Rebalance
    rb = p.get("rebalance", {}) or {}

    def _parse_alloc(d: dict, acc_id: str = "global") -> AssetAllocation:
        return AssetAllocation(
            account_id=str(d.get("account_id", acc_id)),
            equities_pct=float(d.get("equities_pct", 80)),
            bonds_pct=float(d.get("bonds_pct", 10)),
            cash_pct=float(d.get("cash_pct", 5)),
            property_pct=float(d.get("property_pct", 5)),
            alternatives_pct=float(d.get("alternatives_pct", 0)),
            drift_threshold=float(d.get("drift_threshold", 5.0)),
            notes=str(d.get("notes", "")),
        )

    global_target = _parse_alloc(rb.get("global_target", {}))
    account_targets = [_parse_alloc(a) for a in rb.get("account_targets", [])]

    rebalance_cfg = RebalanceConfig(
        enabled=bool(rb.get("enabled", True)),
        global_target=global_target,
        account_targets=account_targets,
        glide_path_enabled=bool(rb.get("glide_path_enabled", True)),
        glide_path_start_age=int(rb.get("glide_path_start_age", 50)),
        glide_path_end_age=int(rb.get("glide_path_end_age", 65)),
        glide_path_equity_floor=float(rb.get("glide_path_equity_floor", 40.0)),
        rebalance_frequency=str(rb.get("rebalance_frequency", "annual")),
        notes=str(rb.get("notes", "")),
    )

    return PlanningConfig(
        survivor=survivor_cfg,
        estate=estate_cfg,
        healthcare=healthcare_cfg,
        rebalance=rebalance_cfg,
        enabled=bool(p.get("enabled", True)),
        notes=str(p.get("notes", "")),
    )
