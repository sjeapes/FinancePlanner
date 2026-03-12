"""
@file tax_engine.py
@brief Tax calculation engine for LifeLedger.

Supports UK (PAYE + NI + CGT), US Federal, and Generic jurisdictions.
All calculations work on annual gross amounts and return structured
TaxResult objects. No external dependencies beyond stdlib.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from backend.models.models import (
    Jurisdiction, TaxProfile, TaxTreatment,
)

logger = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class TaxResult:
    """
    @brief Result of a single tax calculation.
    @param gross_income Gross income before any deductions.
    @param income_tax Income tax payable.
    @param national_insurance NI / payroll tax payable.
    @param net_income Take-home income after all deductions.
    @param effective_rate Combined effective tax rate.
    @param marginal_rate Marginal income tax rate band.
    @param breakdown Detailed breakdown dict for logging/UI.
    """
    gross_income: float = 0.0
    income_tax: float = 0.0
    national_insurance: float = 0.0
    net_income: float = 0.0
    effective_rate: float = 0.0
    marginal_rate: float = 0.0
    breakdown: dict = field(default_factory=dict)

    def total_deductions(self) -> float:
        """@brief Total tax + NI deducted."""
        return self.income_tax + self.national_insurance


@dataclass
class CGTResult:
    """
    @brief Capital gains tax calculation result.
    @param gain Total capital gain.
    @param exempt_amount Annual CGT exemption applied.
    @param taxable_gain Gain after exemption.
    @param cgt_basic Rate applied up to basic rate threshold.
    @param cgt_higher Rate applied above threshold.
    @param total_cgt Total CGT payable.
    """
    gain: float = 0.0
    exempt_amount: float = 0.0
    taxable_gain: float = 0.0
    cgt_basic: float = 0.0
    cgt_higher: float = 0.0
    total_cgt: float = 0.0


# ── Band calculator (shared logic) ───────────────────────────────────────────

def _apply_bands(income: float, bands: list, floor: float = 0.0) -> tuple[float, float]:
    """
    @brief Apply a list of progressive tax bands to a taxable income.
    @param income Taxable income above any allowances.
    @param bands List of TaxBand (must be in ascending limit order).
    @param floor Carry-in from prior bands (used for NI, CGT overlap).
    @return Tuple of (total_tax, marginal_rate).
    """
    total_tax = 0.0
    marginal_rate = 0.0
    remaining = income
    prev_limit = floor

    for band in bands:
        if remaining <= 0:
            break
        upper = band.limit if band.limit is not None else float("inf")
        width = upper - prev_limit
        if width <= 0:
            prev_limit = upper
            continue
        taxable_in_band = min(remaining, width)
        total_tax += taxable_in_band * band.rate
        marginal_rate = band.rate
        remaining -= taxable_in_band
        prev_limit = upper

    return total_tax, marginal_rate


# ── UK Tax calculations ───────────────────────────────────────────────────────

def calculate_uk_income_tax(
    gross: float,
    profile: TaxProfile,
    pension_contributions: float = 0.0,
) -> tuple[float, float]:
    """
    @brief Calculate UK income tax applying personal allowance taper.
    @param gross Gross income.
    @param profile TaxProfile for UK.
    @param pension_contributions Pre-tax pension contributions (reduce taxable).
    @return Tuple of (income_tax, marginal_rate).
    """
    try:
        adjusted_gross = max(0.0, gross - pension_contributions)

        # Personal allowance taper: £1 reduction per £2 over £100k
        pa = profile.personal_allowance
        taper_threshold = 100_000.0
        if adjusted_gross > taper_threshold:
            reduction = min(pa, (adjusted_gross - taper_threshold) * 0.5)
            pa = max(0.0, pa - reduction)

        taxable = max(0.0, adjusted_gross - pa)
        tax, marginal = _apply_bands(taxable, profile.income_tax_bands)
        return tax, marginal
    except Exception as exc:
        logger.error("calculate_uk_income_tax: %s", exc, exc_info=True)
        return 0.0, 0.0


def calculate_uk_ni(gross: float, profile: TaxProfile) -> float:
    """
    @brief Calculate UK Class 1 National Insurance for PAYE employees.
    @param gross Gross income.
    @param profile TaxProfile with ni_bands configured.
    @return NI payable.
    """
    try:
        ni, _ = _apply_bands(gross, profile.ni_bands)
        return ni
    except Exception as exc:
        logger.error("calculate_uk_ni: %s", exc, exc_info=True)
        return 0.0


def calculate_uk_self_employed_ni(gross: float, profile: TaxProfile) -> float:
    """
    @brief Calculate UK Class 4 NI for self-employed income.
    @param gross Gross self-employed profit.
    @param profile TaxProfile with ni_bands for self-employed.
    @return Class 4 NI payable.
    """
    try:
        ni, _ = _apply_bands(gross, profile.ni_bands)
        # Class 2: small flat weekly contribution if above small profits threshold
        small_profits_threshold = getattr(profile, "small_profits_threshold", 12570)
        class2_weekly = getattr(profile, "class2_weekly", 3.45)
        class2 = class2_weekly * 52 if gross > small_profits_threshold else 0.0
        return ni + class2
    except Exception as exc:
        logger.error("calculate_uk_self_employed_ni: %s", exc, exc_info=True)
        return 0.0


def calculate_uk_cgt(
    gain: float,
    existing_income: float,
    profile: TaxProfile,
) -> CGTResult:
    """
    @brief Calculate UK CGT considering basic/higher rate boundary.
    @param gain Total capital gain from disposal.
    @param existing_income Other income in the same tax year.
    @param profile TaxProfile with cgt config.
    @return CGTResult with full breakdown.
    """
    try:
        cgt_cfg = profile.cgt or {}
        exempt = float(cgt_cfg.get("annual_exempt", 3000))
        basic_rate = float(cgt_cfg.get("basic_rate", 0.10))
        higher_rate = float(cgt_cfg.get("higher_rate", 0.20))

        taxable = max(0.0, gain - exempt)
        if taxable == 0:
            return CGTResult(gain=gain, exempt_amount=exempt)

        # Determine how much of basic rate band remains
        basic_limit = 50270.0  # 2024/25
        pa = profile.personal_allowance
        remaining_basic = max(0.0, basic_limit - max(0.0, existing_income - pa))

        basic_gain = min(taxable, remaining_basic)
        higher_gain = max(0.0, taxable - basic_gain)

        cgt_basic_amount = basic_gain * basic_rate
        cgt_higher_amount = higher_gain * higher_rate
        total = cgt_basic_amount + cgt_higher_amount

        return CGTResult(
            gain=gain,
            exempt_amount=exempt,
            taxable_gain=taxable,
            cgt_basic=cgt_basic_amount,
            cgt_higher=cgt_higher_amount,
            total_cgt=total,
        )
    except Exception as exc:
        logger.error("calculate_uk_cgt: %s", exc, exc_info=True)
        return CGTResult(gain=gain)


# ── US Federal calculations ───────────────────────────────────────────────────

def calculate_us_federal_income_tax(
    gross: float,
    profile: TaxProfile,
    filing_status: str = "single",
) -> tuple[float, float]:
    """
    @brief Calculate US Federal income tax with standard deduction.
    @param gross Gross income.
    @param profile TaxProfile for US Federal.
    @param filing_status 'single' or 'married'.
    @return Tuple of (income_tax, marginal_rate).
    """
    try:
        std_deduction = float(
            profile.allowances.get("standard_deduction", 14_600)
            if filing_status == "single"
            else profile.allowances.get("standard_deduction_married", 29_200)
        )
        taxable = max(0.0, gross - std_deduction)
        tax, marginal = _apply_bands(taxable, profile.income_tax_bands)
        return tax, marginal
    except Exception as exc:
        logger.error("calculate_us_federal_income_tax: %s", exc, exc_info=True)
        return 0.0, 0.0


def calculate_fica(gross: float, profile: TaxProfile) -> float:
    """
    @brief Calculate US FICA taxes (Social Security + Medicare).
    @param gross Gross wages.
    @param profile TaxProfile with fica config.
    @return Total FICA employee share.
    """
    try:
        fica = profile.raw.get("fica", {}) if hasattr(profile, "raw") else {}
        ss_rate = float(fica.get("social_security_rate", 0.062))
        ss_wage_base = float(fica.get("social_security_wage_base", 168_600))
        mc_rate = float(fica.get("medicare_rate", 0.0145))
        add_mc_rate = float(fica.get("additional_medicare_rate", 0.009))
        add_mc_threshold = float(fica.get("additional_medicare_threshold", 200_000))

        ss = min(gross, ss_wage_base) * ss_rate
        medicare = gross * mc_rate
        add_medicare = max(0.0, gross - add_mc_threshold) * add_mc_rate
        return ss + medicare + add_medicare
    except Exception as exc:
        logger.error("calculate_fica: %s", exc, exc_info=True)
        return 0.0


# ── Generic jurisdiction ──────────────────────────────────────────────────────

def calculate_generic_tax(gross: float, profile: TaxProfile) -> tuple[float, float]:
    """
    @brief Calculate tax for generic/configurable jurisdiction.
    @param gross Gross income.
    @param profile TaxProfile with income_tax_bands.
    @return Tuple of (income_tax, marginal_rate).
    """
    try:
        taxable = max(0.0, gross - profile.personal_allowance)
        return _apply_bands(taxable, profile.income_tax_bands)
    except Exception as exc:
        logger.error("calculate_generic_tax: %s", exc, exc_info=True)
        return 0.0, 0.0


# ── Main dispatcher ───────────────────────────────────────────────────────────

def calculate_net_income(
    gross: float,
    tax_treatment: TaxTreatment,
    profile: TaxProfile,
    pension_contributions: float = 0.0,
    filing_status: str = "single",
) -> TaxResult:
    """
    @brief Calculate net income and all tax deductions for a given source.

    Dispatches to jurisdiction-specific calculators based on profile.
    Income does not auto-add to net worth — caller must route contributions.

    @param gross Gross annual income amount.
    @param tax_treatment How the income is taxed (PAYE, self_employed, etc.).
    @param profile TaxProfile for the person.
    @param pension_contributions Pre-tax pension contributions (reduces UK taxable).
    @param filing_status US filing status ('single' | 'married').
    @return TaxResult with income_tax, NI, net_income, and breakdown.
    """
    if gross <= 0:
        return TaxResult(gross_income=0.0, net_income=0.0)

    income_tax = 0.0
    ni = 0.0
    marginal = 0.0
    breakdown: dict = {}

    try:
        jur = profile.jurisdiction

        if jur == Jurisdiction.UK:
            if tax_treatment == TaxTreatment.PAYE:
                income_tax, marginal = calculate_uk_income_tax(
                    gross, profile, pension_contributions
                )
                ni = calculate_uk_ni(gross, profile)
                breakdown = {
                    "income_tax": income_tax,
                    "ni_class1": ni,
                    "pension_contributions": pension_contributions,
                }
            elif tax_treatment == TaxTreatment.SELF_EMPLOYED:
                income_tax, marginal = calculate_uk_income_tax(gross, profile)
                ni = calculate_uk_self_employed_ni(gross, profile)
                breakdown = {"income_tax": income_tax, "ni_class4_plus_class2": ni}
            elif tax_treatment in (
                TaxTreatment.PENSION_DRAWDOWN, TaxTreatment.STATE_PENSION
            ):
                income_tax, marginal = calculate_uk_income_tax(gross, profile)
                ni = 0.0  # no NI on pension income
                breakdown = {"income_tax": income_tax, "ni": 0.0}
            elif tax_treatment == TaxTreatment.RENTAL:
                income_tax, marginal = calculate_uk_income_tax(gross, profile)
                ni = 0.0
                breakdown = {"income_tax": income_tax}
            else:
                income_tax, marginal = calculate_uk_income_tax(gross, profile)
                ni = 0.0
                breakdown = {"income_tax": income_tax}

        elif jur == Jurisdiction.US_FEDERAL:
            income_tax, marginal = calculate_us_federal_income_tax(
                gross, profile, filing_status
            )
            ni = calculate_fica(gross, profile)
            breakdown = {"federal_income_tax": income_tax, "fica": ni}

        else:
            income_tax, marginal = calculate_generic_tax(gross, profile)
            breakdown = {"income_tax": income_tax}

        net = max(0.0, gross - income_tax - ni)
        effective = (income_tax + ni) / gross if gross > 0 else 0.0

        result = TaxResult(
            gross_income=gross,
            income_tax=round(income_tax, 2),
            national_insurance=round(ni, 2),
            net_income=round(net, 2),
            effective_rate=round(effective, 4),
            marginal_rate=marginal,
            breakdown=breakdown,
        )

        logger.debug(
            "calculate_net_income: gross=£%.0f → tax=£%.0f NI=£%.0f "
            "net=£%.0f (eff %.1f%%)",
            gross, income_tax, ni, net, effective * 100,
        )
        return result

    except Exception as exc:
        logger.error("calculate_net_income: unexpected error for gross=%.0f: %s",
                     gross, exc, exc_info=True)
        return TaxResult(gross_income=gross, net_income=gross)
