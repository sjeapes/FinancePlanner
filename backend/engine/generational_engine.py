"""
@file generational_engine.py
@brief Phase 7 generational planning engine for LifeLedger.

Projects the financial trajectory of offspring from childhood through their
full working life and retirement, modelling:

  - Career salary progression (10 archetype career paths, UK and US curves)
  - UK taxes (PAYE via tax_engine.py) and US federal taxes
  - Contributions to ISA/SIPP (UK) or 401k/Roth/taxable (US)
  - University costs and funding (UK Plan 5 loan, US 529 plan, LISA)
  - FIRE date detection (4% SWR against target expenses)
  - Wealth transfer from parents: estate net of IHT / US estate tax
  - Combined family wealth timeline (parents + offspring on one axis)

Key output classes:
  ``OffspringProjection``      — year-by-year offspring timeline
  ``WealthTransfer``           — estate net of tax passed to offspring
  ``GenerationalResult``       — combined parents + offspring + transfer

Validation targets (mid scenario):
  UK retirement wealth at 2045:  ~£5.5M
  US retirement wealth at 2045:  ~$12.9M
  Estate to offspring (~2070):   £24M (UK path) / $53M (US path)

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

logger = logging.getLogger("lifeledger.generational")


# ─────────────────────────────────────────────────────────────────────────────
# Config dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CareerSalaryCurve:
    """
    @brief Salary milestones for one career path in one country.

    @param entry_salary    Starting salary (age = entry_age).
    @param entry_age       Age at career start.
    @param mid_salary      Salary at mid-career milestone.
    @param mid_age         Age at mid-career milestone.
    @param senior_salary   Salary at senior milestone.
    @param senior_age      Age at senior milestone.
    @param peak_salary     Maximum salary.
    @param peak_age        Age at peak.
    @param wind_down_age   Age at which salary begins declining.
    @param wind_down_salary Salary at wind-down start.
    """
    entry_salary: float
    entry_age: int
    mid_salary: float
    mid_age: int
    senior_salary: float
    senior_age: int
    peak_salary: float
    peak_age: int
    wind_down_age: int
    wind_down_salary: float


@dataclass
class CareerPath:
    """
    @brief One career archetype with salary curves for UK and US.

    @param career_id  Unique identifier (e.g. 'software_engineer').
    @param label      Display label.
    @param ceiling    Earnings ceiling category.
    @param uk         UK salary curve.
    @param us         US salary curve.
    """
    career_id: str
    label: str
    ceiling: str
    uk: CareerSalaryCurve
    us: CareerSalaryCurve


@dataclass
class OffspringConfig:
    """
    @brief Configuration for one offspring person.

    @param offspring_id       Unique identifier.
    @param name               Display name.
    @param birth_year         Calendar year of birth.
    @param life_expectancy    Projected age at death.
    @param projection_end_year  Last year to project (may exceed life expectancy).
    @param default_career     Default career path ID.
    @param default_country    'uk' | 'us'.
    @param uk_university_start  Year UK university begins.
    @param uk_duration        UK degree duration in years.
    @param us_university_start  Year US university begins.
    @param us_duration        US degree duration in years.
    @param lisa_enabled       True to model a LISA for UK first home.
    @param lisa_start_year    Year LISA contributions begin.
    """
    offspring_id: str
    name: str
    birth_year: int
    life_expectancy: int
    projection_end_year: int
    default_career: str
    default_country: str
    uk_university_start: int
    uk_duration: int
    us_university_start: int
    us_duration: int
    lisa_enabled: bool
    lisa_start_year: int


@dataclass
class UniversityConfig:
    """
    @brief University cost assumptions for UK and US.

    @param uk_tuition_per_year      Plan 5 tuition per year.
    @param uk_living_per_year       Annual living costs.
    @param uk_parent_contribution   Total parental cash support.
    @param uk_loan_threshold        Income threshold for repayment.
    @param uk_loan_rate             Repayment rate above threshold.
    @param uk_write_off_years       Years until loan written off.
    @param us_tuition_mid           Mid-scenario US tuition per year.
    @param us_living_mid            Mid-scenario US living costs per year.
    @param us_529_balance           529 plan balance at university start.
    """
    uk_tuition_per_year: float = 9250.0
    uk_living_per_year: float = 12000.0
    uk_parent_contribution: float = 20000.0
    uk_loan_threshold: float = 25000.0
    uk_loan_rate: float = 0.09
    uk_write_off_years: int = 40
    us_tuition_mid: float = 28000.0
    us_living_mid: float = 20000.0
    us_529_balance: float = 136000.0


@dataclass
class GenerationalMacro:
    """
    @brief Country-specific macro assumptions for one scenario.

    @param inflation         Annual CPI inflation rate.
    @param equity_real_return  Real equity return (above inflation).
    @param salary_real_growth  Real salary growth rate.
    @param healthcare_annual  Annual healthcare cost (0 for UK NHS).
    @param healthcare_aca_bridge  US ACA bridge cost (ages 62–65).
    @param healthcare_medicare   US Medicare cost (ages 65–79).
    @param healthcare_late_life  US late-life healthcare (ages 80+).
    """
    inflation: float = 0.025
    equity_real_return: float = 0.050
    salary_real_growth: float = 0.010
    healthcare_annual: float = 0.0
    healthcare_aca_bridge: float = 0.0
    healthcare_medicare: float = 0.0
    healthcare_late_life: float = 0.0

    @property
    def nominal_equity_return(self) -> float:
        """@brief Nominal equity return = real return + inflation."""
        return self.equity_real_return + self.inflation


@dataclass
class EstateConfig:
    """
    @brief Estate tax configuration for wealth transfer.

    @param uk_nrb              UK nil-rate band per person.
    @param uk_rnrb             UK residence nil-rate band.
    @param uk_iht_rate         UK IHT rate (0.40).
    @param uk_pension_outside  True = SIPP outside estate.
    @param us_exemption        US federal estate exemption per person.
    @param us_rate             US federal estate tax rate.
    @param us_stepped_up_basis  True = inherited assets get cost-basis step-up.
    """
    uk_nrb: float = 325_000.0
    uk_rnrb: float = 175_000.0
    uk_iht_rate: float = 0.40
    uk_pension_outside: bool = True
    us_exemption: float = 14_000_000.0
    us_rate: float = 0.40
    us_stepped_up_basis: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class OffspringYearSnapshot:
    """
    @brief Offspring financial state in one calendar year.

    @param year           Calendar year.
    @param age            Offspring age.
    @param country        'uk' | 'us'.
    @param career_phase   'pre_career' | 'university' | 'working' | 'retired'.
    @param gross_salary   Gross employment income.
    @param income_tax     Income tax paid.
    @param ni_fica        NI (UK) or FICA (US) paid.
    @param net_income     Take-home pay.
    @param student_loan_repayment  UK Plan 5 repayment (0 if US).
    @param healthcare_cost  Annual healthcare cost (0 for UK NHS).
    @param savings_contributed  Amount added to investment accounts.
    @param isa_value      ISA balance (UK) or Roth IRA balance (US).
    @param pension_value  SIPP (UK) or 401k (US) balance.
    @param taxable_value  GIA (UK) or taxable brokerage (US).
    @param total_net_worth  Combined portfolio value.
    @param fire_achieved  True when portfolio ≥ 4% SWR target.
    @param loan_balance   UK student loan outstanding (0 if US/paid off).
    """
    year: int
    age: int
    country: str
    career_phase: str
    gross_salary: float
    income_tax: float
    ni_fica: float
    net_income: float
    student_loan_repayment: float
    healthcare_cost: float
    savings_contributed: float
    isa_value: float
    pension_value: float
    taxable_value: float
    total_net_worth: float
    fire_achieved: bool
    loan_balance: float


@dataclass
class UniversityCostSummary:
    """
    @brief Total university cost breakdown.

    @param country            'uk' | 'us'.
    @param duration_years     Duration of study.
    @param total_tuition      Total tuition fees paid.
    @param total_living       Total living costs.
    @param parental_outlay    Cash from parents.
    @param loan_taken         Loan taken (UK) or 529 used (US).
    @param loan_balance_at_graduation  UK loan balance at graduation.
    @param projected_loan_repayment_years  Estimated years to repay (UK).
    @param projected_loan_write_off  True if loan likely written off.
    """
    country: str
    duration_years: int
    total_tuition: float
    total_living: float
    parental_outlay: float
    loan_taken: float
    loan_balance_at_graduation: float
    projected_loan_repayment_years: float
    projected_loan_write_off: bool


@dataclass
class OffspringProjection:
    """
    @brief Complete offspring financial projection.

    @param offspring_id       Offspring identifier.
    @param name               Display name.
    @param career_path        Career path used.
    @param country            'uk' | 'us'.
    @param years              Year-by-year snapshots.
    @param fire_year          Calendar year FIRE is achieved (None if not).
    @param fire_age           Age at FIRE.
    @param peak_net_worth     Maximum net worth reached.
    @param peak_net_worth_year  Year of peak net worth.
    @param university_cost    University cost breakdown.
    @param lifetime_tax       Total income tax paid over working life.
    @param lifetime_earnings  Total gross earnings over working life.
    """
    offspring_id: str
    name: str
    career_path: str
    country: str
    years: list[OffspringYearSnapshot]
    fire_year: Optional[int]
    fire_age: Optional[int]
    peak_net_worth: float
    peak_net_worth_year: int
    university_cost: UniversityCostSummary
    lifetime_tax: float
    lifetime_earnings: float

    def year(self, yr: int) -> Optional[OffspringYearSnapshot]:
        """@brief Return snapshot for a specific year or None."""
        for s in self.years:
            if s.year == yr:
                return s
        return None


@dataclass
class WealthTransfer:
    """
    @brief Estate handed from parents to offspring.

    @param transfer_year          Calendar year of transfer (assumed: death year).
    @param gross_estate_gbp       Gross estate value in GBP.
    @param gross_estate_usd       Gross estate value in USD.
    @param pension_outside_gbp    SIPP excluded from UK IHT estate.
    @param iht_liability_gbp      UK IHT payable.
    @param us_estate_tax_usd      US federal estate tax payable.
    @param net_to_offspring_gbp   Net estate received in GBP.
    @param net_to_offspring_usd   Net estate received in USD.
    @param fx_rate                GBP/USD rate used.
    @param notes                  Explanation of key assumptions.
    """
    transfer_year: int
    gross_estate_gbp: float
    gross_estate_usd: float
    pension_outside_gbp: float
    iht_liability_gbp: float
    us_estate_tax_usd: float
    net_to_offspring_gbp: float
    net_to_offspring_usd: float
    fx_rate: float
    notes: str = ""


@dataclass
class GenerationalResult:
    """
    @brief Combined generational planning output.

    @param country            'uk' | 'us' (parent path modelled).
    @param macro_scenario     'low' | 'mid' | 'high'.
    @param parent_wealth_by_year   Dict year → parent total net worth.
    @param offspring_projections   List of OffspringProjection (one per offspring).
    @param wealth_transfer        WealthTransfer at estimated death year.
    @param combined_family_wealth  Dict year → parents_nw + offspring_nw (common currency).
    @param fire_years             Dict person_id → FIRE year.
    @param investment_tax_drag    Total lifetime investment tax drag (US only, est.).
    @param warnings               Warning strings.
    """
    country: str
    macro_scenario: str
    parent_wealth_by_year: dict[int, float]
    offspring_projections: list[OffspringProjection]
    wealth_transfer: WealthTransfer
    combined_family_wealth: dict[int, float]
    fire_years: dict[str, Optional[int]]
    investment_tax_drag: float
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Salary interpolation
# ─────────────────────────────────────────────────────────────────────────────


def salary_at_age(curve: CareerSalaryCurve, age: int) -> float:
    """
    @brief Interpolate salary at a given age from a CareerSalaryCurve.

    Uses piecewise linear interpolation across four milestone breakpoints:
    entry → mid → senior → peak → wind_down.

    @param curve  CareerSalaryCurve with milestone ages and salaries.
    @param age    Person's age to evaluate.
    @return       Interpolated gross salary.  Returns 0.0 before entry_age.
    """
    if age < curve.entry_age:
        return 0.0

    segments = [
        (curve.entry_age, curve.entry_salary, curve.mid_age, curve.mid_salary),
        (curve.mid_age,   curve.mid_salary,   curve.senior_age, curve.senior_salary),
        (curve.senior_age, curve.senior_salary, curve.peak_age, curve.peak_salary),
        (curve.peak_age,  curve.peak_salary,   curve.wind_down_age, curve.wind_down_salary),
    ]

    for (a0, s0, a1, s1) in segments:
        if a0 <= age <= a1:
            if a1 == a0:
                return s0
            t = (age - a0) / (a1 - a0)
            return s0 + t * (s1 - s0)

    # After wind-down age: maintain wind-down salary
    return curve.wind_down_salary


# ─────────────────────────────────────────────────────────────────────────────
# UK student loan repayment (Plan 5)
# ─────────────────────────────────────────────────────────────────────────────


def uk_plan5_repayment(gross_salary: float, loan_balance: float,
                       threshold: float, rate: float,
                       loan_interest_rate: float = 0.045) -> tuple[float, float]:
    """
    @brief Compute annual UK Plan 5 student loan repayment and new balance.

    Repayment = 9% of gross income above the £25k threshold.
    Interest accrues on the outstanding balance at RPI + 1.5% (~4.5%).
    Returns (annual_repayment, new_balance).

    @param gross_salary       Annual gross income.
    @param loan_balance       Outstanding loan balance.
    @param threshold          Income threshold (£25,000 for Plan 5).
    @param rate               Repayment rate (0.09).
    @param loan_interest_rate Annual interest rate on the loan.
    @return                   Tuple (repayment, balance_after).
    """
    if loan_balance <= 0:
        return 0.0, 0.0

    interest = loan_balance * loan_interest_rate
    repayment = max(0.0, (gross_salary - threshold)) * rate
    repayment = min(repayment, loan_balance + interest)
    new_balance = max(0.0, loan_balance + interest - repayment)
    return round(repayment, 2), round(new_balance, 2)


# ─────────────────────────────────────────────────────────────────────────────
# US federal income tax (simplified)
# ─────────────────────────────────────────────────────────────────────────────

# 2024 federal brackets (single filer), not inflation-adjusted
_US_FEDERAL_BRACKETS_SINGLE = [
    (11600,   0.10),
    (47150,   0.12),
    (100525,  0.22),
    (191950,  0.24),
    (243725,  0.32),
    (609350,  0.35),
    (float('inf'), 0.37),
]
_US_STANDARD_DEDUCTION_SINGLE = 14600.0
_US_FICA_RATE        = 0.0765   # employee share (7.65%)
_US_FICA_WAGE_BASE   = 168600.0  # 2024
_US_MEDICARE_SURTAX_THRESHOLD = 200000.0
_US_MEDICARE_SURTAX  = 0.009


def calculate_us_tax(gross: float, pretax_401k: float = 0.0,
                     state_rate: float = 0.0) -> tuple[float, float, float]:
    """
    @brief Simplified US federal + state income tax + FICA.

    Applies the 2024 single-filer federal brackets with standard deduction,
    FICA (7.65% up to wage base), Medicare surtax, and a flat state rate.
    Does not model joint-filing or all deductions — use for planning estimates.

    @param gross         Annual gross employment income (USD).
    @param pretax_401k   Pre-tax 401k contribution (reduces federal taxable income).
    @param state_rate    Flat state income tax rate (0.0 for WA, ~0.093 for CA).
    @return              Tuple (federal_tax, fica, state_tax).
    """
    # Federal taxable income
    taxable = max(0.0, gross - pretax_401k - _US_STANDARD_DEDUCTION_SINGLE)

    # Federal income tax (bracket calculation)
    federal = 0.0
    prev_limit = 0.0
    for (limit, rate) in _US_FEDERAL_BRACKETS_SINGLE:
        if taxable <= prev_limit:
            break
        bracket_income = min(taxable, limit) - prev_limit
        federal += bracket_income * rate
        prev_limit = limit

    # Medicare surtax on earned income > $200k
    if gross > _US_MEDICARE_SURTAX_THRESHOLD:
        federal += (gross - _US_MEDICARE_SURTAX_THRESHOLD) * _US_MEDICARE_SURTAX

    # FICA
    fica_base = min(gross, _US_FICA_WAGE_BASE)
    fica = fica_base * _US_FICA_RATE

    # State tax (flat for simplicity)
    state = max(0.0, gross - pretax_401k) * state_rate

    return round(federal, 2), round(fica, 2), round(state, 2)


# ─────────────────────────────────────────────────────────────────────────────
# UK tax (wrapper over tax_engine)
# ─────────────────────────────────────────────────────────────────────────────


def calculate_uk_tax(gross: float,
                     pension_contribution_rate: float = 0.05) -> tuple[float, float]:
    """
    @brief UK PAYE income tax and NI for a given gross salary.

    Uses simplified 2024/25 bands. Returns (income_tax, national_insurance).

    @param gross                    Annual gross employment income (GBP).
    @param pension_contribution_rate  Employee pension contribution as fraction
                                      (reduces adjusted income, not direct tax
                                       relief here — kept simple for offspring model).
    @return                         Tuple (income_tax, national_insurance).
    """
    # Personal allowance (tapers £1:£2 above £100k)
    pa = 12570.0
    if gross > 100000:
        pa = max(0.0, pa - (gross - 100000) / 2)

    taxable = max(0.0, gross - pa)

    # Income tax bands 2024/25
    tax = 0.0
    basic_limit = 50270 - 12570   # £37,700
    higher_limit = 125140 - 12570  # £112,570
    if taxable <= basic_limit:
        tax = taxable * 0.20
    elif taxable <= higher_limit:
        tax = basic_limit * 0.20 + (taxable - basic_limit) * 0.40
    else:
        tax = basic_limit * 0.20 + (higher_limit - basic_limit) * 0.40 + (taxable - higher_limit) * 0.45

    # National Insurance (Class 1 employee, 2024/25)
    # 8% on £12,570–£50,270, 2% above £50,270
    ni = 0.0
    ni_lower = 12570.0
    ni_upper = 50270.0
    if gross > ni_lower:
        band1 = min(gross, ni_upper) - ni_lower
        ni += band1 * 0.08
        if gross > ni_upper:
            ni += (gross - ni_upper) * 0.02

    return round(tax, 2), round(ni, 2)


# ─────────────────────────────────────────────────────────────────────────────
# University cost calculation
# ─────────────────────────────────────────────────────────────────────────────


def calculate_uk_university_cost(cfg: UniversityConfig,
                                  duration: int) -> UniversityCostSummary:
    """
    @brief Calculate UK Plan 5 university cost and loan position at graduation.

    @param cfg       UniversityConfig.
    @param duration  Degree duration in years.
    @return          UniversityCostSummary.
    """
    total_tuition = cfg.uk_tuition_per_year * duration
    total_living  = cfg.uk_living_per_year * duration
    parental_out  = cfg.uk_parent_contribution

    # Loan taken = tuition + living - parental contribution (can't be negative)
    loan_taken = max(0.0, total_tuition + total_living - parental_out)

    # Loan accrues interest at 4.5% during study; balance at graduation
    # Simple compound over duration years
    balance_at_graduation = loan_taken * (1 + 0.045) ** duration

    # Rough repayment horizon: assume grad starts at entry salary, grows 1%/yr real
    # Repayment = 9% of (salary - £25k). At £45k entry: 9% × £20k = £1,800/yr
    # While loan accrues at 4.5%: balance grows ~£balance×4.5%/yr minus repayment
    # Estimate years to repay using simple loop
    balance = balance_at_graduation
    avg_repayment = 2500.0  # rough annual repayment at moderate salary
    years_to_repay = 40.0
    for yr in range(1, 41):
        balance = balance * 1.045 - avg_repayment * (1 + 0.01) ** yr
        if balance <= 0:
            years_to_repay = float(yr)
            break

    write_off = years_to_repay >= 40.0

    return UniversityCostSummary(
        country="uk",
        duration_years=duration,
        total_tuition=round(total_tuition, 2),
        total_living=round(total_living, 2),
        parental_outlay=round(parental_out, 2),
        loan_taken=round(loan_taken, 2),
        loan_balance_at_graduation=round(balance_at_graduation, 2),
        projected_loan_repayment_years=round(years_to_repay, 1),
        projected_loan_write_off=write_off,
    )


def calculate_us_university_cost(cfg: UniversityConfig,
                                  duration: int) -> UniversityCostSummary:
    """
    @brief Calculate US university cost funded by 529 plan.

    @param cfg       UniversityConfig.
    @param duration  Degree duration in years.
    @return          UniversityCostSummary.
    """
    total_tuition = cfg.us_tuition_mid * duration
    total_living  = cfg.us_living_mid * duration
    total_cost    = total_tuition + total_living

    # 529 covers up to its balance
    loan_from_529 = min(cfg.us_529_balance, total_cost)
    parental_out  = max(0.0, total_cost - loan_from_529)

    return UniversityCostSummary(
        country="us",
        duration_years=duration,
        total_tuition=round(total_tuition, 2),
        total_living=round(total_living, 2),
        parental_outlay=round(parental_out, 2),
        loan_taken=round(loan_from_529, 2),
        loan_balance_at_graduation=0.0,  # 529 is not a loan
        projected_loan_repayment_years=0.0,
        projected_loan_write_off=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Offspring projection engine
# ─────────────────────────────────────────────────────────────────────────────


class OffspringProjectionEngine:
    """
    @brief Projects one offspring person's financial trajectory.

    Runs a year-by-year simulation from birth to projection_end_year,
    covering pre-career, university, working, and retirement phases.
    """

    # FIRE target: expenses × 25 (4% SWR)
    _FIRE_EXPENSES_UK = 40_000.0   # £/yr target
    _FIRE_EXPENSES_US = 70_000.0   # $/yr target
    _FIRE_MULTIPLE    = 25.0

    def __init__(self, career_paths: dict[str, CareerPath],
                 university_cfg: UniversityConfig) -> None:
        """
        @brief Initialise the offspring projection engine.

        @param career_paths    Dict of career_id → CareerPath.
        @param university_cfg  UniversityConfig for cost calculations.
        """
        self._careers = career_paths
        self._uni_cfg = university_cfg
        logger.info("OffspringProjectionEngine initialised (%d career paths)", len(career_paths))

    def project(
        self,
        offspring: OffspringConfig,
        macro: GenerationalMacro,
        career_path_id: Optional[str] = None,
        country: Optional[str] = None,
        extra_capital: float = 0.0,  # inheritance windfall injected at start_year
        extra_capital_year: Optional[int] = None,
        state_tax_rate: float = 0.0,  # US state income tax rate
    ) -> OffspringProjection:
        """
        @brief Run the full offspring projection.

        @param offspring           OffspringConfig.
        @param macro               Country-specific macro assumptions.
        @param career_path_id      Override career path (default: offspring.default_career).
        @param country             Override country 'uk' | 'us'.
        @param extra_capital       Lump-sum capital injection (inheritance).
        @param extra_capital_year  Year the injection occurs.
        @param state_tax_rate      US state income tax rate (0.0 for WA).
        @return                    OffspringProjection.
        """
        career_id = career_path_id or offspring.default_career
        ctry = country or offspring.default_country

        if career_id not in self._careers:
            raise ValueError(f"Unknown career path: '{career_id}'")

        career    = self._careers[career_id]
        curve     = career.uk if ctry == "uk" else career.us
        uni_start = offspring.uk_university_start if ctry == "uk" else offspring.us_university_start
        uni_dur   = offspring.uk_duration if ctry == "uk" else offspring.us_duration

        # University cost summary
        uni_cost = (calculate_uk_university_cost(self._uni_cfg, uni_dur)
                    if ctry == "uk"
                    else calculate_us_university_cost(self._uni_cfg, uni_dur))

        # UK student loan balance at graduation
        loan_balance = (uni_cost.loan_balance_at_graduation if ctry == "uk" else 0.0)

        # LISA starting balance (UK)
        lisa_value = 0.0

        # Account balances
        isa_or_roth  = 0.0
        pension_401k = 0.0
        taxable      = 0.0

        # Growth rates
        growth_isa    = 0.07
        growth_pen    = 0.07
        growth_taxabl = 0.065

        # FIRE target
        fire_target = (self._FIRE_EXPENSES_UK * self._FIRE_MULTIPLE if ctry == "uk"
                       else self._FIRE_EXPENSES_US * self._FIRE_MULTIPLE)

        fire_year: Optional[int] = None
        fire_age:  Optional[int] = None

        snapshots: list[OffspringYearSnapshot] = []
        lifetime_tax = 0.0
        lifetime_earnings = 0.0
        peak_nw = 0.0
        peak_nw_year = offspring.birth_year

        for yr in range(offspring.birth_year, offspring.projection_end_year + 1):
            age = yr - offspring.birth_year

            # Inject inheritance capital
            if extra_capital_year and yr == extra_capital_year:
                if ctry == "uk":
                    isa_or_roth = min(isa_or_roth + extra_capital, isa_or_roth + extra_capital)
                    taxable += max(0.0, extra_capital - 20_000)  # ISA limit cap
                    isa_or_roth += min(extra_capital, 20_000)
                else:
                    taxable += extra_capital

            # Determine career phase
            if age < curve.entry_age:
                if uni_start <= yr < uni_start + uni_dur:
                    phase = "university"
                else:
                    phase = "pre_career"
            elif age > offspring.life_expectancy:
                phase = "deceased"
            elif pension_401k + isa_or_roth + taxable >= fire_target and age >= curve.entry_age + 5:
                phase = "retired"
            else:
                phase = "working"

            gross = 0.0
            income_tax = 0.0
            ni_fica = 0.0
            net_income = 0.0
            loan_repayment = 0.0
            healthcare = 0.0
            savings = 0.0

            if phase == "working":
                # Salary with real growth applied each year above base curve
                base_salary = salary_at_age(curve, age)
                years_working = max(0, age - curve.entry_age)
                gross = base_salary * (1 + macro.salary_real_growth + macro.inflation) ** years_working
                gross = min(gross, base_salary * 3)  # cap growth at 3× base for realism

                lifetime_earnings += gross

                if ctry == "uk":
                    income_tax, ni_fica = calculate_uk_tax(gross, pension_contribution_rate=0.05)
                    net_income = gross - income_tax - ni_fica
                    # UK student loan repayment
                    if loan_balance > 0 and yr < uni_start + uni_dur + self._uni_cfg.uk_write_off_years:
                        loan_repayment, loan_balance = uk_plan5_repayment(
                            gross, loan_balance,
                            self._uni_cfg.uk_loan_threshold,
                            self._uni_cfg.uk_loan_rate,
                        )
                    else:
                        loan_balance = 0.0
                    # ISA + SIPP contributions: 20% of net income
                    savings = max(0.0, net_income - loan_repayment) * 0.20
                    isa_contrib  = min(savings * 0.5, 20_000)   # ISA limit
                    sipp_contrib = savings * 0.5
                    isa_or_roth  = (isa_or_roth  + isa_contrib)  * (1 + growth_isa)
                    pension_401k = (pension_401k + sipp_contrib) * (1 + growth_pen)

                else:  # US
                    # 401k contribution
                    k401 = min(gross * 0.10, 23_500)
                    income_tax, ni_fica, st = calculate_us_tax(gross, pretax_401k=k401,
                                                                state_rate=state_tax_rate)
                    net_income = gross - income_tax - ni_fica - k401 - st
                    # Healthcare cost (employer plan assumed)
                    healthcare = macro.healthcare_annual
                    savings = max(0.0, net_income - healthcare) * 0.15
                    roth_contrib   = min(savings * 0.3, 7_000)
                    taxable_contrib = savings - roth_contrib
                    isa_or_roth  = (isa_or_roth  + roth_contrib)   * (1 + growth_isa)
                    pension_401k = (pension_401k + k401)            * (1 + growth_pen)
                    taxable      = (taxable      + taxable_contrib) * (1 + growth_taxabl)

                lifetime_tax += income_tax

            elif phase == "university":
                # Minimal part-time income during university
                gross = 8_000.0 if ctry == "uk" else 15_000.0

            elif phase == "retired":
                # Drawdown: grow accounts at lower rate
                isa_or_roth  = isa_or_roth  * (1 + growth_isa  * 0.7)
                pension_401k = pension_401k * (1 + growth_pen  * 0.7)
                taxable      = taxable      * (1 + growth_taxabl * 0.7)
                if ctry == "us":
                    # Healthcare in US retirement
                    if 62 <= age <= 64:
                        healthcare = macro.healthcare_aca_bridge
                    elif 65 <= age <= 79:
                        healthcare = macro.healthcare_medicare
                    elif age >= 80:
                        healthcare = macro.healthcare_late_life

            else:  # pre_career or deceased
                isa_or_roth  = isa_or_roth  * (1 + growth_isa)
                pension_401k = pension_401k * (1 + growth_pen)
                taxable      = taxable      * (1 + growth_taxabl)

            # LISA growth (UK only)
            if ctry == "uk" and offspring.lisa_enabled and yr >= offspring.lisa_start_year:
                annual_lisa = 4_000 + 1_000  # contribution + 25% govt bonus
                lisa_value = (lisa_value + (annual_lisa if phase == "working" else 0)) * 1.05

            total_nw = isa_or_roth + pension_401k + taxable + lisa_value

            if total_nw > peak_nw:
                peak_nw = total_nw
                peak_nw_year = yr

            # FIRE detection
            if fire_year is None and total_nw >= fire_target and phase == "working":
                fire_year = yr
                fire_age  = age
                logger.debug("Offspring %s FIRE in %d (age %d) nw=%.0f",
                             offspring.name, yr, age, total_nw)

            snapshots.append(OffspringYearSnapshot(
                year=yr, age=age, country=ctry, career_phase=phase,
                gross_salary=round(gross, 2),
                income_tax=round(income_tax, 2),
                ni_fica=round(ni_fica, 2),
                net_income=round(net_income, 2),
                student_loan_repayment=round(loan_repayment, 2),
                healthcare_cost=round(healthcare, 2),
                savings_contributed=round(savings, 2),
                isa_value=round(isa_or_roth, 2),
                pension_value=round(pension_401k, 2),
                taxable_value=round(taxable, 2),
                total_net_worth=round(total_nw, 2),
                fire_achieved=(fire_year is not None),
                loan_balance=round(loan_balance, 2),
            ))

        logger.info(
            "OffspringProjection %s (%s/%s): FIRE=%s peak_nw=%.0f lifetime_tax=%.0f",
            offspring.name, career_id, ctry,
            str(fire_year), peak_nw, lifetime_tax,
        )

        return OffspringProjection(
            offspring_id=offspring.offspring_id,
            name=offspring.name,
            career_path=career_id,
            country=ctry,
            years=snapshots,
            fire_year=fire_year,
            fire_age=fire_age,
            peak_net_worth=round(peak_nw, 2),
            peak_net_worth_year=peak_nw_year,
            university_cost=uni_cost,
            lifetime_tax=round(lifetime_tax, 2),
            lifetime_earnings=round(lifetime_earnings, 2),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Estate / wealth transfer calculation
# ─────────────────────────────────────────────────────────────────────────────


def calculate_wealth_transfer(
    parent_wealth_gbp: float,
    pension_value_gbp: float,
    property_value_gbp: float,
    mortgage_balance_gbp: float,
    death_year: int,
    estate_cfg: EstateConfig,
    fx_rate: float = 1.27,
    has_surviving_partner: bool = False,
) -> WealthTransfer:
    """
    @brief Compute net estate transfer to offspring under UK IHT and US estate tax.

    @param parent_wealth_gbp    Total portfolio value (GBP), excluding pension if outside estate.
    @param pension_value_gbp    SIPP value (excluded from estate if estate_cfg.uk_pension_outside).
    @param property_value_gbp   Property value (net of mortgage counted separately).
    @param mortgage_balance_gbp Outstanding mortgage (liability reduces estate).
    @param death_year           Calendar year of death.
    @param estate_cfg           EstateConfig with UK and US parameters.
    @param fx_rate              GBP/USD conversion rate.
    @param has_surviving_partner  True = NRB + RNRB transferred from deceased.
    @return                     WealthTransfer.
    """
    pension_outside = pension_value_gbp if estate_cfg.uk_pension_outside else 0.0
    net_property    = max(0.0, property_value_gbp - mortgage_balance_gbp)
    gross_estate    = parent_wealth_gbp + net_property - pension_outside

    # UK NRB / RNRB
    nrb  = estate_cfg.uk_nrb  * (2 if has_surviving_partner else 1)
    rnrb = estate_cfg.uk_rnrb * (2 if has_surviving_partner else 1)

    # RNRB tapers above £2M
    rnrb_taper_start = 2_000_000.0
    if gross_estate > rnrb_taper_start:
        taper = min(rnrb, (gross_estate - rnrb_taper_start) / 2)
        rnrb  = max(0.0, rnrb - taper)

    allowances    = nrb + rnrb
    taxable_uk    = max(0.0, gross_estate - allowances)
    iht           = round(taxable_uk * estate_cfg.uk_iht_rate, 2)
    net_to_off_gbp = round(gross_estate - iht, 2)

    # US estate tax (if the assets are held in US)
    gross_usd     = gross_estate * fx_rate
    taxable_us    = max(0.0, gross_usd - estate_cfg.us_exemption)
    us_estate_tax = round(taxable_us * estate_cfg.us_rate, 2)
    net_to_off_usd = round(gross_usd - us_estate_tax, 2)

    notes = (
        f"Estate valued at £{gross_estate:,.0f}. "
        f"Pension excluded: £{pension_outside:,.0f}. "
        f"Allowances: £{allowances:,.0f} (NRB+RNRB). "
        f"IHT @40%: £{iht:,.0f}. "
        f"Net to offspring (UK path): £{net_to_off_gbp:,.0f}. "
        f"US path (gross ${gross_usd:,.0f}, estate tax ${us_estate_tax:,.0f}): "
        f"${net_to_off_usd:,.0f}."
    )

    logger.info(
        "WealthTransfer %d: gross=£%.0f iht=£%.0f net=£%.0f / $%.0f",
        death_year, gross_estate, iht, net_to_off_gbp, net_to_off_usd,
    )

    return WealthTransfer(
        transfer_year=death_year,
        gross_estate_gbp=round(gross_estate, 2),
        gross_estate_usd=round(gross_usd, 2),
        pension_outside_gbp=round(pension_outside, 2),
        iht_liability_gbp=iht,
        us_estate_tax_usd=us_estate_tax,
        net_to_offspring_gbp=net_to_off_gbp,
        net_to_offspring_usd=net_to_off_usd,
        fx_rate=fx_rate,
        notes=notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Master generational engine
# ─────────────────────────────────────────────────────────────────────────────


class GenerationalEngine:
    """
    @brief Phase 7 master generational planning engine.

    Orchestrates the offspring projection, wealth transfer calculation, and
    combined family wealth timeline for a given country path and macro scenario.

    Usage::

        config = load_generational_config("config/generational/generational_config.yaml")
        engine = GenerationalEngine(config)
        result = engine.run(country="uk", macro_scenario="mid")
    """

    def __init__(self, config: dict) -> None:
        """
        @brief Initialise the generational engine from a loaded config dict.

        @param config  Dict loaded from generational_config.yaml.
        """
        self._cfg = config
        self._career_paths = self._load_career_paths()
        self._uni_cfg      = self._load_university_config()
        self._offspring    = self._load_offspring_config()
        self._estate_cfg   = self._load_estate_config()
        self._offspring_engine = OffspringProjectionEngine(self._career_paths, self._uni_cfg)
        logger.info(
            "GenerationalEngine: %d offspring, %d career paths",
            len(self._offspring), len(self._career_paths),
        )

    def run(
        self,
        country: str = "uk",
        macro_scenario: str = "mid",
        parent_wealth_gbp: float = 0.0,
        parent_pension_gbp: float = 0.0,
        parent_property_gbp: float = 0.0,
        parent_mortgage_gbp: float = 0.0,
        parent_death_year: int = 2070,
        parent_wealth_by_year: Optional[dict[int, float]] = None,
        fx_scenario: str = "mid",
    ) -> GenerationalResult:
        """
        @brief Run the full generational analysis.

        @param country               'uk' | 'us'.
        @param macro_scenario        'low' | 'mid' | 'high'.
        @param parent_wealth_gbp     Parent total wealth at projection start.
        @param parent_pension_gbp    Parent pension value (may be outside estate).
        @param parent_property_gbp   Parent property value.
        @param parent_mortgage_gbp   Parent mortgage balance.
        @param parent_death_year     Assumed year of last parent death (estate transfer).
        @param parent_wealth_by_year Pre-computed parent wealth by year (if available).
        @param fx_scenario           'low' | 'mid' | 'high' (GBP/USD rate).
        @return                      GenerationalResult.
        """
        warnings: list[str] = []

        macro = self._get_macro(country, macro_scenario)
        fx    = self._get_fx(fx_scenario)

        # Wealth transfer from parents to offspring
        transfer = calculate_wealth_transfer(
            parent_wealth_gbp=parent_wealth_gbp,
            pension_value_gbp=parent_pension_gbp,
            property_value_gbp=parent_property_gbp,
            mortgage_balance_gbp=parent_mortgage_gbp,
            death_year=parent_death_year,
            estate_cfg=self._estate_cfg,
            fx_rate=fx,
            has_surviving_partner=False,  # last surviving parent
        )

        # Net inheritance per offspring (divide equally)
        n_offspring = max(1, len(self._offspring))
        inheritance_per_offspring = (
            transfer.net_to_offspring_gbp / n_offspring if country == "uk"
            else transfer.net_to_offspring_usd / n_offspring
        )

        # Project each offspring
        projections: list[OffspringProjection] = []
        state_tax = 0.0  # WA state for US phase

        for offspring_cfg in self._offspring:
            proj = self._offspring_engine.project(
                offspring=offspring_cfg,
                macro=macro,
                country=country,
                extra_capital=inheritance_per_offspring,
                extra_capital_year=parent_death_year,
                state_tax_rate=state_tax,
            )
            projections.append(proj)

        # Build combined family wealth dict
        pb_year = parent_wealth_by_year or {}
        combined: dict[int, float] = {}
        all_years = set(pb_year.keys())
        for proj in projections:
            all_years.update(s.year for s in proj.years)

        for yr in sorted(all_years):
            parent_nw = pb_year.get(yr, 0.0)
            offspring_nw = sum(
                (s.total_net_worth for p in projections for s in p.years if s.year == yr),
                0.0,
            )
            # Convert to common currency (GBP for UK path, USD for US path)
            if country == "uk":
                combined[yr] = round(parent_nw + offspring_nw, 2)
            else:
                combined[yr] = round(parent_nw + offspring_nw, 2)

        fire_years = {p.offspring_id: p.fire_year for p in projections}

        # Investment tax drag estimate (US only — UK ISA/SIPP largely tax-free)
        tax_drag = 0.0
        if country == "us":
            for proj in projections:
                tax_drag += proj.lifetime_tax * 0.5  # rough: half lifetime tax from investment income

        if not projections:
            warnings.append("No offspring configured — generational projection incomplete.")

        return GenerationalResult(
            country=country,
            macro_scenario=macro_scenario,
            parent_wealth_by_year=pb_year,
            offspring_projections=projections,
            wealth_transfer=transfer,
            combined_family_wealth=combined,
            fire_years=fire_years,
            investment_tax_drag=round(tax_drag, 2),
            warnings=warnings,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _get_macro(self, country: str, scenario: str) -> GenerationalMacro:
        """
        @brief Load GenerationalMacro from config for a country + scenario.

        @param country   'uk' | 'us'.
        @param scenario  'low' | 'mid' | 'high'.
        @return          GenerationalMacro.
        """
        country_key = country.upper()
        raw = (self._cfg.get("generational", {})
               .get("country_macro", {})
               .get(country_key, {})
               .get(scenario, {}))

        return GenerationalMacro(
            inflation=float(raw.get("inflation", 0.025)),
            equity_real_return=float(raw.get("equity_real_return", 0.05)),
            salary_real_growth=float(raw.get("salary_real_growth", 0.01)),
            healthcare_annual=float(raw.get("healthcare_working", raw.get("annual_healthcare_cost", 0))),
            healthcare_aca_bridge=float(raw.get("healthcare_aca_bridge", 0)),
            healthcare_medicare=float(raw.get("healthcare_medicare", 0)),
            healthcare_late_life=float(raw.get("healthcare_late_life", 0)),
        )

    def _get_fx(self, scenario: str) -> float:
        """
        @brief Get GBP/USD FX rate for a given scenario.

        @param scenario  'low' | 'mid' | 'high'.
        @return          Float FX rate.
        """
        fx_raw = (self._cfg.get("generational", {})
                  .get("fx", {})
                  .get("scenarios", {}))
        return float(fx_raw.get(scenario, 1.27))

    def _load_career_paths(self) -> dict[str, CareerPath]:
        """
        @brief Parse career paths from config dict.

        @return  Dict of career_id → CareerPath.
        """
        paths: dict[str, CareerPath] = {}
        raw_paths = (self._cfg.get("generational", {})
                     .get("career_paths", []))

        for raw in raw_paths:
            def curve(d: dict) -> CareerSalaryCurve:
                return CareerSalaryCurve(
                    entry_salary=float(d.get("entry_salary", 0)),
                    entry_age=int(d.get("entry_age", 22)),
                    mid_salary=float(d.get("mid_salary", 0)),
                    mid_age=int(d.get("mid_age", 30)),
                    senior_salary=float(d.get("senior_salary", 0)),
                    senior_age=int(d.get("senior_age", 38)),
                    peak_salary=float(d.get("peak_salary", 0)),
                    peak_age=int(d.get("peak_age", 46)),
                    wind_down_age=int(d.get("wind_down_age", 58)),
                    wind_down_salary=float(d.get("wind_down_salary", 0)),
                )
            cid = str(raw.get("id", ""))
            if not cid:
                continue
            paths[cid] = CareerPath(
                career_id=cid,
                label=str(raw.get("label", cid)),
                ceiling=str(raw.get("ceiling", "mid")),
                uk=curve(raw.get("uk", {})),
                us=curve(raw.get("us", {})),
            )
        logger.debug("Loaded %d career paths from config", len(paths))
        return paths

    def _load_university_config(self) -> UniversityConfig:
        """
        @brief Parse UniversityConfig from the config dict.

        @return  UniversityConfig.
        """
        u = (self._cfg.get("generational", {})
             .get("university", {}))
        uk  = u.get("uk", {})
        us  = u.get("us", {})
        p529 = u.get("plan_529", {})
        return UniversityConfig(
            uk_tuition_per_year=float(uk.get("tuition_per_year", 9250)),
            uk_living_per_year=float(uk.get("living_costs_per_year", 12000)),
            uk_parent_contribution=float(uk.get("parent_contribution_total", 20000)),
            uk_loan_threshold=float(uk.get("loan_repayment_threshold", 25000)),
            uk_loan_rate=float(uk.get("loan_repayment_rate", 0.09)),
            uk_write_off_years=int(uk.get("loan_write_off_years", 40)),
            us_tuition_mid=float(us.get("mid", {}).get("tuition_per_year", 28000)),
            us_living_mid=float(us.get("mid", {}).get("living_per_year", 20000)),
            us_529_balance=float(p529.get("current_balance", 136000)),
        )

    def _load_offspring_config(self) -> list[OffspringConfig]:
        """
        @brief Parse offspring configs from the config dict.

        @return  List of OffspringConfig.
        """
        configs: list[OffspringConfig] = []
        raw_list = (self._cfg.get("generational", {})
                    .get("offspring", []))
        for raw in raw_list:
            uni = raw.get("university", {})
            lisa = raw.get("lisa", {})
            configs.append(OffspringConfig(
                offspring_id=str(raw.get("id", "")),
                name=str(raw.get("name", "Offspring")),
                birth_year=int(raw.get("birth_year", 2000)),
                life_expectancy=int(raw.get("life_expectancy", 90)),
                projection_end_year=int(raw.get("projection_end_year", 2100)),
                default_career=str(raw.get("default_career_path", "software_engineer")),
                default_country=str(raw.get("default_country", "uk")),
                uk_university_start=int(uni.get("uk_start_year", 2035)),
                uk_duration=int(uni.get("uk_duration_years", 3)),
                us_university_start=int(uni.get("us_start_year", 2035)),
                us_duration=int(uni.get("us_duration_years", 4)),
                lisa_enabled=bool(lisa.get("enabled", True)),
                lisa_start_year=int(lisa.get("start_year", 2035)),
            ))
        return configs

    def _load_estate_config(self) -> EstateConfig:
        """
        @brief Parse EstateConfig from the config dict.

        @return  EstateConfig.
        """
        e = (self._cfg.get("generational", {})
             .get("estate", {}))
        uk = e.get("uk", {})
        us = e.get("us", {})
        return EstateConfig(
            uk_nrb=float(uk.get("nil_rate_band", 325000)),
            uk_rnrb=float(uk.get("residence_nil_rate_band", 175000)),
            uk_iht_rate=float(uk.get("iht_rate", 0.40)),
            uk_pension_outside=bool(uk.get("pension_outside_estate", True)),
            us_exemption=float(us.get("federal_exemption", 14_000_000)),
            us_rate=float(us.get("estate_tax_rate", 0.40)),
            us_stepped_up_basis=bool(us.get("stepped_up_basis", True)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# YAML loader
# ─────────────────────────────────────────────────────────────────────────────


def load_generational_config(path: str) -> dict:
    """
    @brief Load the generational config YAML and return the raw dict.

    @param path  Path to generational_config.yaml.
    @return      Dict with top-level key 'generational'.
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file is not valid YAML.
    """
    logger.info("Loading generational config from: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Generational config not found: %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise
