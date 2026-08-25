"""
@file tax_optimiser.py
@brief Phase 8 tax optimisation engine for LifeLedger.

Implements three independent tax-saving strategies for UK pension drawdown:

Band-filler
    Each year in retirement, determines the optimal amount to draw from
    pension to fill the personal allowance and basic-rate band, then top
    up from ISA (tax-free). Compares against a naive proportional drawdown
    and reports lifetime tax saving.

UFPLS vs PCLS
    Models two pension crystallisation strategies over the full retirement
    period and computes the net-of-tax wealth trajectory for each.

    UFPLS  — each withdrawal is 25% tax-free / 75% taxable (spread over time).
    PCLS   — 25% taken as a lump sum upfront (tax-free), remainder is fully
             taxable on drawdown.

CGT harvest scheduler
    Scans each tax year for unrealised GIA gains below the annual CGT
    exemption (£3,000) and recommends crystallising them to reset the cost
    basis. Also flags loss-harvesting opportunities.

Scottish rates
    Applies Scottish income tax bands for Scottish-resident taxpayers.
    NI remains UK-wide and is unaffected.

All engines are self-contained: they read directly from the scenario YAML
dict and the optimiser config YAML. No simulation run is required.

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

logger = logging.getLogger("lifeledger.tax_optimiser")


# ─────────────────────────────────────────────────────────────────────────────
# UK tax band constants (2024/25)
# These are the reference values; the engine reads from the optimiser config
# where it wants to use the exact tunable band limits.
# ─────────────────────────────────────────────────────────────────────────────

_PA            = 12_570.0   # Personal allowance
_BASIC_LIMIT   = 50_270.0   # Top of basic-rate band (above PA is taxable at 20%)
_HIGHER_LIMIT  = 125_140.0  # Top of higher-rate band (60p taper zone between £100k–£125k)
_BASIC_RATE    = 0.20
_HIGHER_RATE   = 0.40
_ADDNL_RATE    = 0.45
_CGT_EXEMPT    = 3_000.0    # 2024/25 annual CGT exemption
_CGT_BASIC     = 0.10       # CGT on gains within basic-rate band
_CGT_HIGHER    = 0.20       # CGT on gains above basic-rate band
_TRIPLE_LOCK   = 0.025      # State pension triple-lock floor


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class BandFillYear:
    """
    @brief Band-filler result for one tax year.

    @param year               Calendar year.
    @param age                Primary person's age.
    @param target_spending    Annual spending target (inflation-adjusted).
    @param other_income       State pension + rental + other non-pension income.
    @param band_space_pa      Remaining personal allowance after other income.
    @param band_space_basic   Remaining basic-rate band after other income.
    @param pension_drawn_opt  Optimal pension drawdown (band-filling strategy).
    @param pension_drawn_naive  Naive pension drawdown (proportional baseline).
    @param isa_drawn_opt      ISA drawdown under optimal strategy.
    @param isa_drawn_naive    ISA drawdown under naive strategy.
    @param tax_opt            Income tax paid under optimal strategy.
    @param tax_naive          Income tax paid under naive strategy.
    @param tax_saved          Tax saved this year (naive − optimal).
    @param pension_pot_opt    Pension pot at year end (optimal).
    @param pension_pot_naive  Pension pot at year end (naive).
    @param isa_pot_opt        ISA pot at year end (optimal).
    @param isa_pot_naive      ISA pot at year end (naive).
    @param action             Short human-readable recommendation string.
    """
    year: int
    age: int
    target_spending: float
    other_income: float
    band_space_pa: float
    band_space_basic: float
    pension_drawn_opt: float
    pension_drawn_naive: float
    isa_drawn_opt: float
    isa_drawn_naive: float
    tax_opt: float
    tax_naive: float
    tax_saved: float
    pension_pot_opt: float
    pension_pot_naive: float
    isa_pot_opt: float
    isa_pot_naive: float
    action: str


@dataclass
class BandFillResult:
    """
    @brief Full band-filler analysis result.

    @param years                 Year-by-year breakdown.
    @param lifetime_tax_opt      Total lifetime income tax (optimal strategy).
    @param lifetime_tax_naive    Total lifetime income tax (naive baseline).
    @param lifetime_tax_saved    Total tax saved over retirement.
    @param isa_exhausted_year_opt   Year ISA runs out (optimal), None if never.
    @param isa_exhausted_year_naive Year ISA runs out (naive), None if never.
    @param pension_exhausted_year_opt   Year pension runs out (optimal).
    @param pension_exhausted_year_naive Year pension runs out (naive).
    @param warnings              List of warning messages.
    """
    years: list[BandFillYear]
    lifetime_tax_opt: float
    lifetime_tax_naive: float
    lifetime_tax_saved: float
    isa_exhausted_year_opt: Optional[int]
    isa_exhausted_year_naive: Optional[int]
    pension_exhausted_year_opt: Optional[int]
    pension_exhausted_year_naive: Optional[int]
    warnings: list[str] = field(default_factory=list)


@dataclass
class UFPLSYear:
    """
    @brief UFPLS vs PCLS comparison for one year.

    @param year              Calendar year.
    @param age               Primary person's age.
    @param withdrawal_target Target annual withdrawal amount.
    @param ufpls_gross       Gross UFPLS withdrawal needed to meet target net.
    @param ufpls_tax_free    Tax-free portion of UFPLS withdrawal.
    @param ufpls_taxable     Taxable portion of UFPLS withdrawal.
    @param ufpls_tax         Income tax on UFPLS taxable portion.
    @param ufpls_net         Net cash received from UFPLS.
    @param ufpls_pot         Remaining pension pot after UFPLS.
    @param pcls_gross        Gross drawdown withdrawal under PCLS.
    @param pcls_tax          Income tax on PCLS drawdown.
    @param pcls_net          Net cash received from PCLS drawdown.
    @param pcls_drawdown_pot Remaining pension drawdown pot.
    @param pcls_lump_pot     PCLS lump sum pot (growing separately).
    @param ufpls_total_wealth  Combined UFPLS pot + cash received.
    @param pcls_total_wealth   Combined PCLS pots + cash received.
    @param delta             UFPLS − PCLS wealth differential.
    """
    year: int
    age: int
    withdrawal_target: float
    ufpls_gross: float
    ufpls_tax_free: float
    ufpls_taxable: float
    ufpls_tax: float
    ufpls_net: float
    ufpls_pot: float
    pcls_gross: float
    pcls_tax: float
    pcls_net: float
    pcls_drawdown_pot: float
    pcls_lump_pot: float
    ufpls_total_wealth: float
    pcls_total_wealth: float
    delta: float


@dataclass
class UFPLSResult:
    """
    @brief Full UFPLS vs PCLS comparison result.

    @param pcls_lump_sum         PCLS tax-free lump sum taken at crystallisation.
    @param starting_pot          Pension pot at crystallisation.
    @param years                 Year-by-year comparison.
    @param lifetime_tax_ufpls    Total income tax paid over projection (UFPLS).
    @param lifetime_tax_pcls     Total income tax paid over projection (PCLS).
    @param terminal_wealth_ufpls Terminal wealth at projection end (UFPLS).
    @param terminal_wealth_pcls  Terminal wealth at projection end (PCLS).
    @param preferred_strategy    'ufpls' | 'pcls' based on lifetime tax saving.
    @param tax_saving_gbp        Lifetime tax saved by preferred strategy.
    @param warnings              Warning messages.
    """
    pcls_lump_sum: float
    starting_pot: float
    years: list[UFPLSYear]
    lifetime_tax_ufpls: float
    lifetime_tax_pcls: float
    terminal_wealth_ufpls: float
    terminal_wealth_pcls: float
    preferred_strategy: str
    tax_saving_gbp: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class CGTHarvestYear:
    """
    @brief CGT harvest recommendation for one tax year.

    @param year                Calendar year.
    @param gia_value           GIA market value at start of year.
    @param cost_basis          Estimated cost basis of the GIA.
    @param unrealised_gain     Estimated unrealised gain (value − cost_basis).
    @param exempt_remaining    CGT exempt amount remaining (£3,000 less prior disposals).
    @param harvest_amount      Amount of gains recommended to crystallise.
    @param cgt_if_harvested    CGT payable if harvested (should be £0 if ≤ exempt).
    @param cgt_if_not_harvested CGT that would be payable if NOT harvested (future est.).
    @param trade_cost          Estimated transaction cost of harvest.
    @param net_saving          Net lifetime CGT saved by harvesting (less trade cost).
    @param action              'harvest' | 'monitor' | 'no_gain' | 'loss_harvest'.
    @param recommendation      Human-readable recommendation.
    """
    year: int
    gia_value: float
    cost_basis: float
    unrealised_gain: float
    exempt_remaining: float
    harvest_amount: float
    cgt_if_harvested: float
    cgt_if_not_harvested: float
    trade_cost: float
    net_saving: float
    action: str
    recommendation: str


@dataclass
class CGTHarvestResult:
    """
    @brief Full CGT harvest schedule.

    @param years                  Year-by-year harvest recommendations.
    @param total_cgt_without      Estimated total CGT without any harvesting.
    @param total_cgt_with         Estimated total CGT with harvest schedule.
    @param total_lifetime_saving  Estimated lifetime CGT saved.
    @param total_trade_costs      Total estimated transaction costs of harvesting.
    @param net_saving             Lifetime saving less transaction costs.
    @param harvest_years          List of years where action = 'harvest'.
    @param warnings               Warning messages.
    """
    years: list[CGTHarvestYear]
    total_cgt_without: float
    total_cgt_with: float
    total_lifetime_saving: float
    total_trade_costs: float
    net_saving: float
    harvest_years: list[int]
    warnings: list[str] = field(default_factory=list)


@dataclass
class TaxOptimiserSummary:
    """
    @brief Combined Phase 8 tax optimiser summary.

    @param band_fill_saving_gbp   Lifetime tax saved by band-filling.
    @param ufpls_saving_gbp       Lifetime tax saved by preferred UFPLS/PCLS strategy.
    @param cgt_harvest_saving_gbp Net lifetime CGT saved by harvest schedule.
    @param total_saving_gbp       Combined total lifetime saving.
    @param top_actions            List of highest-priority recommended actions.
    @param band_fill              BandFillResult.
    @param ufpls                  UFPLSResult.
    @param cgt_harvest            CGTHarvestResult.
    @param warnings               Consolidated warnings.
    """
    band_fill_saving_gbp: float
    ufpls_saving_gbp: float
    cgt_harvest_saving_gbp: float
    total_saving_gbp: float
    top_actions: list[str]
    band_fill: Optional[BandFillResult]
    ufpls: Optional[UFPLSResult]
    cgt_harvest: Optional[CGTHarvestResult]
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Scottish income tax
# ─────────────────────────────────────────────────────────────────────────────


def _scottish_income_tax(gross: float, cfg: dict) -> float:
    """
    @brief Compute Scottish income tax for a given gross income.

    @param gross  Annual gross income (above personal allowance is applied).
    @param cfg    The `scottish_rates` section of the optimiser config.
    @return       Scottish income tax payable.
    """
    pa = _PA   # Scottish PA is same as UK PA
    taxable = max(0.0, gross - pa)
    # PA taper above £100k (same as rest of UK)
    if gross > 100_000:
        reduction = min(pa, (gross - 100_000) * 0.5)
        taxable = max(0.0, gross - max(0.0, pa - reduction))

    bands = cfg.get("bands", [])
    if not bands:
        # Fallback to UK standard if Scottish bands not configured
        return _uk_income_tax(gross)

    tax = 0.0
    prev_from = _PA  # bands start above the PA
    for band in bands:
        band_from = float(band.get("from", 0)) - 1   # inclusive
        band_to   = band.get("to")
        rate      = float(band.get("rate", 0))
        band_to_f = float(band_to) if band_to is not None else float("inf")

        in_band = max(0.0, min(gross, band_to_f) - max(prev_from, band_from))
        tax += in_band * rate
        prev_from = band_to_f

    return round(tax, 2)


def _uk_income_tax(gross: float) -> float:
    """
    @brief Simplified UK income tax (2024/25 bands, no tax profile needed).

    @param gross  Annual gross income.
    @return       Income tax payable.
    """
    pa = _PA
    if gross > 100_000:
        taper = min(pa, (gross - 100_000) * 0.5)
        pa = max(0.0, pa - taper)
    taxable = max(0.0, gross - pa)

    if taxable <= (_BASIC_LIMIT - _PA):
        return round(taxable * _BASIC_RATE, 2)
    elif taxable <= (_HIGHER_LIMIT - _PA):
        return round((_BASIC_LIMIT - _PA) * _BASIC_RATE +
                     (taxable - (_BASIC_LIMIT - _PA)) * _HIGHER_RATE, 2)
    else:
        return round((_BASIC_LIMIT - _PA) * _BASIC_RATE +
                     (_HIGHER_LIMIT - _BASIC_LIMIT) * _HIGHER_RATE +
                     (taxable - (_HIGHER_LIMIT - _PA)) * _ADDNL_RATE, 2)


def _income_tax(gross: float, scottish_cfg: Optional[dict] = None) -> float:
    """
    @brief Compute income tax using Scottish or UK bands.

    @param gross           Annual gross income.
    @param scottish_cfg    Scottish rates config section (None = UK standard).
    @return                Income tax payable.
    """
    if scottish_cfg and scottish_cfg.get("scottish_taxpayer", False):
        return _scottish_income_tax(gross, scottish_cfg)
    return _uk_income_tax(gross)


# ─────────────────────────────────────────────────────────────────────────────
# Band-filler engine
# ─────────────────────────────────────────────────────────────────────────────


class BandFillerEngine:
    """
    @brief Computes the optimal annual pension/ISA drawdown schedule.

    Strategy: each year, draw just enough from pension to fill the target
    tax band (personal allowance + basic-rate band by default), then top up
    from ISA. Compare against a naive proportional drawdown baseline.
    """

    def __init__(self, cfg: dict) -> None:
        """
        @brief Initialise with the optimiser config dict.

        @param cfg  The full optimiser config (`tax_optimiser` key).
        """
        self._cfg = cfg
        self._bf  = cfg.get("band_filler", {})
        self._scot = cfg.get("scottish_rates", {})
        logger.info("BandFillerEngine initialised: target_band=%s",
                    self._bf.get("target_band", "basic_rate"))

    def run(
        self,
        pension_pot: float,
        isa_pot: float,
        gia_pot: float,
        state_pension_annual: float,
        state_pension_start_year: int,
        retirement_year: int,
        death_year: int,
        birth_year: int,
        annual_spending: float,
        pension_growth_rate: float = 0.07,
        isa_growth_rate: float = 0.07,
        inflation_rate: Optional[float] = None,
        rental_income_annual: float = 0.0,
    ) -> BandFillResult:
        """
        @brief Run the band-filler projection from retirement to death.

        @param pension_pot          Pension pot at retirement (GBP).
        @param isa_pot              ISA pot at retirement (GBP).
        @param gia_pot              GIA pot at retirement (GBP, not used in drawdown optimisation but tracked).
        @param state_pension_annual Annual state pension in today's money.
        @param state_pension_start_year Year state pension commences.
        @param retirement_year      First year of retirement.
        @param death_year           Last projection year.
        @param birth_year           Primary person's birth year.
        @param annual_spending      Annual spending target in today's money.
        @param pension_growth_rate  Nominal growth rate of pension pot.
        @param isa_growth_rate      Nominal growth rate of ISA pot.
        @param inflation_rate       CPI for uprating spending + state pension.
        @param rental_income_annual Annual rental income (in today's money).
        @return                     BandFillResult.
        """
        proj_cfg    = self._cfg.get("projection", {})
        infl        = inflation_rate or float(proj_cfg.get("inflation_rate", 0.025))
        naive_pf    = float(self._bf.get("naive_pension_fraction", 0.60))
        target_band = self._bf.get("target_band", "basic_rate")
        buffer      = float(self._bf.get("safety_buffer_gbp", 300.0))
        triple_lock = self._bf.get("state_pension_triple_lock", True)
        sp_floor    = float(self._bf.get("triple_lock_floor", 0.025))

        # Determine target fill limit
        if target_band == "personal_allowance":
            fill_limit = _PA - buffer
        elif target_band == "higher_rate":
            fill_limit = _HIGHER_LIMIT - buffer
        else:  # basic_rate (default)
            fill_limit = _BASIC_LIMIT - buffer

        warnings: list[str] = []

        # Running pots — two parallel tracks (optimal and naive)
        pen_opt  = pension_pot
        isa_opt  = isa_pot
        pen_naive = pension_pot
        isa_naive = isa_pot

        lifetime_tax_opt   = 0.0
        lifetime_tax_naive = 0.0
        years: list[BandFillYear] = []

        isa_exhausted_opt   = None
        isa_exhausted_naive = None
        pen_exhausted_opt   = None
        pen_exhausted_naive = None

        for yr in range(retirement_year, death_year + 1):
            age     = yr - birth_year
            elapsed = yr - retirement_year

            # Inflate spending and state pension
            target_spend = annual_spending * (1 + infl) ** elapsed
            sp_growth    = max(infl, sp_floor) if triple_lock else infl
            sp_this_yr   = (state_pension_annual * (1 + sp_growth) ** elapsed
                            if yr >= state_pension_start_year else 0.0)
            rental_this  = (rental_income_annual * (1 + infl) ** elapsed
                            if self._bf.get("include_rental_income", True) else 0.0)

            # Other income reduces band-fill space
            other_income  = sp_this_yr + rental_this
            band_space_pa = max(0.0, _PA - other_income)
            band_space_br = max(0.0, fill_limit - _PA)  # basic rate portion

            # ── Optimal strategy ─────────────────────────────────────────────
            # Need this much net cash after tax
            net_needed = max(0.0, target_spend - other_income)

            # How much can we draw from pension at 0% + 20% combined?
            # Tax on PA portion = 0, on basic-rate portion = 20%
            # Gross pension to yield net_needed:
            # If net_needed ≤ band_space_pa: draw gross = net_needed (0% tax)
            # If net_needed ≤ band_space_pa + band_space_br × 0.8: partly into basic
            # Draw up to fill_limit gross from pension, rest from ISA

            # Optimal pension draw = fill as much of the band as needed
            max_pension_opt = min(
                pen_opt,   # can't draw more than we have
                fill_limit - other_income,  # fill up to the target band limit
            )
            # Tax on optimal pension draw
            tax_opt_on_pension = _income_tax(
                max(0.0, other_income + max_pension_opt), self._scot
            ) - _income_tax(other_income, self._scot)
            net_from_pension_opt = max_pension_opt - tax_opt_on_pension

            if net_from_pension_opt >= net_needed:
                # We can get enough from pension without filling the full band
                # Binary search for exact pension amount needed
                lo, hi = 0.0, max_pension_opt
                for _ in range(40):
                    mid = (lo + hi) / 2
                    t   = (_income_tax(max(0.0, other_income + mid), self._scot)
                           - _income_tax(other_income, self._scot))
                    if mid - t >= net_needed:
                        hi = mid
                    else:
                        lo = mid
                pension_drawn_opt = round(hi, 2)
                tax_opt_this_yr = round(
                    _income_tax(max(0.0, other_income + pension_drawn_opt), self._scot)
                    - _income_tax(other_income, self._scot), 2
                )
                isa_drawn_opt = max(0.0, net_needed - (pension_drawn_opt - tax_opt_this_yr))
            else:
                # Fill full band from pension, top up from ISA
                pension_drawn_opt = round(max_pension_opt, 2)
                tax_opt_this_yr   = round(tax_opt_on_pension, 2)
                isa_drawn_opt     = max(0.0, net_needed - net_from_pension_opt)

            pension_drawn_opt = min(pension_drawn_opt, pen_opt)
            isa_drawn_opt     = min(isa_drawn_opt, isa_opt)

            # ── Naive strategy ───────────────────────────────────────────────
            gross_naive   = net_needed / (1 - 0.20)  # rough estimate; refine below
            pension_drawn_naive = min(pen_naive, net_needed / (1 - 0.20) * naive_pf)
            isa_drawn_naive     = min(isa_naive, net_needed - (pension_drawn_naive * 0.80))
            # Recompute tax on naive pension draw
            total_naive_gross = other_income + pension_drawn_naive
            tax_naive_this_yr = max(0.0,
                _income_tax(total_naive_gross, self._scot)
                - _income_tax(other_income, self._scot)
            )

            # Clamp to available pot
            pension_drawn_naive = min(pension_drawn_naive, pen_naive)
            isa_drawn_naive     = min(isa_drawn_naive, isa_naive)

            # Tax saved this year
            tax_saved = max(0.0, tax_naive_this_yr - tax_opt_this_yr)

            lifetime_tax_opt   += tax_opt_this_yr
            lifetime_tax_naive += tax_naive_this_yr

            # Grow and deplete pots
            pen_opt   = max(0.0, pen_opt   - pension_drawn_opt)  * (1 + pension_growth_rate)
            isa_opt   = max(0.0, isa_opt   - isa_drawn_opt)      * (1 + isa_growth_rate)
            pen_naive = max(0.0, pen_naive - pension_drawn_naive) * (1 + pension_growth_rate)
            isa_naive = max(0.0, isa_naive - isa_drawn_naive)     * (1 + isa_growth_rate)

            if isa_opt <= 0 and isa_exhausted_opt is None:
                isa_exhausted_opt = yr
                warnings.append(f"ISA exhausted at age {age} ({yr}) on optimal strategy.")
            if isa_naive <= 0 and isa_exhausted_naive is None:
                isa_exhausted_naive = yr
            if pen_opt <= 0 and pen_exhausted_opt is None:
                pen_exhausted_opt = yr
                warnings.append(f"Pension exhausted at age {age} ({yr}) on optimal strategy.")
            if pen_naive <= 0 and pen_exhausted_naive is None:
                pen_exhausted_naive = yr

            # Build action string
            if pension_drawn_opt < max_pension_opt * 0.5:
                action = f"Draw £{pension_drawn_opt:,.0f} from pension (PA only) — low tax year"
            elif band_space_br > 0:
                action = f"Draw £{pension_drawn_opt:,.0f} pension (fills band) + £{isa_drawn_opt:,.0f} ISA"
            else:
                action = f"Draw £{pension_drawn_opt:,.0f} from pension"

            years.append(BandFillYear(
                year=yr, age=age,
                target_spending=round(target_spend, 2),
                other_income=round(other_income, 2),
                band_space_pa=round(band_space_pa, 2),
                band_space_basic=round(band_space_br, 2),
                pension_drawn_opt=pension_drawn_opt,
                pension_drawn_naive=round(pension_drawn_naive, 2),
                isa_drawn_opt=round(isa_drawn_opt, 2),
                isa_drawn_naive=round(isa_drawn_naive, 2),
                tax_opt=tax_opt_this_yr,
                tax_naive=round(tax_naive_this_yr, 2),
                tax_saved=round(tax_saved, 2),
                pension_pot_opt=round(pen_opt, 2),
                pension_pot_naive=round(pen_naive, 2),
                isa_pot_opt=round(isa_opt, 2),
                isa_pot_naive=round(isa_naive, 2),
                action=action,
            ))

        total_saved = round(lifetime_tax_naive - lifetime_tax_opt, 2)
        logger.info(
            "BandFillerEngine: lifetime_tax_opt=£%.0f naive=£%.0f saved=£%.0f",
            lifetime_tax_opt, lifetime_tax_naive, total_saved,
        )

        return BandFillResult(
            years=years,
            lifetime_tax_opt=round(lifetime_tax_opt, 2),
            lifetime_tax_naive=round(lifetime_tax_naive, 2),
            lifetime_tax_saved=max(0.0, total_saved),
            isa_exhausted_year_opt=isa_exhausted_opt,
            isa_exhausted_year_naive=isa_exhausted_naive,
            pension_exhausted_year_opt=pen_exhausted_opt,
            pension_exhausted_year_naive=pen_exhausted_naive,
            warnings=warnings,
        )


# ─────────────────────────────────────────────────────────────────────────────
# UFPLS vs PCLS engine
# ─────────────────────────────────────────────────────────────────────────────


class UFPLSEngine:
    """
    @brief Models UFPLS vs PCLS pension crystallisation strategies.

    UFPLS: Uncrystallised Funds Pension Lump Sum — each withdrawal is
    25% tax-free and 75% taxable. The tax-free allowance is spread across
    every withdrawal throughout retirement.

    PCLS: Pension Commencement Lump Sum — take 25% of the pot as a single
    tax-free lump sum at crystallisation. The remaining 75% enters a
    drawdown fund and every subsequent withdrawal is fully taxable.
    """

    def __init__(self, cfg: dict) -> None:
        self._cfg  = cfg
        self._ucfg = cfg.get("ufpls", {})
        self._scot = cfg.get("scottish_rates", {})

    def run(
        self,
        pension_pot: float,
        crystallisation_year: int,
        death_year: int,
        birth_year: int,
        annual_withdrawal: float,
        other_income: float = 0.0,
        pension_growth_rate: float = 0.07,
        lump_sum_growth_rate: Optional[float] = None,
        inflation_rate: Optional[float] = None,
    ) -> UFPLSResult:
        """
        @brief Run the UFPLS vs PCLS comparison projection.

        @param pension_pot          Pension pot at crystallisation (GBP).
        @param crystallisation_year First year of drawdown / crystallisation.
        @param death_year           Last projection year.
        @param birth_year           Primary person's birth year.
        @param annual_withdrawal    Annual cash withdrawal target.
        @param other_income         Other income per year (state pension, etc.).
        @param pension_growth_rate  Nominal growth on drawdown pot.
        @param lump_sum_growth_rate Growth on reinvested PCLS lump sum (None = same as pension).
        @param inflation_rate       CPI for uprating withdrawals.
        @return                     UFPLSResult.
        """
        proj_cfg    = self._cfg.get("projection", {})
        infl        = inflation_rate or float(proj_cfg.get("inflation_rate", 0.025))
        tf_frac     = float(self._ucfg.get("tax_free_fraction", 0.25))
        reinvest    = self._ucfg.get("pcls_reinvest_lump_sum", True)
        ls_growth   = lump_sum_growth_rate or float(
            self._ucfg.get("pcls_reinvest_growth_rate", 0.06)
        )

        warnings: list[str] = []

        # PCLS: take 25% as lump sum, 75% into drawdown
        pcls_lump = round(pension_pot * tf_frac, 2)
        pcls_draw_start = round(pension_pot * (1 - tf_frac), 2)

        # Running pots
        ufpls_pot   = pension_pot
        pcls_ddpot  = pcls_draw_start
        pcls_lumppot = pcls_lump if reinvest else 0.0

        lifetime_tax_ufpls = 0.0
        lifetime_tax_pcls  = 0.0
        years: list[UFPLSYear] = []

        for yr in range(crystallisation_year, death_year + 1):
            age     = yr - birth_year
            elapsed = yr - crystallisation_year
            target  = annual_withdrawal * (1 + infl) ** elapsed
            net_needed = max(0.0, target - other_income)

            # ── UFPLS ───────────────────────────────────────────────────────
            # Gross UFPLS = net_needed / (1 - tax_rate_on_75%)
            # Iteratively solve: gross − tax_on(75%_of_gross) = net_needed
            ufpls_gross = 0.0
            ufpls_tf    = 0.0
            ufpls_tax   = 0.0
            ufpls_net   = 0.0

            if ufpls_pot > 0 and net_needed > 0:
                lo, hi = 0.0, min(ufpls_pot, net_needed * 3)
                for _ in range(50):
                    mid = (lo + hi) / 2
                    tf  = mid * tf_frac
                    txb = mid - tf
                    tx  = max(0.0,
                               _income_tax(other_income + txb, self._scot)
                               - _income_tax(other_income, self._scot))
                    net = mid - tx
                    if net >= net_needed:
                        hi = mid
                    else:
                        lo = mid
                ufpls_gross = round(min(hi, ufpls_pot), 2)
                ufpls_tf    = round(ufpls_gross * tf_frac, 2)
                ufpls_txb   = round(ufpls_gross - ufpls_tf, 2)
                ufpls_tax   = round(max(0.0,
                                        _income_tax(other_income + ufpls_txb, self._scot)
                                        - _income_tax(other_income, self._scot)), 2)
                ufpls_net   = round(ufpls_gross - ufpls_tax, 2)
            else:
                ufpls_txb = 0.0

            # ── PCLS ────────────────────────────────────────────────────────
            pcls_gross = 0.0
            pcls_tax   = 0.0
            pcls_net   = 0.0

            if pcls_ddpot > 0 and net_needed > 0:
                lo, hi = 0.0, min(pcls_ddpot, net_needed * 3)
                for _ in range(50):
                    mid = (lo + hi) / 2
                    tx  = max(0.0,
                               _income_tax(other_income + mid, self._scot)
                               - _income_tax(other_income, self._scot))
                    if mid - tx >= net_needed:
                        hi = mid
                    else:
                        lo = mid
                pcls_gross = round(min(hi, pcls_ddpot), 2)
                pcls_tax   = round(max(0.0,
                                       _income_tax(other_income + pcls_gross, self._scot)
                                       - _income_tax(other_income, self._scot)), 2)
                pcls_net   = round(pcls_gross - pcls_tax, 2)

            # Update pots and accumulate tax
            lifetime_tax_ufpls += ufpls_tax
            lifetime_tax_pcls  += pcls_tax

            ufpls_pot   = max(0.0, ufpls_pot  - ufpls_gross) * (1 + pension_growth_rate)
            pcls_ddpot  = max(0.0, pcls_ddpot - pcls_gross)  * (1 + pension_growth_rate)
            pcls_lumppot = pcls_lumppot * (1 + ls_growth)

            ufpls_wealth = ufpls_pot
            pcls_wealth  = pcls_ddpot + pcls_lumppot

            years.append(UFPLSYear(
                year=yr, age=age,
                withdrawal_target=round(target, 2),
                ufpls_gross=ufpls_gross,
                ufpls_tax_free=ufpls_tf,
                ufpls_taxable=round(ufpls_txb, 2),
                ufpls_tax=ufpls_tax,
                ufpls_net=ufpls_net,
                ufpls_pot=round(ufpls_pot, 2),
                pcls_gross=pcls_gross,
                pcls_tax=pcls_tax,
                pcls_net=pcls_net,
                pcls_drawdown_pot=round(pcls_ddpot, 2),
                pcls_lump_pot=round(pcls_lumppot, 2),
                ufpls_total_wealth=round(ufpls_wealth, 2),
                pcls_total_wealth=round(pcls_wealth, 2),
                delta=round(ufpls_wealth - pcls_wealth, 2),
            ))

        terminal_ufpls = years[-1].ufpls_pot if years else 0.0
        terminal_pcls  = (years[-1].pcls_drawdown_pot + years[-1].pcls_lump_pot) if years else 0.0

        tax_diff = lifetime_tax_ufpls - lifetime_tax_pcls
        preferred = "pcls" if tax_diff > 0 else "ufpls"
        saving    = abs(tax_diff)

        logger.info(
            "UFPLSEngine: tax_ufpls=£%.0f tax_pcls=£%.0f preferred=%s saving=£%.0f",
            lifetime_tax_ufpls, lifetime_tax_pcls, preferred, saving,
        )

        return UFPLSResult(
            pcls_lump_sum=pcls_lump,
            starting_pot=pension_pot,
            years=years,
            lifetime_tax_ufpls=round(lifetime_tax_ufpls, 2),
            lifetime_tax_pcls=round(lifetime_tax_pcls, 2),
            terminal_wealth_ufpls=round(terminal_ufpls, 2),
            terminal_wealth_pcls=round(terminal_pcls, 2),
            preferred_strategy=preferred,
            tax_saving_gbp=round(saving, 2),
            warnings=warnings,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CGT harvest scheduler
# ─────────────────────────────────────────────────────────────────────────────


class CGTHarvestEngine:
    """
    @brief Schedules annual CGT harvesting for a GIA account.

    Each year, checks whether the unrealised gain is below the annual CGT
    exemption (£3,000 for 2024/25). If so, recommends selling and rebuying
    to reset the cost basis — this eliminates that gain from future CGT
    without paying any tax now.
    """

    def __init__(self, cfg: dict) -> None:
        self._cfg  = cfg
        self._hcfg = cfg.get("cgt_harvest", {})

    def run(
        self,
        gia_value: float,
        gia_cost_basis: float,
        first_year: int,
        last_year: int,
        gia_growth_rate: Optional[float] = None,
        existing_income: float = 0.0,
    ) -> CGTHarvestResult:
        """
        @brief Run the CGT harvest schedule projection.

        @param gia_value        Current GIA market value (GBP).
        @param gia_cost_basis   Estimated cost basis of the GIA.
        @param first_year       First year to model.
        @param last_year        Last year to model.
        @param gia_growth_rate  Annual nominal return on the GIA.
        @param existing_income  Other income (used to determine CGT rate).
        @return                 CGTHarvestResult.
        """
        exempt      = float(self._hcfg.get("annual_exempt_gbp", _CGT_EXEMPT))
        trigger     = float(self._hcfg.get("harvest_trigger_gbp", 500.0))
        max_sell    = float(self._hcfg.get("max_sell_pct", 1.0))
        trade_cost  = float(self._hcfg.get("estimated_trade_cost_gbp", 50.0))
        loss_harvest = self._hcfg.get("include_loss_harvesting", True)
        growth      = gia_growth_rate or float(self._hcfg.get("fallback_gain_rate", 0.07))

        proj = self._cfg.get("projection", {})

        warnings: list[str] = []
        years: list[CGTHarvestYear] = []

        value  = gia_value
        basis  = gia_cost_basis
        total_cgt_without = 0.0
        total_cgt_with    = 0.0
        total_trade_costs = 0.0
        harvest_years: list[int] = []

        for yr in range(first_year, last_year + 1):
            gain = max(-value, value - basis)  # unrealised gain (negative = loss)

            # CGT that would accrue if sold right now (without harvesting)
            taxable_gain = max(0.0, gain - exempt)
            in_basic = max(0.0, _BASIC_LIMIT - existing_income - _PA)
            basic_gain   = min(taxable_gain, in_basic)
            higher_gain  = max(0.0, taxable_gain - basic_gain)
            cgt_no_harvest = round(basic_gain * _CGT_BASIC + higher_gain * _CGT_HIGHER, 2)

            action = "no_gain"
            harvest_amount = 0.0
            cgt_if_harvested = 0.0
            cost_this_yr = 0.0
            net_saving = 0.0
            rec = "No action required — no significant unrealised gain."

            if gain > trigger and gain <= exempt:
                # Can crystallise the entire gain tax-free this year
                action = "harvest"
                harvest_amount = gain * max_sell
                cgt_if_harvested = 0.0
                cost_this_yr = trade_cost
                net_saving = cgt_no_harvest - cost_this_yr
                basis = value  # reset cost basis
                rec = (f"Sell and rebuy — crystallise £{gain:,.0f} gain tax-free "
                       f"(within £{exempt:,.0f} exemption). Saves ~£{net_saving:,.0f} future CGT.")
                harvest_years.append(yr)

            elif gain > exempt:
                # Can only partially harvest (up to exempt amount)
                action = "harvest"
                partial = min(gain, exempt) / gain * value
                harvest_amount = partial
                cgt_if_harvested = 0.0
                cost_this_yr = trade_cost
                net_saving = (exempt * _CGT_BASIC) - cost_this_yr
                # Update cost basis partially
                frac = partial / value
                basis = basis + (value - basis) * frac  # blended cost basis
                rec = (f"Partial harvest — crystallise £{exempt:,.0f} of £{gain:,.0f} gain "
                       f"tax-free. Remaining £{gain-exempt:,.0f} deferred.")
                harvest_years.append(yr)

            elif gain < -trigger and loss_harvest:
                action = "loss_harvest"
                harvest_amount = abs(gain)
                cgt_if_harvested = 0.0
                cost_this_yr = trade_cost
                net_saving = abs(gain) * _CGT_BASIC - cost_this_yr
                basis = value
                rec = f"Loss harvest — crystallise £{abs(gain):,.0f} loss to offset future gains."

            elif gain > 0:
                action = "monitor"
                rec = f"Unrealised gain £{gain:,.0f} — below harvest trigger. Monitor."

            total_cgt_without += cgt_no_harvest
            total_cgt_with    += cgt_if_harvested
            total_trade_costs += cost_this_yr

            years.append(CGTHarvestYear(
                year=yr,
                gia_value=round(value, 2),
                cost_basis=round(basis, 2),
                unrealised_gain=round(gain, 2),
                exempt_remaining=exempt,
                harvest_amount=round(harvest_amount, 2),
                cgt_if_harvested=cgt_if_harvested,
                cgt_if_not_harvested=cgt_no_harvest,
                trade_cost=round(cost_this_yr, 2),
                net_saving=round(net_saving, 2),
                action=action,
                recommendation=rec,
            ))

            # Grow the GIA for next year
            value = value * (1 + growth)
            # Basis grows only by new contributions; gains accrue from market

        total_saving = total_cgt_without - total_cgt_with
        net = total_saving - total_trade_costs

        logger.info(
            "CGTHarvestEngine: cgt_without=£%.0f with=£%.0f trade_costs=£%.0f net=£%.0f",
            total_cgt_without, total_cgt_with, total_trade_costs, net,
        )

        return CGTHarvestResult(
            years=years,
            total_cgt_without=round(total_cgt_without, 2),
            total_cgt_with=round(total_cgt_with, 2),
            total_lifetime_saving=round(total_saving, 2),
            total_trade_costs=round(total_trade_costs, 2),
            net_saving=round(net, 2),
            harvest_years=harvest_years,
            warnings=warnings,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Master tax optimiser
# ─────────────────────────────────────────────────────────────────────────────


class TaxOptimiser:
    """
    @brief Phase 8 master tax optimiser.

    Runs all three strategies against the scenario data and returns a
    combined TaxOptimiserSummary with lifetime savings and top actions.

    Usage::

        cfg = load_optimiser_config("config/tax/optimiser_config.yaml")
        optimiser = TaxOptimiser(cfg)
        result = optimiser.run(scenario_dict)
    """

    def __init__(self, cfg: dict) -> None:
        """
        @brief Initialise the tax optimiser from a loaded config dict.

        @param cfg  Dict loaded from optimiser_config.yaml.
        """
        self._cfg     = cfg.get("tax_optimiser", cfg)
        self._bf_eng  = BandFillerEngine(self._cfg)
        self._ufpls   = UFPLSEngine(self._cfg)
        self._cgt     = CGTHarvestEngine(self._cfg)

    def run(self, scenario: dict) -> TaxOptimiserSummary:
        """
        @brief Run all enabled optimisers against a scenario dict.

        @param scenario  Raw scenario YAML dict (top-level 'scenario' or root).
        @return          TaxOptimiserSummary.
        """
        warnings: list[str] = []
        sc = scenario.get("scenario", scenario)

        # ── Extract scenario inputs ───────────────────────────────────────────
        people   = sc.get("people", [])
        primary  = people[0] if people else {}
        birth_yr = int(str(primary.get("date_of_birth", "1980-01-01"))[:4])
        retire_age = int(primary.get("retirement_age", 60))
        life_exp   = int(primary.get("life_expectancy", 87))
        retire_yr  = birth_yr + retire_age
        death_yr   = birth_yr + life_exp

        # State pension
        sp = primary.get("state_pension", {})
        sp_weekly  = float(sp.get("weekly_amount", 221.20))
        sp_start_age = int(sp.get("expected_start_age", 67))
        sp_yr      = birth_yr + sp_start_age
        sp_annual  = sp_weekly * 52

        # Pots from scenario
        pension_funds = sc.get("pension_funds", [])
        pension_val = sum(float(p.get("current_value", 0)) for p in pension_funds)
        pension_growth = (float(pension_funds[0].get("assumed_growth_rate", 0.07))
                          if pension_funds else 0.07)

        inv_accounts = sc.get("investment_accounts", [])
        isa_val = sum(float(a.get("current_value", 0)) for a in inv_accounts
                      if "ISA" in str(a.get("account_type", "")).upper())
        gia_val = sum(float(a.get("current_value", 0)) for a in inv_accounts
                      if "GIA" in str(a.get("account_type", "")).upper())
        isa_growth = 0.07

        # Annual spending from expenses
        expenses = sc.get("expense_buckets", [])
        annual_spend = sum(float(e.get("annual_amount", 0)) for e in expenses
                           if not e.get("end_date"))
        annual_spend = annual_spend or 40_000.0

        proj_cfg = self._cfg.get("projection", {})
        proj_end = int(proj_cfg.get("end_year", death_yr))

        bf_result: Optional[BandFillResult] = None
        ufpls_result: Optional[UFPLSResult] = None
        cgt_result: Optional[CGTHarvestResult] = None

        # ── Band-filler ───────────────────────────────────────────────────────
        if self._cfg.get("band_filler", {}).get("enabled", True):
            try:
                bf_result = self._bf_eng.run(
                    pension_pot=pension_val,
                    isa_pot=isa_val,
                    gia_pot=gia_val,
                    state_pension_annual=sp_annual,
                    state_pension_start_year=sp_yr,
                    retirement_year=retire_yr,
                    death_year=min(death_yr, proj_end),
                    birth_year=birth_yr,
                    annual_spending=annual_spend,
                    pension_growth_rate=pension_growth,
                    isa_growth_rate=isa_growth,
                )
            except Exception as exc:
                warnings.append(f"Band-filler failed: {exc}")
                logger.error("Band-filler error: %s", exc, exc_info=True)

        # ── UFPLS ─────────────────────────────────────────────────────────────
        if self._cfg.get("ufpls", {}).get("enabled", True) and pension_val > 0:
            try:
                ufpls_result = self._ufpls.run(
                    pension_pot=pension_val,
                    crystallisation_year=retire_yr,
                    death_year=min(death_yr, proj_end),
                    birth_year=birth_yr,
                    annual_withdrawal=annual_spend,
                    other_income=sp_annual,
                    pension_growth_rate=pension_growth,
                )
            except Exception as exc:
                warnings.append(f"UFPLS comparison failed: {exc}")
                logger.error("UFPLS error: %s", exc, exc_info=True)

        # ── CGT harvest ───────────────────────────────────────────────────────
        if self._cfg.get("cgt_harvest", {}).get("enabled", True) and gia_val > 0:
            try:
                # Assume 40% of GIA is gains (no cost basis data without statement)
                gia_basis = gia_val * 0.60
                cgt_result = self._cgt.run(
                    gia_value=gia_val,
                    gia_cost_basis=gia_basis,
                    first_year=date.today().year,
                    last_year=min(death_yr, proj_end),
                    existing_income=sp_annual,
                )
            except Exception as exc:
                warnings.append(f"CGT harvest failed: {exc}")
                logger.error("CGT harvest error: %s", exc, exc_info=True)

        # ── Summary ───────────────────────────────────────────────────────────
        bf_saving   = bf_result.lifetime_tax_saved if bf_result else 0.0
        ufpls_saving = ufpls_result.tax_saving_gbp if ufpls_result else 0.0
        cgt_saving  = cgt_result.net_saving if cgt_result else 0.0
        total       = round(bf_saving + ufpls_saving + cgt_saving, 2)

        top_actions: list[str] = []
        if bf_saving > 0:
            top_actions.append(
                f"Band-filling: draw £{pension_val * 0.04:,.0f}/yr from pension to fill "
                f"basic-rate band, rest from ISA — saves £{bf_saving:,.0f} lifetime tax."
            )
        if ufpls_result and ufpls_result.preferred_strategy == "ufpls":
            top_actions.append(
                f"Use UFPLS (25% tax-free per withdrawal) rather than taking a single PCLS "
                f"lump sum — saves £{ufpls_saving:,.0f} in lifetime income tax."
            )
        elif ufpls_result and ufpls_result.preferred_strategy == "pcls":
            top_actions.append(
                f"Take PCLS lump sum (£{ufpls_result.pcls_lump_sum:,.0f} tax-free) at "
                f"retirement — saves £{ufpls_saving:,.0f} vs UFPLS strategy."
            )
        if cgt_saving > 0 and cgt_result:
            top_actions.append(
                f"CGT harvest annually: realise gains below £{_CGT_EXEMPT:,.0f} exemption "
                f"each year — saves £{cgt_saving:,.0f} net lifetime CGT."
            )
        if not top_actions:
            top_actions.append(
                "No significant optimisation opportunities identified. "
                "Check that pension, ISA, and GIA values are configured in the scenario."
            )

        return TaxOptimiserSummary(
            band_fill_saving_gbp=round(bf_saving, 2),
            ufpls_saving_gbp=round(ufpls_saving, 2),
            cgt_harvest_saving_gbp=round(cgt_saving, 2),
            total_saving_gbp=total,
            top_actions=top_actions,
            band_fill=bf_result,
            ufpls=ufpls_result,
            cgt_harvest=cgt_result,
            warnings=warnings,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────────────────────


def load_optimiser_config(path: str) -> dict:
    """
    @brief Load the tax optimiser YAML config from disk.

    @param path  Absolute or relative path to optimiser_config.yaml.
    @return      Dict with 'tax_optimiser' top-level key.
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file is invalid YAML.
    """
    logger.info("Loading tax optimiser config from: %s", path)
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
