"""
@file mortgage.py
@brief Mortgage calculation engine for LifeLedger.

Handles full amortisation scheduling, multiple rate periods (fixed/variable
transitions), lump-sum and regular overpayments, offset account modelling,
property value projection, and equity tracking across the mortgage lifetime.

All monetary values are in the base currency defined by the config unless
explicitly noted.  Results are returned as structured dataclasses so callers
can serialise to YAML, feed into the projection engine, or expose via the
FastAPI layer.

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
# Logging setup
# ---------------------------------------------------------------------------

logger = logging.getLogger("lifeledger.mortgage")


# ---------------------------------------------------------------------------
# Configuration dataclasses (mirrors YAML schema)
# ---------------------------------------------------------------------------


@dataclass
class RatePeriod:
    """
    @brief A single fixed or variable rate period within a mortgage.

    Maps 1-to-1 with a YAML ``rate_periods`` list entry.

    @param label          Human-readable label, e.g. "Initial 5-yr fix".
    @param annual_rate    Gross annual interest rate as a decimal (0.035 = 3.5%).
    @param start_date     First day this rate applies (ISO date string or date).
    @param end_date       Last day this rate applies, or None if open-ended.
    @param rate_type      'fixed' or 'variable'.  Informational only for now.
    @param notes          Optional free-text notes for this period.
    """

    label: str
    annual_rate: float
    start_date: date
    end_date: Optional[date] = None
    rate_type: str = "fixed"
    notes: str = ""


@dataclass
class Overpayment:
    """
    @brief A single overpayment event (lump sum or recurring monthly extra).

    @param date           Date the overpayment is applied (for lump sums).
    @param amount         Amount of the overpayment in base currency.
    @param overpayment_type  'lump_sum' or 'monthly_extra'.
    @param monthly_extra_start  Start date for a monthly_extra overpayment series.
    @param monthly_extra_end    End date (inclusive) for a monthly_extra series.
    @param notes          Optional free-text notes.
    """

    amount: float
    overpayment_type: str = "lump_sum"           # 'lump_sum' | 'monthly_extra'
    date: Optional[date] = None                   # for lump_sum
    monthly_extra_start: Optional[date] = None    # for monthly_extra
    monthly_extra_end: Optional[date] = None      # for monthly_extra
    notes: str = ""


@dataclass
class MortgageConfig:
    """
    @brief Root configuration for a single mortgage, loaded from YAML.

    @param mortgage_id          Unique string identifier (e.g. "primary_residence").
    @param label                Display label for the UI.
    @param property_id          Foreign key to a Property entity in the main config.
    @param original_balance     Initial loan principal in base currency.
    @param start_date           Mortgage start date.
    @param term_years           Total mortgage term in years.
    @param repayment_type       'repayment' or 'interest_only'.
    @param rate_periods         Ordered list of RatePeriod objects.
    @param overpayments         List of Overpayment objects (may be empty).
    @param offset_balance       Current balance held in an offset account (reduces
                                 interest-bearing principal).  Defaults to 0.
    @param offset_grows_at      Annual growth rate of offset balance as a decimal.
    @param annual_overpayment_cap_pct  ERC-free overpayment allowance as a
                                       percentage of original balance per year
                                       (e.g. 0.10 = 10 %).  0 = no cap enforced.
    @param currency             ISO 4217 currency code, e.g. 'GBP'.
    @param enabled              Set False to exclude from projections without
                                 deleting the config entry.
    @param notes                Free-text notes.
    """

    mortgage_id: str
    label: str
    property_id: str
    original_balance: float
    start_date: date
    term_years: int
    repayment_type: str = "repayment"           # 'repayment' | 'interest_only'
    rate_periods: list[RatePeriod] = field(default_factory=list)
    overpayments: list[Overpayment] = field(default_factory=list)
    offset_balance: float = 0.0
    offset_grows_at: float = 0.0
    annual_overpayment_cap_pct: float = 0.10
    currency: str = "GBP"
    enabled: bool = True
    notes: str = ""


@dataclass
class PropertyConfig:
    """
    @brief Property value projection configuration.

    @param property_id        Unique identifier matching a MortgageConfig.property_id.
    @param label              Display label.
    @param purchase_price     Original purchase price in base currency.
    @param current_value      Current estimated market value.
    @param annual_growth_rate Assumed annual house price growth as a decimal.
    @param purchase_date      Date of purchase.
    @param currency           ISO 4217 currency code.
    @param notes              Free-text notes.
    """

    property_id: str
    label: str
    purchase_price: float
    current_value: float
    annual_growth_rate: float = 0.03
    purchase_date: Optional[date] = None
    currency: str = "GBP"
    notes: str = ""


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AmortisationRow:
    """
    @brief One month of the amortisation schedule.

    @param period_number     1-based month index from mortgage start.
    @param payment_date      Date this payment falls due.
    @param opening_balance   Balance at the start of this month.
    @param scheduled_payment Standard contractual monthly payment.
    @param overpayment       Any extra payment applied this month.
    @param total_payment     scheduled_payment + overpayment.
    @param interest_charge   Interest charged on the effective balance this month.
    @param principal_paid    Portion of payment reducing the balance.
    @param closing_balance   Balance after all payments this month.
    @param annual_rate       Interest rate in effect this month (decimal).
    @param offset_balance    Offset account balance this month (if applicable).
    @param effective_balance Opening balance minus offset_balance.
    """

    period_number: int
    payment_date: date
    opening_balance: float
    scheduled_payment: float
    overpayment: float
    total_payment: float
    interest_charge: float
    principal_paid: float
    closing_balance: float
    annual_rate: float
    offset_balance: float
    effective_balance: float


@dataclass
class AnnualSummary:
    """
    @brief Annual rollup of amortisation data for use in the projection engine.

    @param year                  Calendar year.
    @param opening_balance       Balance on 1 Jan (or mortgage start if first year).
    @param closing_balance       Balance on 31 Dec (or payoff date).
    @param total_interest_paid   Cumulative interest charged during the year.
    @param total_principal_paid  Cumulative principal reduction during the year.
    @param total_overpayments    Cumulative overpayments during the year.
    @param scheduled_payments    Sum of contractual payments during the year.
    @param monthly_payment       Contractual monthly payment at year-end rate.
    @param annual_rate           Interest rate at the end of the year.
    @param property_value        Projected property value at year-end.
    @param equity                property_value minus closing_balance.
    @param ltv                   Loan-to-value ratio at year-end (0–1).
    @param mortgage_active       False if the mortgage was fully repaid in or before
                                  this year.
    """

    year: int
    opening_balance: float
    closing_balance: float
    total_interest_paid: float
    total_principal_paid: float
    total_overpayments: float
    scheduled_payments: float
    monthly_payment: float
    annual_rate: float
    property_value: float
    equity: float
    ltv: float
    mortgage_active: bool


@dataclass
class MortgageResult:
    """
    @brief Top-level result object returned by MortgageEngine.run().

    @param mortgage_id          Mirrors MortgageConfig.mortgage_id.
    @param schedule             Full month-by-month amortisation schedule.
    @param annual_summaries     Year-by-year rollup for the projection engine.
    @param total_interest       Total interest paid over the full term.
    @param total_cost           total_interest + original_balance.
    @param actual_term_months   Number of months until fully repaid (may be shorter
                                 than contracted if overpayments applied).
    @param payoff_date          Date the mortgage reaches zero balance.
    @param warnings             List of warning strings (e.g. cap breaches).
    """

    mortgage_id: str
    schedule: list[AmortisationRow]
    annual_summaries: list[AnnualSummary]
    total_interest: float
    total_cost: float
    actual_term_months: int
    payoff_date: date
    warnings: list[str]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MortgageEngine:
    """
    @brief Core mortgage calculation engine.

    Constructs a full amortisation schedule respecting multiple rate periods,
    lump-sum and monthly overpayments, and an optional offset account.  Produces
    both a month-by-month schedule and annual summaries for use by the projection
    engine.

    Usage::

        engine = MortgageEngine(mortgage_cfg, property_cfg)
        result = engine.run()
    """

    # Tolerance below which the balance is considered zero (£ pence)
    BALANCE_ZERO_THRESHOLD: float = 0.005

    def __init__(
        self,
        mortgage_config: MortgageConfig,
        property_config: Optional[PropertyConfig] = None,
    ) -> None:
        """
        @brief Initialise the engine with config objects.

        @param mortgage_config  Populated MortgageConfig dataclass.
        @param property_config  Optional PropertyConfig for equity calculations.
                                If omitted, property values are reported as 0.
        @raises ValueError      If the mortgage config fails basic validation.
        """
        self._cfg = mortgage_config
        self._prop = property_config
        self._validate_config()
        logger.info(
            "MortgageEngine initialised: id=%s label='%s' balance=%.2f term=%d yrs",
            self._cfg.mortgage_id,
            self._cfg.label,
            self._cfg.original_balance,
            self._cfg.term_years,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> MortgageResult:
        """
        @brief Execute the full amortisation calculation.

        Iterates month by month from mortgage start date to either the scheduled
        end date or the month the balance reaches zero (whichever comes first).
        Overpayments are applied and the annual overpayment cap is tracked.

        @return MortgageResult containing schedule, summaries, and metadata.
        @raises RuntimeError    If the schedule fails to converge (balance never
                                 reaches zero within 600 months).
        """
        logger.info("Running amortisation for mortgage_id=%s", self._cfg.mortgage_id)

        schedule: list[AmortisationRow] = []
        warnings: list[str] = []

        balance = self._cfg.original_balance
        offset = self._cfg.offset_balance
        max_months = self._cfg.term_years * 12

        # Track overpayments per calendar year for cap enforcement
        yearly_overpayments: dict[int, float] = {}

        current_date = self._first_payment_date()
        period = 0
        payoff_date = current_date

        for month_idx in range(1, max_months + 2):
            if balance < self.BALANCE_ZERO_THRESHOLD:
                payoff_date = current_date
                logger.debug("Balance zeroed at period %d (%s)", month_idx - 1, current_date)
                break

            if month_idx > max_months + 1:
                msg = (
                    f"Mortgage {self._cfg.mortgage_id} did not reach zero balance "
                    f"within {max_months + 1} months — check config."
                )
                logger.error(msg)
                raise RuntimeError(msg)

            period += 1
            annual_rate = self._rate_for_date(current_date)
            monthly_rate = annual_rate / 12.0

            # Offset reduces the interest-bearing balance
            effective_balance = max(0.0, balance - offset)

            # Scheduled payment recalculated at each rate change for repayment
            scheduled_payment = self._scheduled_payment(
                balance, annual_rate, max_months - (period - 1)
            )

            # Interest on effective balance
            if self._cfg.repayment_type == "interest_only":
                interest_charge = effective_balance * monthly_rate
                principal_from_scheduled = 0.0
            else:
                interest_charge = effective_balance * monthly_rate
                principal_from_scheduled = max(0.0, scheduled_payment - interest_charge)

            # Overpayment for this month
            year = current_date.year
            overpayment_amount = self._overpayment_for_month(current_date)

            # Cap enforcement
            if self._cfg.annual_overpayment_cap_pct > 0:
                cap = self._cfg.original_balance * self._cfg.annual_overpayment_cap_pct
                used = yearly_overpayments.get(year, 0.0)
                headroom = max(0.0, cap - used)
                if overpayment_amount > headroom:
                    msg = (
                        f"{current_date}: overpayment £{overpayment_amount:,.2f} "
                        f"exceeds remaining cap £{headroom:,.2f} for {year}. "
                        f"Capped at £{headroom:,.2f}."
                    )
                    logger.warning(msg)
                    warnings.append(msg)
                    overpayment_amount = headroom

            yearly_overpayments[year] = yearly_overpayments.get(year, 0.0) + overpayment_amount

            # Cap overpayment so we don't overshoot zero
            overpayment_amount = min(overpayment_amount, max(0.0, balance - principal_from_scheduled))

            total_payment = scheduled_payment + overpayment_amount
            principal_paid = principal_from_scheduled + overpayment_amount
            closing_balance = max(0.0, balance - principal_paid)

            # Offset grows each month (annual rate / 12)
            offset = offset * (1 + self._cfg.offset_grows_at / 12.0)

            row = AmortisationRow(
                period_number=period,
                payment_date=current_date,
                opening_balance=round(balance, 2),
                scheduled_payment=round(scheduled_payment, 2),
                overpayment=round(overpayment_amount, 2),
                total_payment=round(total_payment, 2),
                interest_charge=round(interest_charge, 2),
                principal_paid=round(principal_paid, 2),
                closing_balance=round(closing_balance, 2),
                annual_rate=annual_rate,
                offset_balance=round(offset, 2),
                effective_balance=round(effective_balance, 2),
            )
            schedule.append(row)

            balance = closing_balance
            current_date = self._next_month(current_date)

        if not schedule:
            raise RuntimeError(f"Mortgage {self._cfg.mortgage_id}: empty schedule generated.")

        payoff_date = schedule[-1].payment_date
        actual_term_months = len(schedule)
        total_interest = round(sum(r.interest_charge for r in schedule), 2)
        total_cost = round(total_interest + self._cfg.original_balance, 2)

        annual_summaries = self._build_annual_summaries(schedule)

        logger.info(
            "Amortisation complete: periods=%d payoff=%s total_interest=%.2f",
            actual_term_months,
            payoff_date,
            total_interest,
        )

        return MortgageResult(
            mortgage_id=self._cfg.mortgage_id,
            schedule=schedule,
            annual_summaries=annual_summaries,
            total_interest=total_interest,
            total_cost=total_cost,
            actual_term_months=actual_term_months,
            payoff_date=payoff_date,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_config(self) -> None:
        """
        @brief Sanity-check the MortgageConfig before running.

        @raises ValueError  On any fatal configuration error.
        """
        cfg = self._cfg
        errors: list[str] = []

        if cfg.original_balance <= 0:
            errors.append(f"original_balance must be > 0, got {cfg.original_balance}")
        if cfg.term_years <= 0:
            errors.append(f"term_years must be > 0, got {cfg.term_years}")
        if cfg.repayment_type not in ("repayment", "interest_only"):
            errors.append(f"repayment_type must be 'repayment' or 'interest_only', got '{cfg.repayment_type}'")
        if not cfg.rate_periods:
            errors.append("rate_periods must contain at least one entry")
        for rp in cfg.rate_periods:
            if rp.annual_rate < 0 or rp.annual_rate > 1:
                errors.append(
                    f"rate_period '{rp.label}': annual_rate {rp.annual_rate} is outside [0, 1]"
                )
        if cfg.offset_balance < 0:
            errors.append(f"offset_balance must be >= 0, got {cfg.offset_balance}")
        if cfg.annual_overpayment_cap_pct < 0 or cfg.annual_overpayment_cap_pct > 1:
            errors.append(
                f"annual_overpayment_cap_pct must be in [0, 1], got {cfg.annual_overpayment_cap_pct}"
            )

        if errors:
            msg = f"MortgageConfig validation failed for '{cfg.mortgage_id}': " + "; ".join(errors)
            logger.error(msg)
            raise ValueError(msg)

    def _first_payment_date(self) -> date:
        """
        @brief Return the date of the first monthly payment.

        Convention: payments fall on the same day-of-month as the start date,
        one month after drawdown.

        @return date of first payment.
        """
        start = self._cfg.start_date
        month = start.month + 1
        year = start.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(start.day, self._days_in_month(year, month))
        return date(year, month, day)

    @staticmethod
    def _next_month(d: date) -> date:
        """
        @brief Advance a date by one calendar month, clamping to month-end.

        @param d  Input date.
        @return   Date one month later.
        """
        month = d.month + 1
        year = d.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(d.day, MortgageEngine._days_in_month(year, month))
        return date(year, month, day)

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        """
        @brief Return the number of days in a given month.

        @param year   Calendar year.
        @param month  Calendar month (1–12).
        @return       Day count.
        """
        if month == 12:
            return (date(year + 1, 1, 1) - date(year, 12, 1)).days
        return (date(year, month + 1, 1) - date(year, month, 1)).days

    def _rate_for_date(self, d: date) -> float:
        """
        @brief Resolve the applicable annual interest rate for a given date.

        Iterates rate_periods in order.  The last period with a start_date <=
        d and either no end_date or end_date >= d wins.  Falls back to the
        final rate period if no period explicitly covers the date (handles
        open-ended revert-to-SVR periods).

        @param d  Payment date to look up.
        @return   Annual interest rate as a decimal.
        """
        applicable: Optional[RatePeriod] = None
        for rp in self._cfg.rate_periods:
            if rp.start_date <= d:
                if rp.end_date is None or rp.end_date >= d:
                    applicable = rp

        if applicable is None:
            # Fall back to last period (open-ended SVR)
            applicable = self._cfg.rate_periods[-1]
            logger.debug(
                "No rate period matched %s; falling back to '%s'",
                d,
                applicable.label,
            )

        return applicable.annual_rate

    def _scheduled_payment(
        self, balance: float, annual_rate: float, remaining_months: int
    ) -> float:
        """
        @brief Compute the standard amortising monthly payment.

        Uses the standard annuity formula.  For interest-only mortgages returns
        only the monthly interest.  Returns the full balance if fewer than 1
        month remains.

        @param balance          Current outstanding principal.
        @param annual_rate      Current annual interest rate as a decimal.
        @param remaining_months Months remaining in the term.
        @return                 Monthly payment amount.
        """
        if self._cfg.repayment_type == "interest_only":
            return round(balance * (annual_rate / 12.0), 2)

        if remaining_months <= 0:
            return round(balance, 2)

        monthly_rate = annual_rate / 12.0
        if monthly_rate == 0:
            return round(balance / remaining_months, 2)

        payment = balance * (monthly_rate * (1 + monthly_rate) ** remaining_months) / (
            (1 + monthly_rate) ** remaining_months - 1
        )
        return round(payment, 2)

    def _overpayment_for_month(self, d: date) -> float:
        """
        @brief Return the total overpayment amount due in a given month.

        Sums:
        - Any lump-sum overpayment whose date falls within this month.
        - Any monthly_extra overpayment whose date range covers this month.

        @param d  First day of the payment month.
        @return   Total overpayment for the month.
        """
        total = 0.0
        for op in self._cfg.overpayments:
            if op.overpayment_type == "lump_sum" and op.date is not None:
                if op.date.year == d.year and op.date.month == d.month:
                    total += op.amount
            elif op.overpayment_type == "monthly_extra":
                start = op.monthly_extra_start or date.min
                end = op.monthly_extra_end or date.max
                if start <= d <= end:
                    total += op.amount
        return total

    def _property_value_at_year_end(self, year: int) -> float:
        """
        @brief Project property value at 31 December of a given year.

        Uses the PropertyConfig annual_growth_rate compounded from purchase_date
        (or mortgage start_date if purchase_date is not set).

        @param year  Calendar year to project to.
        @return      Projected property value, or 0.0 if no PropertyConfig.
        """
        if self._prop is None:
            return 0.0

        base_value = self._prop.current_value
        base_date = self._prop.purchase_date or self._cfg.start_date
        years_elapsed = year - base_date.year
        if years_elapsed < 0:
            return base_value
        return round(base_value * (1 + self._prop.annual_growth_rate) ** years_elapsed, 2)

    def _build_annual_summaries(
        self, schedule: list[AmortisationRow]
    ) -> list[AnnualSummary]:
        """
        @brief Roll up the monthly schedule into year-by-year summaries.

        @param schedule  Full amortisation schedule produced by run().
        @return          List of AnnualSummary, one per calendar year spanned.
        """
        if not schedule:
            return []

        summaries: list[AnnualSummary] = []
        years = sorted({r.payment_date.year for r in schedule})

        for year in years:
            rows = [r for r in schedule if r.payment_date.year == year]
            opening = rows[0].opening_balance
            closing = rows[-1].closing_balance
            total_interest = round(sum(r.interest_charge for r in rows), 2)
            total_principal = round(sum(r.principal_paid for r in rows), 2)
            total_overpayments = round(sum(r.overpayment for r in rows), 2)
            scheduled_payments = round(sum(r.scheduled_payment for r in rows), 2)
            monthly_payment = rows[-1].scheduled_payment
            annual_rate = rows[-1].annual_rate
            property_value = self._property_value_at_year_end(year)
            equity = round(property_value - closing, 2)
            ltv = round(closing / property_value, 4) if property_value > 0 else 0.0
            mortgage_active = closing > self.BALANCE_ZERO_THRESHOLD

            summaries.append(
                AnnualSummary(
                    year=year,
                    opening_balance=round(opening, 2),
                    closing_balance=round(closing, 2),
                    total_interest_paid=total_interest,
                    total_principal_paid=total_principal,
                    total_overpayments=total_overpayments,
                    scheduled_payments=scheduled_payments,
                    monthly_payment=monthly_payment,
                    annual_rate=annual_rate,
                    property_value=property_value,
                    equity=equity,
                    ltv=ltv,
                    mortgage_active=mortgage_active,
                )
            )

        logger.debug("Built %d annual summaries", len(summaries))
        return summaries


# ---------------------------------------------------------------------------
# YAML loader helpers
# ---------------------------------------------------------------------------


def _parse_date(value) -> date:
    """
    @brief Coerce a YAML value to a Python date.

    Accepts a datetime.date, datetime.datetime, or ISO 8601 string.

    @param value  Raw value from YAML parse.
    @return       Python date object.
    @raises ValueError  If value cannot be parsed.
    """
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):          # datetime
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"Cannot parse date from '{value}': {exc}") from exc


def load_mortgage_config_from_yaml(path: str) -> tuple[MortgageConfig, Optional[PropertyConfig]]:
    """
    @brief Load a MortgageConfig (and optional PropertyConfig) from a YAML file.

    Expected top-level keys: ``mortgage`` and optionally ``property``.

    @param path  Filesystem path to the YAML config file.
    @return      Tuple of (MortgageConfig, PropertyConfig | None).
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file is not valid YAML.
    @raises ValueError         If required keys are missing or values are invalid.
    """
    logger.info("Loading mortgage config from: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Mortgage config file not found: %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise

    if "mortgage" not in raw:
        raise ValueError(f"YAML file '{path}' must have a top-level 'mortgage' key.")

    m = raw["mortgage"]

    # Rate periods
    rate_periods: list[RatePeriod] = []
    for rp_raw in m.get("rate_periods", []):
        rp = RatePeriod(
            label=rp_raw.get("label", ""),
            annual_rate=float(rp_raw["annual_rate"]),
            start_date=_parse_date(rp_raw["start_date"]),
            end_date=_parse_date(rp_raw["end_date"]) if rp_raw.get("end_date") else None,
            rate_type=rp_raw.get("rate_type", "fixed"),
            notes=rp_raw.get("notes", ""),
        )
        rate_periods.append(rp)

    # Overpayments
    overpayments: list[Overpayment] = []
    for op_raw in m.get("overpayments", []):
        op = Overpayment(
            amount=float(op_raw["amount"]),
            overpayment_type=op_raw.get("overpayment_type", "lump_sum"),
            date=_parse_date(op_raw["date"]) if op_raw.get("date") else None,
            monthly_extra_start=_parse_date(op_raw["monthly_extra_start"]) if op_raw.get("monthly_extra_start") else None,
            monthly_extra_end=_parse_date(op_raw["monthly_extra_end"]) if op_raw.get("monthly_extra_end") else None,
            notes=op_raw.get("notes", ""),
        )
        overpayments.append(op)

    mortgage_cfg = MortgageConfig(
        mortgage_id=m["mortgage_id"],
        label=m["label"],
        property_id=m["property_id"],
        original_balance=float(m["original_balance"]),
        start_date=_parse_date(m["start_date"]),
        term_years=int(m["term_years"]),
        repayment_type=m.get("repayment_type", "repayment"),
        rate_periods=rate_periods,
        overpayments=overpayments,
        offset_balance=float(m.get("offset_balance", 0.0)),
        offset_grows_at=float(m.get("offset_grows_at", 0.0)),
        annual_overpayment_cap_pct=float(m.get("annual_overpayment_cap_pct", 0.10)),
        currency=m.get("currency", "GBP"),
        enabled=bool(m.get("enabled", True)),
        notes=m.get("notes", ""),
    )

    # Optional property config
    property_cfg: Optional[PropertyConfig] = None
    if "property" in raw:
        p = raw["property"]
        property_cfg = PropertyConfig(
            property_id=p["property_id"],
            label=p["label"],
            purchase_price=float(p["purchase_price"]),
            current_value=float(p["current_value"]),
            annual_growth_rate=float(p.get("annual_growth_rate", 0.03)),
            purchase_date=_parse_date(p["purchase_date"]) if p.get("purchase_date") else None,
            currency=p.get("currency", "GBP"),
            notes=p.get("notes", ""),
        )

    logger.info(
        "Loaded mortgage '%s' (balance=%.2f, term=%d yrs, %d rate periods, %d overpayments)",
        mortgage_cfg.mortgage_id,
        mortgage_cfg.original_balance,
        mortgage_cfg.term_years,
        len(rate_periods),
        len(overpayments),
    )
    return mortgage_cfg, property_cfg
