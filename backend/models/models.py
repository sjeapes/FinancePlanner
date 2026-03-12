"""
@file models.py
@brief Core data models for LifeLedger Phase 1.

Defines all dataclass-based models that map 1:1 to the YAML schema.
Using Python dataclasses (stdlib) in place of Pydantic v2 to avoid
external dependencies; validation logic is implemented explicitly.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


# ── Enumerations ─────────────────────────────────────────────────────────────

class TaxTreatment(str, Enum):
    """Tax treatment for income sources."""
    PAYE = "PAYE"
    SELF_EMPLOYED = "self_employed"
    RENTAL = "rental"
    PENSION_DRAWDOWN = "pension_drawdown"
    STATE_PENSION = "state_pension"
    OTHER = "other"


class AccountType(str, Enum):
    """Account types for savings and investment accounts."""
    ISA = "ISA"
    LISA = "LISA"
    CASH_ISA = "cash_ISA"
    GIA = "GIA"
    K401 = "401k"
    IRA = "IRA"
    GENERAL = "general"


class PensionType(str, Enum):
    """Pension fund types."""
    SIPP = "SIPP"
    WORKPLACE_DC = "workplace_DC"
    DB = "DB"
    K401 = "401k"
    IRA = "IRA"
    STATE = "state"


class MortgageType(str, Enum):
    """Mortgage repayment structure."""
    REPAYMENT = "repayment"
    INTEREST_ONLY = "interest_only"


class TrackingMode(str, Enum):
    """Investment holding tracking mode."""
    TOTAL_VALUE = "total_value"
    UNITS = "units"


class DrawdownMode(str, Enum):
    """Pension drawdown mode."""
    PCT_SWR = "pct_swr"
    FIXED_AMOUNT = "fixed_amount"
    ANNUITY = "annuity"


class EventType(str, Enum):
    """Life event types."""
    SELL_ASSET = "sell_asset"
    BUY_ASSET = "buy_asset"
    LUMP_SUM_INCOME = "lump_sum_income"
    INHERITANCE = "inheritance"
    MAJOR_EXPENSE = "major_expense"
    REDUNDANCY = "redundancy"
    OTHER = "other"


class Jurisdiction(str, Enum):
    """Tax jurisdiction identifiers."""
    UK = "UK"
    US_FEDERAL = "US_federal"
    US_STATE = "US_state"
    IRELAND = "Ireland"
    GENERIC = "generic"


# ── Sub-models ────────────────────────────────────────────────────────────────

@dataclass
class StatePension:
    """
    @brief State pension entitlement for a person.
    @param eligible Whether eligible for state pension.
    @param qualifying_years NI qualifying years accrued.
    @param full_qualifying_years Years required for full pension.
    @param expected_start_age Age at which pension commences.
    @param weekly_amount Weekly pension amount at full entitlement.
    @param deferral_years Years of deferral (increases amount).
    """
    eligible: bool = True
    qualifying_years: int = 0
    full_qualifying_years: int = 35
    expected_start_age: int = 67
    weekly_amount: float = 221.20
    deferral_years: int = 0

    def annual_amount(self, deferral_bonus_per_year: float = 0.01) -> float:
        """
        @brief Calculate annual state pension considering qualifying years and deferral.
        @param deferral_bonus_per_year Annual percentage increase per year of deferral.
        @return Adjusted annual pension amount.
        """
        if not self.eligible:
            return 0.0
        try:
            proportion = min(self.qualifying_years / self.full_qualifying_years, 1.0)
            base = self.weekly_amount * 52 * proportion
            deferral_uplift = 1.0 + (self.deferral_years * deferral_bonus_per_year)
            return base * deferral_uplift
        except ZeroDivisionError:
            logger.error("StatePension: full_qualifying_years is 0 — check config")
            return 0.0


@dataclass
class InterestRatePeriod:
    """
    @brief A time-bounded interest / growth rate.
    @param start_date Period start (inclusive).
    @param end_date Period end (exclusive); None = open-ended.
    @param rate Annual rate as a decimal (e.g. 0.0485 = 4.85%).
    """
    start_date: date
    end_date: Optional[date]
    rate: float


@dataclass
class RatePeriod:
    """
    @brief Mortgage rate period.
    @param start_date Period start.
    @param end_date Period end; None = open-ended.
    @param rate Annual interest rate decimal.
    @param rate_type Descriptive label e.g. 'fixed', 'variable'.
    """
    start_date: date
    end_date: Optional[date]
    rate: float
    rate_type: str = "fixed"


@dataclass
class LumpSumPayment:
    """
    @brief Scheduled mortgage overpayment.
    @param date Payment date.
    @param amount Payment amount in account currency.
    @param label Human-readable label.
    """
    date: date
    amount: float
    label: str = ""


@dataclass
class Contribution:
    """
    @brief Income routing rule — fraction of gross income sent to an account.
    @param destination_account_id Target account ID.
    @param rate Fraction of gross income (e.g. 0.10 = 10%).
    @param cap_annual Maximum annual contribution (allowance cap).
    @param employer_top_up Employer match rate added on top.
    """
    destination_account_id: str
    rate: float
    cap_annual: Optional[float] = None
    employer_top_up: float = 0.0


@dataclass
class DrawdownConfig:
    """
    @brief Pension drawdown configuration.
    @param mode DrawdownMode enum value.
    @param rate Annual drawdown rate (used when mode=pct_swr).
    @param fixed_amount Annual fixed drawdown (used when mode=fixed_amount).
    @param start_date Date drawdown commences.
    @param tax_free_lump_sum_pct Fraction taken as tax-free lump sum at start.
    @param lump_sum_taken Whether TFLS has already been taken.
    """
    mode: DrawdownMode
    rate: float = 0.04
    fixed_amount: Optional[float] = None
    start_date: Optional[date] = None
    tax_free_lump_sum_pct: float = 0.25
    lump_sum_taken: bool = False


@dataclass
class SymbolLink:
    """
    @brief Market data link configuration for an investment holding.
    @param provider Data provider id (yfinance | alpha_vantage | finnhub).
    @param symbol Exchange ticker symbol.
    @param isin ISIN code for FIGI resolution.
    @param auto_refresh Whether to auto-refresh on schedule.
    @param refresh_schedule Frequency: on_app_open | daily | weekly | manual.
    @param last_fetched_at Timestamp of last successful price fetch.
    @param last_fetched_price Last successfully fetched price.
    """
    provider: str = "yfinance"
    symbol: str = ""
    isin: Optional[str] = None
    auto_refresh: bool = True
    refresh_schedule: str = "on_app_open"
    last_fetched_at: Optional[datetime] = None
    last_fetched_price: Optional[float] = None


@dataclass
class TaxBand:
    """
    @brief Single income or CGT tax band.
    @param limit Upper limit of band (None = no limit / additional rate).
    @param rate Tax rate as decimal.
    @param label Human-readable label.
    """
    limit: Optional[float]
    rate: float
    label: str = ""


# ── Primary Models ────────────────────────────────────────────────────────────

@dataclass
class Person:
    """
    @brief Represents an individual in the financial plan.
    @param id Unique identifier.
    @param name Display name.
    @param date_of_birth Used for age calculations throughout projection.
    @param retirement_age Target retirement age.
    @param life_expectancy Projection end age.
    @param tax_profile_id Reference to a TaxProfile.
    @param state_pension State pension entitlement.
    """
    id: str
    name: str
    date_of_birth: date
    retirement_age: int = 65
    life_expectancy: int = 90
    tax_profile_id: str = "uk_standard"
    state_pension: StatePension = field(default_factory=StatePension)

    def age_at(self, year: int) -> int:
        """@brief Return integer age in a given calendar year."""
        return year - self.date_of_birth.year

    def retirement_year(self) -> int:
        """@brief Return calendar year of retirement."""
        return self.date_of_birth.year + self.retirement_age

    def death_year(self) -> int:
        """@brief Return projected final year of plan."""
        return self.date_of_birth.year + self.life_expectancy

    def state_pension_start_year(self) -> int:
        """@brief Return calendar year state pension commences."""
        return self.date_of_birth.year + self.state_pension.expected_start_age


@dataclass
class IncomeSource:
    """
    @brief A single recurring income stream for a person.
    @param id Unique identifier.
    @param name Display name.
    @param person_id Owner person ID.
    @param gross_annual Gross annual amount in specified currency.
    @param currency ISO 4217 currency code.
    @param tax_treatment How this income is taxed.
    @param start_date Income commences.
    @param end_date Income ends (None = indefinite).
    @param annual_growth_rate Annual rate of increase applied each year.
    @param contributions Routing rules for savings/pension contributions.
    """
    id: str
    name: str
    person_id: str
    gross_annual: float
    currency: str = "GBP"
    tax_treatment: TaxTreatment = TaxTreatment.PAYE
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    annual_growth_rate: float = 0.0
    contributions: list[Contribution] = field(default_factory=list)

    def is_active_in_year(self, year: int) -> bool:
        """
        @brief Check whether income is active in a given year.
        @param year Calendar year to check.
        @return True if active.
        """
        try:
            if self.start_date and self.start_date.year > year:
                return False
            if self.end_date and self.end_date.year < year:
                return False
            return True
        except Exception as exc:
            logger.error("IncomeSource.is_active_in_year error for %s: %s", self.id, exc)
            return False

    def gross_in_year(self, year: int) -> float:
        """
        @brief Return inflation/growth-adjusted gross amount for a year.
        @param year Target calendar year.
        @return Adjusted gross annual amount.
        """
        if not self.is_active_in_year(year):
            return 0.0
        try:
            base_year = self.start_date.year if self.start_date else year
            n = max(0, year - base_year)
            return self.gross_annual * ((1.0 + self.annual_growth_rate) ** n)
        except Exception as exc:
            logger.error("IncomeSource.gross_in_year error for %s: %s", self.id, exc)
            return 0.0


@dataclass
class InvestmentHolding:
    """
    @brief A single holding within an investment account.
    @param id Unique identifier.
    @param name Display name.
    @param instrument_type ETF | fund | share | bond | other.
    @param tracking_mode total_value or units.
    @param total_value Current total value (total_value mode).
    @param units Number of units held (units mode).
    @param price_per_unit Price per unit (units mode).
    @param currency Holding currency.
    @param assumed_growth_rate Annual growth rate for projection.
    @param symbol_link Optional market data linkage.
    """
    id: str
    name: str
    instrument_type: str = "ETF"
    tracking_mode: TrackingMode = TrackingMode.UNITS
    total_value: Optional[float] = None
    units: Optional[float] = None
    price_per_unit: Optional[float] = None
    currency: str = "GBP"
    assumed_growth_rate: float = 0.07
    symbol_link: Optional[SymbolLink] = None

    def current_value(self) -> float:
        """
        @brief Compute current holding value based on tracking mode.
        @return Current value in holding currency.
        """
        try:
            if self.tracking_mode == TrackingMode.UNITS:
                if self.units is None or self.price_per_unit is None:
                    logger.warning("Holding %s: units/price_per_unit not set", self.id)
                    return 0.0
                return self.units * self.price_per_unit
            else:
                return self.total_value or 0.0
        except Exception as exc:
            logger.error("InvestmentHolding.current_value error for %s: %s", self.id, exc)
            return 0.0


@dataclass
class SavingsAccount:
    """
    @brief A savings or cash account with time-varying interest rates.
    @param id Unique identifier.
    @param name Display name.
    @param account_type AccountType enum.
    @param current_value Current balance.
    @param currency Account currency.
    @param owner_id Person ID of owner.
    @param interest_rate_periods List of time-bounded interest rates.
    @param annual_contribution Direct annual contribution (outside income routing).
    @param isa_allowance_used Amount of ISA allowance consumed.
    """
    id: str
    name: str
    account_type: AccountType = AccountType.GENERAL
    current_value: float = 0.0
    currency: str = "GBP"
    owner_id: str = ""
    interest_rate_periods: list[InterestRatePeriod] = field(default_factory=list)
    annual_contribution: float = 0.0
    isa_allowance_used: float = 0.0

    def rate_for_year(self, year: int) -> float:
        """
        @brief Return the applicable interest rate for a given year.
        @param year Calendar year.
        @return Interest rate as decimal; 0.0 if no matching period.
        """
        try:
            for period in reversed(self.interest_rate_periods):
                if period.start_date and period.start_date.year > year:
                    continue
                if period.end_date and period.end_date.year <= year:
                    continue
                return period.rate
            if self.interest_rate_periods:
                return self.interest_rate_periods[-1].rate
            return 0.0
        except Exception as exc:
            logger.error("SavingsAccount.rate_for_year error for %s: %s", self.id, exc)
            return 0.0


@dataclass
class InvestmentAccount:
    """
    @brief An investment account (ISA, GIA, etc.) containing holdings.
    @param id Unique identifier.
    @param name Display name.
    @param account_type Account wrapper type.
    @param current_value Current total value (sum of holdings).
    @param currency Base currency.
    @param owner_id Person ID.
    @param assumed_growth_rate Fallback growth rate if no holdings.
    @param holdings List of InvestmentHolding objects.
    """
    id: str
    name: str
    account_type: AccountType = AccountType.ISA
    current_value: float = 0.0
    currency: str = "GBP"
    owner_id: str = ""
    assumed_growth_rate: float = 0.07
    holdings: list[InvestmentHolding] = field(default_factory=list)

    def total_value(self) -> float:
        """
        @brief Sum value of all holdings (uses current_value if no holdings).
        @return Total account value.
        """
        try:
            if self.holdings:
                return sum(h.current_value() for h in self.holdings)
            return self.current_value
        except Exception as exc:
            logger.error("InvestmentAccount.total_value error for %s: %s", self.id, exc)
            return self.current_value

    def effective_growth_rate(self) -> float:
        """
        @brief Weighted average growth rate across all holdings.
        @return Weighted growth rate; falls back to assumed_growth_rate.
        """
        try:
            if not self.holdings:
                return self.assumed_growth_rate
            total = self.total_value()
            if total == 0:
                return self.assumed_growth_rate
            return sum(
                h.current_value() / total * h.assumed_growth_rate
                for h in self.holdings
            )
        except Exception as exc:
            logger.error("InvestmentAccount.effective_growth_rate error for %s: %s",
                         self.id, exc)
            return self.assumed_growth_rate


@dataclass
class PensionFund:
    """
    @brief A pension fund (SIPP, workplace DC, DB, etc.).
    @param id Unique identifier.
    @param name Display name.
    @param pension_type PensionType enum.
    @param current_value Current fund value.
    @param currency Fund currency.
    @param owner_id Person ID.
    @param assumed_growth_rate Annual growth rate during accumulation.
    @param drawdown_config Drawdown/annuity configuration.
    """
    id: str
    name: str
    pension_type: PensionType = PensionType.SIPP
    current_value: float = 0.0
    currency: str = "GBP"
    owner_id: str = ""
    assumed_growth_rate: float = 0.07
    drawdown_config: Optional[DrawdownConfig] = None

    def is_in_drawdown(self, year: int) -> bool:
        """
        @brief Whether pension is in drawdown phase in a given year.
        @param year Calendar year to check.
        @return True if drawdown has commenced.
        """
        if not self.drawdown_config or not self.drawdown_config.start_date:
            return False
        return year >= self.drawdown_config.start_date.year


@dataclass
class PropertyAsset:
    """
    @brief A property (residential or commercial).
    @param id Unique identifier.
    @param name Display name.
    @param property_type Descriptive type (residential, buy_to_let, etc.).
    @param current_value Estimated current market value.
    @param currency Property currency.
    @param owner_ids List of person IDs (joint ownership).
    @param purchase_date Date of purchase.
    @param purchase_price Original purchase price.
    @param assumed_growth_rate Annual capital growth rate.
    @param rental_income_annual Gross annual rental income (0 if primary residence).
    @param mortgage_id Linked mortgage ID (if any).
    """
    id: str
    name: str
    property_type: str = "residential"
    current_value: float = 0.0
    currency: str = "GBP"
    owner_ids: list[str] = field(default_factory=list)
    purchase_date: Optional[date] = None
    purchase_price: float = 0.0
    assumed_growth_rate: float = 0.035
    rental_income_annual: float = 0.0
    mortgage_id: Optional[str] = None


@dataclass
class Mortgage:
    """
    @brief A mortgage linked to a property.
    @param id Unique identifier.
    @param name Display name.
    @param property_id Linked PropertyAsset ID.
    @param mortgage_type Repayment or interest-only.
    @param original_principal Original loan amount.
    @param current_balance Outstanding balance.
    @param currency Loan currency.
    @param start_date Mortgage start date.
    @param term_years Total mortgage term.
    @param rate_periods List of RatePeriod objects.
    @param lump_sum_payments Scheduled overpayments.
    """
    id: str
    name: str
    property_id: str = ""
    mortgage_type: MortgageType = MortgageType.REPAYMENT
    original_principal: float = 0.0
    current_balance: float = 0.0
    currency: str = "GBP"
    start_date: Optional[date] = None
    term_years: int = 25
    rate_periods: list[RatePeriod] = field(default_factory=list)
    lump_sum_payments: list[LumpSumPayment] = field(default_factory=list)

    def rate_for_year(self, year: int) -> float:
        """
        @brief Return applicable mortgage rate for a given year.
        @param year Calendar year.
        @return Rate as decimal; 0.0 if no periods defined.
        """
        try:
            for period in reversed(self.rate_periods):
                if period.start_date and period.start_date.year > year:
                    continue
                if period.end_date and period.end_date.year <= year:
                    continue
                return period.rate
            if self.rate_periods:
                return self.rate_periods[-1].rate
            return 0.0
        except Exception as exc:
            logger.error("Mortgage.rate_for_year error for %s: %s", self.id, exc)
            return 0.0

    def maturity_year(self) -> int:
        """@brief Return year mortgage is fully repaid."""
        if not self.start_date:
            return 9999
        return self.start_date.year + self.term_years


@dataclass
class LifeEvent:
    """
    @brief A one-off financial life event.
    @param id Unique identifier.
    @param name Display name.
    @param event_type EventType enum.
    @param date Event date.
    @param amount Financial impact (positive = inflow, negative = outflow).
    @param currency Event currency.
    @param affects_account_id Account to credit/debit.
    @param probability Probability weight for Monte Carlo (0.0–1.0).
    """
    id: str
    name: str
    event_type: EventType = EventType.OTHER
    date: Optional[date] = None
    amount: float = 0.0
    currency: str = "GBP"
    affects_account_id: Optional[str] = None
    probability: float = 1.0


@dataclass
class ExpenseBucket:
    """
    @brief A recurring expense category.
    @param id Unique identifier.
    @param name Display name.
    @param annual_amount Annual cost in specified currency.
    @param currency Expense currency.
    @param applies_to List of person IDs this expense belongs to.
    @param inflation_linked Whether to inflate the amount annually.
    @param start_date Expense commences.
    @param end_date Expense ends (None = indefinite).
    """
    id: str
    name: str
    annual_amount: float = 0.0
    currency: str = "GBP"
    applies_to: list[str] = field(default_factory=list)
    inflation_linked: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    def is_active_in_year(self, year: int) -> bool:
        """
        @brief Check whether this expense bucket is active in a given year.
        @param year Calendar year.
        @return True if active.
        """
        if self.start_date and self.start_date.year > year:
            return False
        if self.end_date and self.end_date.year < year:
            return False
        return True


@dataclass
class FIRETarget:
    """
    @brief FIRE (Financial Independence, Retire Early) target parameters.
    @param target_net_worth Required net worth to achieve FIRE.
    @param annual_expenses_target Target annual expenses in retirement.
    @param swr Safe Withdrawal Rate (e.g. 0.04 = 4%).
    @param fire_type lean_fire | fire | fat_fire | coast_fire.
    """
    target_net_worth: float = 1_000_000.0
    annual_expenses_target: float = 40_000.0
    swr: float = 0.04
    fire_type: str = "fire"

    def implied_target(self) -> float:
        """
        @brief Derive implied target net worth from expenses and SWR.
        @return Implied target (expenses / SWR).
        """
        try:
            if self.swr <= 0:
                logger.error("FIRETarget: SWR must be > 0")
                return self.target_net_worth
            return self.annual_expenses_target / self.swr
        except Exception as exc:
            logger.error("FIRETarget.implied_target error: %s", exc)
            return self.target_net_worth


@dataclass
class TaxProfile:
    """
    @brief Tax profile for a jurisdiction.
    @param id Unique identifier.
    @param name Display name.
    @param jurisdiction Jurisdiction enum.
    @param income_tax_bands List of TaxBand for income tax.
    @param ni_bands National insurance / payroll tax bands.
    @param personal_allowance Personal tax-free allowance.
    @param cgt Capital gains tax configuration dict.
    @param allowances Annual contribution allowances dict.
    """
    id: str
    name: str
    jurisdiction: Jurisdiction = Jurisdiction.UK
    income_tax_bands: list[TaxBand] = field(default_factory=list)
    ni_bands: list[TaxBand] = field(default_factory=list)
    personal_allowance: float = 12570.0
    cgt: dict[str, Any] = field(default_factory=dict)
    allowances: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    """
    @brief A named financial scenario (YAML diff from base).
    @param id Unique identifier.
    @param name Display name.
    @param description Human-readable description.
    @param is_base Whether this is the base scenario.
    @param colour UI colour for graph overlay.
    @param people Override list of Person objects.
    @param income_sources Override list of IncomeSource objects.
    @param savings_accounts Override savings accounts.
    @param investment_accounts Override investment accounts.
    @param pension_funds Override pension funds.
    @param properties Override properties.
    @param mortgages Override mortgages.
    @param expense_buckets Override expense buckets.
    @param life_events Override life events.
    @param fire_target Override FIRE target.
    """
    id: str
    name: str
    description: str = ""
    is_base: bool = False
    colour: str = "#0e9aad"
    people: list[Person] = field(default_factory=list)
    income_sources: list[IncomeSource] = field(default_factory=list)
    savings_accounts: list[SavingsAccount] = field(default_factory=list)
    investment_accounts: list[InvestmentAccount] = field(default_factory=list)
    pension_funds: list[PensionFund] = field(default_factory=list)
    properties: list[PropertyAsset] = field(default_factory=list)
    mortgages: list[Mortgage] = field(default_factory=list)
    expense_buckets: list[ExpenseBucket] = field(default_factory=list)
    life_events: list[LifeEvent] = field(default_factory=list)
    fire_target: Optional[FIRETarget] = None


@dataclass
class Checkpoint:
    """
    @brief An actual recorded net worth snapshot used to anchor projections.
    @param id Unique identifier.
    @param date Date of the checkpoint.
    @param total_net_worth Actual total net worth at checkpoint date.
    @param account_values Dict of account_id -> actual value.
    @param notes Free-text annotation.
    """
    id: str
    date: date
    total_net_worth: float = 0.0
    account_values: dict[str, float] = field(default_factory=dict)
    notes: str = ""


@dataclass
class AppConfig:
    """
    @brief Top-level application configuration loaded from YAML.
    @param base_currency Default display/calculation currency.
    @param log_level Logging level string.
    @param projection_start_year Start year for all projections.
    @param projection_end_year End year for all projections.
    @param inflation_base_rate Default CPI rate.
    @param monte_carlo_simulations Number of MC simulation runs.
    @param monte_carlo_seed RNG seed for reproducibility (None = random).
    @param raw Raw dict of full config for pass-through access.
    """
    base_currency: str = "GBP"
    log_level: str = "INFO"
    projection_start_year: int = 2025
    projection_end_year: int = 2075
    inflation_base_rate: float = 0.025
    monte_carlo_simulations: int = 1000
    monte_carlo_seed: Optional[int] = 42
    raw: dict = field(default_factory=dict)
