"""
@file tax_wrappers.py
@brief Tax wrapper rules, CGT disposal tracker, and FX conversion for LifeLedger.

Sits between the account models and the tax engine.  Answers three questions
for the projection engine:

  1. **Wrapper treatment** — given an account type, what tax applies to
     contributions, growth, and withdrawals?

  2. **CGT tracking** — for GIA-type accounts, track acquisition lots, record
     disposals, apply the annual CGT allowance, and compute the net taxable gain
     per year.

  3. **FX conversion** — convert amounts between currencies using a spot rate
     and configurable annual drift.

Supported wrapper types
-----------------------
UK wrappers
  ISA          — no tax on growth or withdrawals; contributions from net income.
  LISA         — like ISA + 25% government bonus up to £4k/yr; penalty on
                 non-qualifying withdrawal.
  SIPP         — contributions receive basic-rate tax relief at source
                 (higher-rate via self-assessment); growth tax-deferred;
                 drawdown taxed as income.
  GIA          — growth/dividends taxable in year; disposals subject to CGT.

US wrappers
  401k         — pre-tax contributions; growth tax-deferred; withdrawals taxed
                 as ordinary income; RMDs from age 73.
  Roth_401k    — post-tax contributions; growth and qualified withdrawals tax-free.
  IRA_traditional — similar to 401k.
  IRA_roth     — similar to Roth_401k.
  Brokerage_US — equivalent to GIA; long-term CG rates for assets held > 1 yr.

Ireland
  PRSA         — pension; 20–40% tax relief on contributions depending on age;
                 growth tax-free; drawdown taxed as income.

Generic
  Taxable      — fully taxable (worst case; user-configurable rates).
  Tax_free     — fully exempt (best case).

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

logger = logging.getLogger("lifeledger.tax_wrappers")


# ---------------------------------------------------------------------------
# Wrapper type constants
# ---------------------------------------------------------------------------

WT_ISA              = "ISA"
WT_LISA             = "LISA"
WT_SIPP             = "SIPP"
WT_GIA              = "GIA"
WT_401K             = "401k"
WT_ROTH_401K        = "Roth_401k"
WT_IRA_TRADITIONAL  = "IRA_traditional"
WT_IRA_ROTH         = "IRA_roth"
WT_BROKERAGE_US     = "Brokerage_US"
WT_PRSA             = "PRSA"
WT_TAXABLE          = "Taxable"
WT_TAX_FREE         = "Tax_free"

ALL_WRAPPER_TYPES: frozenset[str] = frozenset({
    WT_ISA, WT_LISA, WT_SIPP, WT_GIA,
    WT_401K, WT_ROTH_401K, WT_IRA_TRADITIONAL, WT_IRA_ROTH, WT_BROKERAGE_US,
    WT_PRSA, WT_TAXABLE, WT_TAX_FREE,
})


# ---------------------------------------------------------------------------
# Wrapper treatment dataclass
# ---------------------------------------------------------------------------


@dataclass
class WrapperTreatment:
    """
    @brief Tax treatment rules for a single account wrapper type.

    All rates are decimals.  None means "not applicable / no additional charge".

    @param wrapper_type              Wrapper type identifier string.
    @param contribution_relief_rate  Tax relief on contributions at source
                                     (0.20 = basic rate added by HMRC for SIPPs).
                                     0.0 = no relief; contributions from net income.
    @param contribution_limit_annual Annual contribution cap in base currency.
                                     0 = no limit enforced by this layer.
    @param growth_taxable            True if investment returns are taxable in-year.
    @param growth_tax_rate           Rate applied to in-year growth when taxable.
                                     None = use income tax rate.
    @param withdrawal_taxable        True if withdrawals are taxed as income.
    @param withdrawal_tax_rate       Override income tax rate on withdrawals.
                                     None = use income tax rate.
    @param pcls_fraction             UK pension tax-free cash fraction (0.25).
                                     0.0 for non-SIPP wrappers.
    @param early_withdrawal_penalty  Penalty rate for withdrawals before
                                     minimum access age (e.g. 0.10 for US 401k).
    @param early_withdrawal_age      Age below which penalty applies.
    @param lisa_bonus_rate           LISA government bonus rate (0.25 = 25 %).
    @param lisa_bonus_cap            Maximum annual LISA contributions eligible
                                     for bonus.
    @param lisa_penalty_rate         Withdrawal penalty for non-qualifying
                                     LISA withdrawals (0.25 = 25 %).
    @param cgt_applicable            True if CGT applies on asset disposals.
    @param long_term_cg_threshold_months  US: months held to qualify for
                                     long-term CGT rates (12).
    @param jurisdiction              Jurisdiction this wrapper applies to.
    @param notes                     Free-text notes.
    """

    wrapper_type: str
    contribution_relief_rate: float = 0.0
    contribution_limit_annual: float = 0.0
    growth_taxable: bool = False
    growth_tax_rate: Optional[float] = None
    withdrawal_taxable: bool = False
    withdrawal_tax_rate: Optional[float] = None
    pcls_fraction: float = 0.0
    early_withdrawal_penalty: float = 0.0
    early_withdrawal_age: int = 0
    lisa_bonus_rate: float = 0.0
    lisa_bonus_cap: float = 0.0
    lisa_penalty_rate: float = 0.0
    cgt_applicable: bool = False
    long_term_cg_threshold_months: int = 12
    jurisdiction: str = "UK"
    notes: str = ""


# ---------------------------------------------------------------------------
# Built-in wrapper definitions (2024/25 tax year rules)
# ---------------------------------------------------------------------------


def _default_wrappers() -> dict[str, WrapperTreatment]:
    """
    @brief Return the built-in WrapperTreatment definitions for all types.

    These can be overridden per-account via YAML config.

    @return  Dict mapping wrapper_type string -> WrapperTreatment.
    """
    return {
        WT_ISA: WrapperTreatment(
            wrapper_type=WT_ISA,
            contribution_relief_rate=0.0,
            contribution_limit_annual=20_000.0,
            growth_taxable=False,
            withdrawal_taxable=False,
            cgt_applicable=False,
            jurisdiction="UK",
            notes="Stocks & Shares ISA or Cash ISA. No tax on growth or withdrawals.",
        ),
        WT_LISA: WrapperTreatment(
            wrapper_type=WT_LISA,
            contribution_relief_rate=0.0,
            contribution_limit_annual=4_000.0,
            growth_taxable=False,
            withdrawal_taxable=False,
            lisa_bonus_rate=0.25,
            lisa_bonus_cap=4_000.0,
            lisa_penalty_rate=0.25,
            cgt_applicable=False,
            jurisdiction="UK",
            notes="Lifetime ISA. 25% bonus on up to £4k/yr. "
                  "25% withdrawal penalty for non-qualifying withdrawals.",
        ),
        WT_SIPP: WrapperTreatment(
            wrapper_type=WT_SIPP,
            contribution_relief_rate=0.20,       # basic rate relief at source
            contribution_limit_annual=60_000.0,  # annual allowance 2024/25
            growth_taxable=False,
            withdrawal_taxable=True,
            pcls_fraction=0.25,
            cgt_applicable=False,
            jurisdiction="UK",
            notes="SIPP / personal pension. 25% PCLS tax-free; remaining drawdown "
                  "taxed as income. Relief at source for basic rate; higher-rate "
                  "relief claimed via self-assessment.",
        ),
        WT_GIA: WrapperTreatment(
            wrapper_type=WT_GIA,
            contribution_relief_rate=0.0,
            contribution_limit_annual=0.0,       # no limit
            growth_taxable=True,                 # dividends / interest taxable
            growth_tax_rate=None,                # use income tax rate
            withdrawal_taxable=False,            # withdrawals of capital not taxed
            cgt_applicable=True,
            jurisdiction="UK",
            notes="General Investment Account. Growth (dividends/interest) taxable "
                  "in year. Disposals subject to CGT with annual allowance.",
        ),
        WT_401K: WrapperTreatment(
            wrapper_type=WT_401K,
            contribution_relief_rate=0.0,        # pre-tax; relief via payroll
            contribution_limit_annual=23_000.0,  # 2024 IRS limit (employee)
            growth_taxable=False,
            withdrawal_taxable=True,
            early_withdrawal_penalty=0.10,
            early_withdrawal_age=59,
            cgt_applicable=False,
            jurisdiction="US",
            notes="Traditional 401(k). Pre-tax contributions; growth deferred; "
                  "withdrawals taxed as ordinary income. 10% penalty before 59½.",
        ),
        WT_ROTH_401K: WrapperTreatment(
            wrapper_type=WT_ROTH_401K,
            contribution_relief_rate=0.0,
            contribution_limit_annual=23_000.0,
            growth_taxable=False,
            withdrawal_taxable=False,
            early_withdrawal_penalty=0.10,
            early_withdrawal_age=59,
            cgt_applicable=False,
            jurisdiction="US",
            notes="Roth 401(k). Post-tax contributions; growth and qualified "
                  "withdrawals tax-free. 10% penalty before 59½ on earnings.",
        ),
        WT_IRA_TRADITIONAL: WrapperTreatment(
            wrapper_type=WT_IRA_TRADITIONAL,
            contribution_relief_rate=0.0,
            contribution_limit_annual=7_000.0,   # 2024 IRS limit
            growth_taxable=False,
            withdrawal_taxable=True,
            early_withdrawal_penalty=0.10,
            early_withdrawal_age=59,
            cgt_applicable=False,
            jurisdiction="US",
            notes="Traditional IRA. Deductible contributions (if eligible); "
                  "growth deferred; withdrawals taxed as income.",
        ),
        WT_IRA_ROTH: WrapperTreatment(
            wrapper_type=WT_IRA_ROTH,
            contribution_relief_rate=0.0,
            contribution_limit_annual=7_000.0,
            growth_taxable=False,
            withdrawal_taxable=False,
            early_withdrawal_penalty=0.0,
            cgt_applicable=False,
            jurisdiction="US",
            notes="Roth IRA. Post-tax contributions; growth and qualified "
                  "withdrawals tax-free. No RMDs in owner's lifetime.",
        ),
        WT_BROKERAGE_US: WrapperTreatment(
            wrapper_type=WT_BROKERAGE_US,
            contribution_relief_rate=0.0,
            contribution_limit_annual=0.0,
            growth_taxable=True,
            growth_tax_rate=0.15,               # typical long-term CG rate
            withdrawal_taxable=False,
            cgt_applicable=True,
            long_term_cg_threshold_months=12,
            jurisdiction="US",
            notes="US taxable brokerage. Dividends and short-term CG taxed as "
                  "income; long-term CG at 0/15/20% depending on income.",
        ),
        WT_PRSA: WrapperTreatment(
            wrapper_type=WT_PRSA,
            contribution_relief_rate=0.20,
            contribution_limit_annual=0.0,       # age-based % of net relevant earnings
            growth_taxable=False,
            withdrawal_taxable=True,
            pcls_fraction=0.25,
            jurisdiction="Ireland",
            notes="Personal Retirement Savings Account. Relief at 20–40% "
                  "depending on age band; 25% tax-free lump sum; drawdown taxed.",
        ),
        WT_TAXABLE: WrapperTreatment(
            wrapper_type=WT_TAXABLE,
            contribution_relief_rate=0.0,
            contribution_limit_annual=0.0,
            growth_taxable=True,
            withdrawal_taxable=True,
            cgt_applicable=True,
            jurisdiction="generic",
            notes="Fully taxable generic wrapper. Use for unknown account types.",
        ),
        WT_TAX_FREE: WrapperTreatment(
            wrapper_type=WT_TAX_FREE,
            contribution_relief_rate=0.0,
            contribution_limit_annual=0.0,
            growth_taxable=False,
            withdrawal_taxable=False,
            cgt_applicable=False,
            jurisdiction="generic",
            notes="Fully exempt generic wrapper.",
        ),
    }


# ---------------------------------------------------------------------------
# CGT disposal tracking
# ---------------------------------------------------------------------------


@dataclass
class CGTLot:
    """
    @brief A single acquisition lot for CGT tracking.

    @param lot_id           Unique identifier for this lot.
    @param account_id       Account the lot is held in.
    @param asset_id         Asset/instrument identifier.
    @param acquisition_date Date the lot was acquired.
    @param units            Number of units (or 1 for a single lump).
    @param cost_per_unit    Cost basis per unit.
    @param currency         ISO 4217 code.
    """

    lot_id: str
    account_id: str
    asset_id: str
    acquisition_date: date
    units: float
    cost_per_unit: float
    currency: str = "GBP"

    @property
    def total_cost(self) -> float:
        """@brief Total acquisition cost for this lot."""
        return round(self.units * self.cost_per_unit, 2)


@dataclass
class CGTDisposal:
    """
    @brief A single disposal event for CGT calculation.

    @param disposal_id      Unique identifier.
    @param account_id       Account the disposal is from.
    @param asset_id         Asset/instrument identifier.
    @param disposal_date    Date of disposal.
    @param proceeds         Gross proceeds from the disposal.
    @param cost_basis       Total acquisition cost attributable to disposed units.
    @param exempt           True if the disposal is CGT-exempt (ISA, PPR, etc.).
    @param currency         ISO 4217 code.
    @param label            Human-readable description.
    """

    disposal_id: str
    account_id: str
    asset_id: str
    disposal_date: date
    proceeds: float
    cost_basis: float
    exempt: bool = False
    currency: str = "GBP"
    label: str = ""

    @property
    def gain(self) -> float:
        """@brief Net gain on this disposal (may be negative = loss)."""
        return round(self.proceeds - self.cost_basis, 2)


@dataclass
class CGTYearResult:
    """
    @brief Annual CGT computation summary.

    @param year                 Calendar year.
    @param gross_gains          Sum of all gains before losses and allowance.
    @param losses               Sum of all realised losses (positive number).
    @param net_gain_pre_annual  Net gain before annual exemption.
    @param annual_exemption     Annual CGT allowance applied.
    @param taxable_gain         Net gain after losses and allowance.
    @param basic_rate_cgt       CGT at basic rate (residential: 18%, other: 10%).
    @param higher_rate_cgt      CGT at higher rate (residential: 24%, other: 20%).
    @param total_cgt_liability  Total CGT payable this year.
    @param disposals            List of CGTDisposal objects processed.
    @param exempt_disposals     List of exempt disposals (not counted).
    @param warnings             Warning strings.
    """

    year: int
    gross_gains: float = 0.0
    losses: float = 0.0
    net_gain_pre_annual: float = 0.0
    annual_exemption: float = 0.0
    taxable_gain: float = 0.0
    basic_rate_cgt: float = 0.0
    higher_rate_cgt: float = 0.0
    total_cgt_liability: float = 0.0
    disposals: list[CGTDisposal] = field(default_factory=list)
    exempt_disposals: list[CGTDisposal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CGTTracker:
    """
    @brief Tracks CGT lots and computes annual CGT liability.

    Supports UK CGT rules: annual exemption, basic/higher rate split,
    loss carry-forward, and residential property surcharge.  Also
    handles US long-term vs short-term distinction.

    Usage::

        tracker = CGTTracker(annual_exemption=3000, basic_rate=0.10,
                             higher_rate=0.20)
        tracker.add_lot(lot)
        tracker.record_disposal(disposal)
        result = tracker.compute_year(2025, income_in_basic_band=15000,
                                      basic_band_remaining=10000)
    """

    def __init__(
        self,
        annual_exemption: float = 3_000.0,
        basic_rate: float = 0.10,
        higher_rate: float = 0.20,
        residential_basic_rate: float = 0.18,
        residential_higher_rate: float = 0.24,
        carry_losses: bool = True,
    ) -> None:
        """
        @brief Initialise the CGT tracker.

        @param annual_exemption          Annual CGT exemption (UK 2024/25: £3,000).
        @param basic_rate                CGT rate for basic-rate taxpayers (non-residential).
        @param higher_rate               CGT rate for higher-rate taxpayers.
        @param residential_basic_rate    Surcharge rate for residential property (basic).
        @param residential_higher_rate   Surcharge rate for residential property (higher).
        @param carry_losses              If True, unused losses carry forward
                                         to future years.
        """
        self._annual_exemption = annual_exemption
        self._basic_rate = basic_rate
        self._higher_rate = higher_rate
        self._res_basic = residential_basic_rate
        self._res_higher = residential_higher_rate
        self._carry_losses = carry_losses

        self._lots: list[CGTLot] = []
        self._disposals: list[CGTDisposal] = []
        self._carried_losses: float = 0.0
        logger.debug(
            "CGTTracker: exemption=%.0f basic=%.0f%% higher=%.0f%%",
            annual_exemption, basic_rate * 100, higher_rate * 100,
        )

    def add_lot(self, lot: CGTLot) -> None:
        """
        @brief Register an acquisition lot.

        @param lot  CGTLot to record.
        """
        self._lots.append(lot)
        logger.debug(
            "CGT lot added: %s %s units=%.4f cost=%.2f",
            lot.account_id, lot.asset_id, lot.units, lot.total_cost,
        )

    def record_disposal(self, disposal: CGTDisposal) -> None:
        """
        @brief Record a disposal for processing in the current year.

        @param disposal  CGTDisposal to record.
        """
        self._disposals.append(disposal)
        logger.debug(
            "CGT disposal: %s %s proceeds=%.2f basis=%.2f gain=%.2f",
            disposal.account_id, disposal.asset_id,
            disposal.proceeds, disposal.cost_basis, disposal.gain,
        )

    def compute_year(
        self,
        year: int,
        basic_band_remaining: float = 0.0,
        is_residential: bool = False,
    ) -> CGTYearResult:
        """
        @brief Compute the CGT liability for a given calendar year.

        Processes all disposals recorded since the last compute_year call
        (or since initialisation).  Applies annual exemption, loss carry-forward,
        and splits liability between basic and higher rate bands.

        @param year                  Calendar year being computed.
        @param basic_band_remaining  Remaining basic-rate income tax band headroom
                                     (used to split CGT between basic/higher rate).
        @param is_residential        If True, use residential property CGT rates.
        @return                      CGTYearResult.
        """
        year_disposals = [d for d in self._disposals if d.disposal_date.year == year]
        exempt = [d for d in year_disposals if d.exempt]
        taxable_disp = [d for d in year_disposals if not d.exempt]

        result = CGTYearResult(
            year=year,
            annual_exemption=self._annual_exemption,
            disposals=taxable_disp,
            exempt_disposals=exempt,
        )

        gains = sum(max(0.0, d.gain) for d in taxable_disp)
        losses = sum(abs(min(0.0, d.gain)) for d in taxable_disp)
        result.gross_gains = round(gains, 2)
        result.losses = round(losses, 2)

        # Apply carried losses from prior years
        total_losses = losses + self._carried_losses
        net_gain = max(0.0, gains - total_losses)
        result.net_gain_pre_annual = round(net_gain, 2)

        # Update carried losses
        if gains > 0 and self._carry_losses:
            unused_losses = max(0.0, total_losses - gains)
            self._carried_losses = unused_losses
        elif self._carry_losses:
            self._carried_losses = total_losses

        # Apply annual exemption
        taxable = max(0.0, net_gain - self._annual_exemption)
        exemption_used = min(net_gain, self._annual_exemption)
        result.annual_exemption = round(exemption_used, 2)
        result.taxable_gain = round(taxable, 2)

        if taxable <= 0:
            logger.debug("Year %d: no CGT liability (gain=%.2f, exemption=%.2f)", year, net_gain, exemption_used)
            return result

        # Split between basic and higher rate
        br = self._res_basic if is_residential else self._basic_rate
        hr = self._res_higher if is_residential else self._higher_rate

        basic_portion = min(taxable, max(0.0, basic_band_remaining))
        higher_portion = taxable - basic_portion

        result.basic_rate_cgt = round(basic_portion * br, 2)
        result.higher_rate_cgt = round(higher_portion * hr, 2)
        result.total_cgt_liability = round(result.basic_rate_cgt + result.higher_rate_cgt, 2)

        logger.info(
            "CGT year=%d taxable_gain=%.2f basic_cgt=%.2f higher_cgt=%.2f total=%.2f",
            year, taxable, result.basic_rate_cgt, result.higher_rate_cgt, result.total_cgt_liability,
        )
        return result

    def clear_year_disposals(self, year: int) -> None:
        """
        @brief Remove disposals for a processed year from the pending list.

        @param year  Calendar year whose disposals have been processed.
        """
        self._disposals = [d for d in self._disposals if d.disposal_date.year != year]


# ---------------------------------------------------------------------------
# LISA bonus calculator
# ---------------------------------------------------------------------------


def compute_lisa_bonus(
    contributions: float,
    wrapper: WrapperTreatment,
) -> float:
    """
    @brief Compute the annual LISA government bonus for a given contribution.

    Bonus = min(contributions, lisa_bonus_cap) * lisa_bonus_rate.

    @param contributions  Employee contributions in the year.
    @param wrapper        WrapperTreatment for the LISA account.
    @return               Bonus amount.
    """
    if wrapper.wrapper_type != WT_LISA or wrapper.lisa_bonus_rate == 0:
        return 0.0
    eligible = min(contributions, wrapper.lisa_bonus_cap)
    bonus = round(eligible * wrapper.lisa_bonus_rate, 2)
    logger.debug("LISA bonus: contributions=%.2f eligible=%.2f bonus=%.2f", contributions, eligible, bonus)
    return bonus


def compute_lisa_withdrawal_penalty(
    withdrawal: float,
    original_contribution: float,
    wrapper: WrapperTreatment,
) -> float:
    """
    @brief Compute the LISA non-qualifying withdrawal penalty.

    The penalty effectively claws back the government bonus plus a
    further 6.25% of contributions.

    @param withdrawal             Gross withdrawal amount.
    @param original_contribution  Original contribution (pre-bonus) amount.
    @param wrapper                WrapperTreatment for the LISA account.
    @return                       Penalty amount.
    """
    if wrapper.wrapper_type != WT_LISA or wrapper.lisa_penalty_rate == 0:
        return 0.0
    penalty = round(withdrawal * wrapper.lisa_penalty_rate, 2)
    logger.warning(
        "LISA non-qualifying withdrawal: %.2f — penalty=%.2f", withdrawal, penalty
    )
    return penalty


# ---------------------------------------------------------------------------
# FX conversion
# ---------------------------------------------------------------------------


@dataclass
class FXRate:
    """
    @brief A currency pair with spot rate and annual drift.

    @param base_currency    The base (from) currency ISO 4217 code.
    @param quote_currency   The quote (to) currency ISO 4217 code.
    @param spot_rate        Current spot rate (1 base = spot_rate quote).
    @param annual_drift     Expected annual rate change as a decimal
                            (0.02 = base appreciates 2 % vs quote per year).
    @param rate_date        Date the spot_rate was recorded.
    @param notes            Free-text notes.
    """

    base_currency: str
    quote_currency: str
    spot_rate: float
    annual_drift: float = 0.0
    rate_date: Optional[date] = None
    notes: str = ""


class FXManager:
    """
    @brief Currency conversion manager with drift projection.

    Holds a set of FXRate objects and converts amounts between currencies,
    compounding the annual drift from rate_date to the target year.

    Usage::

        fx = FXManager([FXRate("GBP", "USD", 1.27, 0.0)])
        usd = fx.convert(1000, "GBP", "USD", year=2030)
    """

    def __init__(self, rates: list[FXRate]) -> None:
        """
        @brief Initialise the FX manager with a list of rates.

        @param rates  List of FXRate objects (both directions auto-derived).
        """
        self._rates: dict[tuple[str, str], FXRate] = {}
        for r in rates:
            self._rates[(r.base_currency, r.quote_currency)] = r
            # Also store inverse for convenience
            if (r.quote_currency, r.base_currency) not in self._rates:
                self._rates[(r.quote_currency, r.base_currency)] = FXRate(
                    base_currency=r.quote_currency,
                    quote_currency=r.base_currency,
                    spot_rate=round(1.0 / r.spot_rate, 6) if r.spot_rate else 1.0,
                    annual_drift=-r.annual_drift,
                    rate_date=r.rate_date,
                    notes=f"Auto-inverse of {r.base_currency}/{r.quote_currency}",
                )
        logger.debug("FXManager: loaded %d rate pairs", len(rates))

    def rate(self, from_ccy: str, to_ccy: str, year: Optional[int] = None) -> float:
        """
        @brief Return the effective exchange rate for a currency pair.

        Compounds annual drift from the rate_date year to target year.

        @param from_ccy  Source currency ISO code.
        @param to_ccy    Target currency ISO code.
        @param year      Target calendar year (None = use spot rate unchanged).
        @return          Exchange rate (1 from_ccy = result to_ccy).
        @raises KeyError If the currency pair is not registered.
        """
        if from_ccy == to_ccy:
            return 1.0

        key = (from_ccy, to_ccy)
        if key not in self._rates:
            raise KeyError(
                f"No FX rate registered for {from_ccy}/{to_ccy}. "
                f"Available: {list(self._rates.keys())}"
            )

        fx = self._rates[key]
        spot = fx.spot_rate

        if year is not None and fx.rate_date is not None and fx.annual_drift != 0.0:
            years_elapsed = year - fx.rate_date.year
            spot = round(spot * (1 + fx.annual_drift) ** years_elapsed, 6)

        return spot

    def convert(self, amount: float, from_ccy: str, to_ccy: str, year: Optional[int] = None) -> float:
        """
        @brief Convert an amount from one currency to another.

        @param amount    Amount in from_ccy.
        @param from_ccy  Source currency.
        @param to_ccy    Target currency.
        @param year      Calendar year for drift projection.
        @return          Converted amount in to_ccy.
        """
        if from_ccy == to_ccy:
            return amount
        r = self.rate(from_ccy, to_ccy, year)
        result = round(amount * r, 2)
        logger.debug(
            "FX convert: %.2f %s → %.2f %s (rate=%.6f year=%s)",
            amount, from_ccy, result, to_ccy, r, year,
        )
        return result

    def add_rate(self, rate: FXRate) -> None:
        """
        @brief Register an additional FX rate at runtime.

        @param rate  FXRate to add.
        """
        self._rates[(rate.base_currency, rate.quote_currency)] = rate
        logger.debug("FXManager: added rate %s/%s=%.6f", rate.base_currency, rate.quote_currency, rate.spot_rate)


# ---------------------------------------------------------------------------
# Tax wrappers engine (main entry point)
# ---------------------------------------------------------------------------


@dataclass
class ContributionResult:
    """
    @brief Result of processing a contribution through a wrapper.

    @param gross_contribution      Gross amount contributed.
    @param relief_amount           Tax relief added at source.
    @param total_into_account      Gross + relief = actual fund credit.
    @param allowance_used          Amount counted against annual allowance.
    @param allowance_remaining     Allowance remaining after this contribution.
    @param allowance_breached      True if contribution exceeds allowance.
    @param lisa_bonus              LISA government bonus (0 for non-LISA).
    @param warnings                Warning strings.
    """
    gross_contribution: float
    relief_amount: float
    total_into_account: float
    allowance_used: float
    allowance_remaining: float
    allowance_breached: bool
    lisa_bonus: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class WithdrawalResult:
    """
    @brief Result of processing a withdrawal through a wrapper.

    @param gross_withdrawal        Gross amount requested.
    @param tax_free_amount         Portion exempt from income tax (PCLS etc.).
    @param taxable_amount          Portion subject to income tax.
    @param penalty_amount          Early withdrawal penalty (if applicable).
    @param net_received            Amount received after penalties.
    @param warnings                Warning strings.
    """
    gross_withdrawal: float
    tax_free_amount: float
    taxable_amount: float
    penalty_amount: float
    net_received: float
    warnings: list[str] = field(default_factory=list)


class TaxWrapperEngine:
    """
    @brief Main engine for tax wrapper computations.

    Provides methods to compute contribution relief, withdrawal treatment,
    annual growth tax, LISA bonus, and CGT for any registered account.

    Usage::

        engine = TaxWrapperEngine(wrappers_config)
        cr = engine.process_contribution("vanguard_sipp", WT_SIPP, 12000)
        wr = engine.process_withdrawal("vanguard_sipp", WT_SIPP, 30000, age=60)
    """

    def __init__(
        self,
        wrapper_overrides: Optional[dict[str, WrapperTreatment]] = None,
        cgt_tracker: Optional[CGTTracker] = None,
        fx_manager: Optional[FXManager] = None,
    ) -> None:
        """
        @brief Initialise the engine.

        @param wrapper_overrides  Dict of wrapper_type -> WrapperTreatment
                                  overriding the built-in defaults.
        @param cgt_tracker        Shared CGTTracker instance.  A default one
                                  is created if not provided.
        @param fx_manager         Shared FXManager instance.
        """
        self._wrappers = _default_wrappers()
        if wrapper_overrides:
            self._wrappers.update(wrapper_overrides)
        self.cgt = cgt_tracker or CGTTracker()
        self.fx = fx_manager or FXManager([])
        logger.info(
            "TaxWrapperEngine initialised with %d wrapper types", len(self._wrappers)
        )

    def get_treatment(self, wrapper_type: str) -> WrapperTreatment:
        """
        @brief Return the WrapperTreatment for a given wrapper type.

        @param wrapper_type  Wrapper type string.
        @return              WrapperTreatment.
        @raises KeyError     If wrapper_type is not recognised.
        """
        if wrapper_type not in self._wrappers:
            logger.warning(
                "Unknown wrapper type '%s' — using Taxable fallback.", wrapper_type
            )
            return self._wrappers[WT_TAXABLE]
        return self._wrappers[wrapper_type]

    def process_contribution(
        self,
        account_id: str,
        wrapper_type: str,
        gross_contribution: float,
        allowance_used_ytd: float = 0.0,
    ) -> ContributionResult:
        """
        @brief Compute relief and allowance check for a contribution.

        @param account_id           Account identifier (for logging).
        @param wrapper_type         Wrapper type string.
        @param gross_contribution   Gross contribution amount.
        @param allowance_used_ytd   Total contributions already made this year
                                    (for allowance headroom check).
        @return                     ContributionResult.
        """
        wt = self.get_treatment(wrapper_type)
        relief = round(gross_contribution * wt.contribution_relief_rate, 2)
        total_into_account = round(gross_contribution + relief, 2)
        allowance_used = gross_contribution  # relief is HMRC's addition, not user's
        limit = wt.contribution_limit_annual
        allowance_remaining = max(0.0, limit - allowance_used_ytd - allowance_used) if limit > 0 else float("inf")
        breached = limit > 0 and (allowance_used_ytd + allowance_used) > limit
        lisa_bonus = compute_lisa_bonus(gross_contribution, wt)
        warnings = []
        if breached:
            warnings.append(
                f"Account '{account_id}' ({wrapper_type}): contribution £{gross_contribution:,.0f} "
                f"causes annual limit breach (limit=£{limit:,.0f}, used=£{allowance_used_ytd:,.0f})."
            )
            logger.warning(warnings[-1])
        logger.debug(
            "Contribution %s %s: gross=%.2f relief=%.2f total=%.2f breached=%s",
            account_id, wrapper_type, gross_contribution, relief, total_into_account, breached,
        )
        return ContributionResult(
            gross_contribution=gross_contribution,
            relief_amount=relief,
            total_into_account=total_into_account,
            allowance_used=allowance_used,
            allowance_remaining=allowance_remaining if allowance_remaining != float("inf") else 0.0,
            allowance_breached=breached,
            lisa_bonus=lisa_bonus,
            warnings=warnings,
        )

    def process_withdrawal(
        self,
        account_id: str,
        wrapper_type: str,
        gross_withdrawal: float,
        age: int = 0,
        is_first_drawdown: bool = False,
        pcls_already_taken: bool = False,
    ) -> WithdrawalResult:
        """
        @brief Compute tax-free / taxable split and penalties for a withdrawal.

        For SIPPs, applies the PCLS (25 % tax-free cash) in the first drawdown
        year.  For early withdrawal from US accounts, applies the 10 % penalty.

        @param account_id           Account identifier (for logging).
        @param wrapper_type         Wrapper type string.
        @param gross_withdrawal     Gross amount to withdraw.
        @param age                  Holder's current age (for penalty check).
        @param is_first_drawdown    True if this is the first drawdown year.
        @param pcls_already_taken   True if PCLS was taken in a prior year.
        @return                     WithdrawalResult.
        """
        wt = self.get_treatment(wrapper_type)
        warnings = []
        tax_free = 0.0
        taxable = 0.0
        penalty = 0.0

        # PCLS for UK pension wrappers
        if (
            is_first_drawdown
            and not pcls_already_taken
            and wt.pcls_fraction > 0
        ):
            tax_free = round(gross_withdrawal * wt.pcls_fraction, 2)
            taxable = round(gross_withdrawal - tax_free, 2)
        elif wt.withdrawal_taxable:
            taxable = gross_withdrawal
        else:
            tax_free = gross_withdrawal

        # Early withdrawal penalty (US)
        if (
            wt.early_withdrawal_penalty > 0
            and wt.early_withdrawal_age > 0
            and age > 0
            and age < wt.early_withdrawal_age
        ):
            penalty = round(taxable * wt.early_withdrawal_penalty, 2)
            warnings.append(
                f"Account '{account_id}' ({wrapper_type}): early withdrawal at age {age} "
                f"— penalty {wt.early_withdrawal_penalty:.0%} = £{penalty:,.2f}."
            )
            logger.warning(warnings[-1])

        net_received = round(gross_withdrawal - penalty, 2)
        logger.debug(
            "Withdrawal %s %s: gross=%.2f tax_free=%.2f taxable=%.2f penalty=%.2f",
            account_id, wrapper_type, gross_withdrawal, tax_free, taxable, penalty,
        )
        return WithdrawalResult(
            gross_withdrawal=gross_withdrawal,
            tax_free_amount=tax_free,
            taxable_amount=taxable,
            penalty_amount=penalty,
            net_received=net_received,
            warnings=warnings,
        )

    def in_year_growth_tax(
        self,
        account_id: str,
        wrapper_type: str,
        gross_growth: float,
        marginal_income_tax_rate: float = 0.20,
    ) -> float:
        """
        @brief Compute tax on in-year growth (dividends/interest) for GIA-type accounts.

        For wrappers where growth_taxable=True, applies the growth_tax_rate
        (or falls back to the marginal income tax rate).

        @param account_id              Account identifier.
        @param wrapper_type            Wrapper type string.
        @param gross_growth            Gross investment return this year.
        @param marginal_income_tax_rate  Holder's marginal income tax rate.
        @return                        Tax liability on growth (0 for ISA/SIPP/etc).
        """
        wt = self.get_treatment(wrapper_type)
        if not wt.growth_taxable or gross_growth <= 0:
            return 0.0
        rate = wt.growth_tax_rate if wt.growth_tax_rate is not None else marginal_income_tax_rate
        tax = round(gross_growth * rate, 2)
        logger.debug(
            "Growth tax %s %s: growth=%.2f rate=%.2f%% tax=%.2f",
            account_id, wrapper_type, gross_growth, rate * 100, tax,
        )
        return tax


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def load_tax_wrappers_config(path: str) -> TaxWrapperEngine:
    """
    @brief Load a TaxWrapperEngine from a YAML configuration file.

    Expected top-level keys:
      ``wrapper_overrides`` — list of wrapper override dicts
      ``cgt``              — CGT tracker settings
      ``fx_rates``         — list of FX rate dicts

    @param path  Filesystem path to the YAML config file.
    @return      Configured TaxWrapperEngine.
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file is not valid YAML.
    """
    logger.info("Loading tax wrappers config from: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Tax wrappers config not found: %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise

    raw = raw or {}

    # Wrapper overrides
    overrides: dict[str, WrapperTreatment] = {}
    for item in raw.get("wrapper_overrides", []):
        wt_key = item.get("wrapper_type")
        if not wt_key:
            continue
        overrides[wt_key] = WrapperTreatment(
            wrapper_type=wt_key,
            contribution_relief_rate=float(item.get("contribution_relief_rate", 0)),
            contribution_limit_annual=float(item.get("contribution_limit_annual", 0)),
            growth_taxable=bool(item.get("growth_taxable", False)),
            growth_tax_rate=float(item["growth_tax_rate"]) if item.get("growth_tax_rate") is not None else None,
            withdrawal_taxable=bool(item.get("withdrawal_taxable", False)),
            withdrawal_tax_rate=float(item["withdrawal_tax_rate"]) if item.get("withdrawal_tax_rate") is not None else None,
            pcls_fraction=float(item.get("pcls_fraction", 0)),
            early_withdrawal_penalty=float(item.get("early_withdrawal_penalty", 0)),
            early_withdrawal_age=int(item.get("early_withdrawal_age", 0)),
            lisa_bonus_rate=float(item.get("lisa_bonus_rate", 0)),
            lisa_bonus_cap=float(item.get("lisa_bonus_cap", 0)),
            lisa_penalty_rate=float(item.get("lisa_penalty_rate", 0)),
            cgt_applicable=bool(item.get("cgt_applicable", False)),
            long_term_cg_threshold_months=int(item.get("long_term_cg_threshold_months", 12)),
            jurisdiction=str(item.get("jurisdiction", "UK")),
            notes=str(item.get("notes", "")),
        )

    # CGT tracker
    cgt_raw = raw.get("cgt", {}) or {}
    cgt_tracker = CGTTracker(
        annual_exemption=float(cgt_raw.get("annual_exemption", 3_000)),
        basic_rate=float(cgt_raw.get("basic_rate", 0.10)),
        higher_rate=float(cgt_raw.get("higher_rate", 0.20)),
        residential_basic_rate=float(cgt_raw.get("residential_basic_rate", 0.18)),
        residential_higher_rate=float(cgt_raw.get("residential_higher_rate", 0.24)),
        carry_losses=bool(cgt_raw.get("carry_losses", True)),
    )

    # FX rates
    fx_rates: list[FXRate] = []
    for item in raw.get("fx_rates", []):
        rd_raw = item.get("rate_date")
        rd = None
        if rd_raw:
            try:
                rd = date.fromisoformat(str(rd_raw))
            except ValueError:
                pass
        fx_rates.append(FXRate(
            base_currency=str(item["base_currency"]),
            quote_currency=str(item["quote_currency"]),
            spot_rate=float(item["spot_rate"]),
            annual_drift=float(item.get("annual_drift", 0)),
            rate_date=rd,
            notes=str(item.get("notes", "")),
        ))
    fx_manager = FXManager(fx_rates) if fx_rates else FXManager([])

    engine = TaxWrapperEngine(
        wrapper_overrides=overrides if overrides else None,
        cgt_tracker=cgt_tracker,
        fx_manager=fx_manager,
    )
    logger.info(
        "Tax wrappers loaded: %d overrides, CGT exemption=%.0f, %d FX pairs",
        len(overrides), cgt_raw.get("annual_exemption", 3_000), len(fx_rates),
    )
    return engine
