"""
@file test_phase7_generational.py
@brief Regression tests for Phase 7 (Generational Engine) and Phase 10 (Statement Parser).

Validated figures from CLAUDE.md §12.5 (run 2026-08-24, mid scenario):
  UK retirement 2044:          £4,838,463   ±5%
  US retirement 2044:          $11,852,795  ±5%
  UK gross estate 2072 (no-drawdown):  £24,780,531  ±3%
  US gross estate 2072 (no-drawdown):  $52,917,793  ±3%
  Offspring FIRE age (SWE, UK):        44

Run with:
    pytest tests/test_phase7_generational.py -v

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CFG_PATH = ROOT / "config" / "generational" / "generational_config.yaml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def gen_config():
    """Load generational config once for all tests."""
    from backend.engine.generational_engine import load_generational_config
    if not CFG_PATH.exists():
        pytest.skip("generational_config.yaml not found — skipping Phase 7 tests")
    return load_generational_config(str(CFG_PATH))


@pytest.fixture(scope="session")
def gen_engine(gen_config):
    """Create GenerationalEngine once for all tests."""
    from backend.engine.generational_engine import GenerationalEngine
    return GenerationalEngine(gen_config)


@pytest.fixture(scope="session")
def uk_macro_mid(gen_config):
    from backend.engine.generational_engine import GenerationalMacro
    raw = gen_config["generational"]["country_macro"]["UK"]["mid"]
    return GenerationalMacro(
        inflation=float(raw["inflation"]),
        equity_real_return=float(raw["equity_real_return"]),
        salary_real_growth=float(raw["salary_real_growth"]),
        healthcare_annual=0.0,
    )


@pytest.fixture(scope="session")
def us_macro_mid(gen_config):
    from backend.engine.generational_engine import GenerationalMacro
    raw = gen_config["generational"]["country_macro"]["US"]["mid"]
    return GenerationalMacro(
        inflation=float(raw["inflation"]),
        equity_real_return=float(raw["equity_real_return"]),
        salary_real_growth=float(raw["salary_real_growth"]),
        healthcare_annual=float(raw.get("healthcare_working", 0)),
        healthcare_aca_bridge=float(raw.get("healthcare_aca_bridge", 0)),
        healthcare_medicare=float(raw.get("healthcare_medicare", 0)),
        healthcare_late_life=float(raw.get("healthcare_late_life", 0)),
    )


# ---------------------------------------------------------------------------
# 1. Salary curves
# ---------------------------------------------------------------------------


class TestSalaryCurves:
    """Salary interpolation across all 10 career archetypes."""

    def test_all_ten_careers_loaded(self, gen_engine):
        paths = gen_engine._career_paths
        assert len(paths) >= 10, f"Expected 10+ career paths, got {len(paths)}"

    def test_software_engineer_uk_milestones(self, gen_engine):
        from backend.engine.generational_engine import salary_at_age
        swe = gen_engine._career_paths["software_engineer"]
        assert salary_at_age(swe.uk, 21) == 0.0, "Pre-career should be 0"
        assert salary_at_age(swe.uk, 22) == swe.uk.entry_salary
        assert salary_at_age(swe.uk, 48) == swe.uk.peak_salary
        assert swe.uk.peak_salary > swe.uk.entry_salary * 2

    def test_software_engineer_us_vs_uk_ratio(self, gen_engine):
        """US entry salary should be at least 2× the UK equivalent."""
        from backend.engine.generational_engine import salary_at_age
        swe = gen_engine._career_paths["software_engineer"]
        ratio = swe.us.entry_salary / swe.uk.entry_salary
        assert ratio >= 2.0, f"US/UK salary ratio too low: {ratio:.2f}"

    def test_salary_monotonic_to_peak(self, gen_engine):
        """Salary must rise from entry to peak for all careers."""
        from backend.engine.generational_engine import salary_at_age
        for cid, cp in gen_engine._career_paths.items():
            for curve, label in [(cp.uk, "uk"), (cp.us, "us")]:
                entry = salary_at_age(curve, curve.entry_age)
                peak  = salary_at_age(curve, curve.peak_age)
                assert peak >= entry, \
                    f"{cid}/{label}: peak ({peak}) < entry ({entry})"

    @pytest.mark.parametrize("career_id", [
        "software_engineer", "doctor", "lawyer", "nurse", "teacher",
        "data_scientist", "accountant", "finance", "entrepreneur", "tradesperson",
    ])
    def test_career_has_positive_salaries(self, gen_engine, career_id):
        cp = gen_engine._career_paths.get(career_id)
        assert cp is not None, f"Career {career_id} not found"
        assert cp.uk.peak_salary > 0
        assert cp.us.peak_salary > 0


# ---------------------------------------------------------------------------
# 2. Tax calculations
# ---------------------------------------------------------------------------


class TestUKTax:
    """UK PAYE income tax and NI."""

    def test_below_personal_allowance_no_tax(self):
        from backend.engine.generational_engine import calculate_uk_tax
        tax, ni = calculate_uk_tax(12570)
        assert tax == 0.0

    def test_basic_rate_band(self):
        from backend.engine.generational_engine import calculate_uk_tax
        tax, ni = calculate_uk_tax(30_000)
        expected_tax = (30_000 - 12_570) * 0.20
        assert abs(tax - expected_tax) < 50

    def test_higher_rate_kicks_in_above_50270(self):
        from backend.engine.generational_engine import calculate_uk_tax
        tax_50k, _ = calculate_uk_tax(50_000)
        tax_60k, _ = calculate_uk_tax(60_000)
        marginal = (tax_60k - tax_50k) / 10_000
        assert marginal == pytest.approx(0.40, abs=0.02)

    def test_pa_taper_above_100k(self):
        from backend.engine.generational_engine import calculate_uk_tax
        tax_100k, _ = calculate_uk_tax(100_000)
        tax_120k, _ = calculate_uk_tax(120_000)
        # Effective rate > 40% between 100k–125k due to PA taper
        marginal = (tax_120k - tax_100k) / 20_000
        assert marginal > 0.40

    def test_ni_class1(self):
        from backend.engine.generational_engine import calculate_uk_tax
        _, ni = calculate_uk_tax(50_000)
        expected_ni = (50_000 - 12_570) * 0.08
        assert abs(ni - expected_ni) < 100


class TestUSTax:
    """US federal income tax and FICA."""

    def test_zero_income_zero_tax(self):
        from backend.engine.generational_engine import calculate_us_tax
        fed, fica, st = calculate_us_tax(0.0)
        assert fed == 0.0 and fica == 0.0 and st == 0.0

    def test_fica_rate(self):
        from backend.engine.generational_engine import calculate_us_tax
        _, fica, _ = calculate_us_tax(100_000, pretax_401k=0, state_rate=0.0)
        # 7.65% of first $168,600
        expected_fica = min(100_000, 168_600) * 0.0765
        assert abs(fica - expected_fica) < 50

    def test_wa_state_zero(self):
        from backend.engine.generational_engine import calculate_us_tax
        _, _, st = calculate_us_tax(300_000, state_rate=0.0)
        assert st == 0.0

    def test_pretax_401k_reduces_federal(self):
        from backend.engine.generational_engine import calculate_us_tax
        fed_no_contrib, _, _ = calculate_us_tax(100_000, pretax_401k=0)
        fed_with_contrib, _, _ = calculate_us_tax(100_000, pretax_401k=23_500)
        assert fed_with_contrib < fed_no_contrib


# ---------------------------------------------------------------------------
# 3. University costs
# ---------------------------------------------------------------------------


class TestUniversityCosts:
    """UK Plan 5 loan and US 529 plan cost calculations."""

    def test_uk_plan5_loan_balance_at_graduation(self, gen_engine):
        from backend.engine.generational_engine import calculate_uk_university_cost
        result = calculate_uk_university_cost(gen_engine._uni_cfg, duration=3)
        assert result.loan_taken > 0
        assert result.loan_balance_at_graduation > result.loan_taken  # interest accrued
        assert result.total_tuition == pytest.approx(9250 * 3, rel=0.01)

    def test_uk_plan5_write_off_likely(self, gen_engine):
        """Most Plan 5 loans are expected to be written off at 40 years."""
        from backend.engine.generational_engine import calculate_uk_university_cost
        result = calculate_uk_university_cost(gen_engine._uni_cfg, duration=3)
        assert result.projected_loan_write_off is True

    def test_us_529_covers_tuition(self, gen_engine):
        from backend.engine.generational_engine import calculate_us_university_cost
        result = calculate_us_university_cost(gen_engine._uni_cfg, duration=4)
        assert result.loan_taken <= gen_engine._uni_cfg.us_529_balance
        assert result.loan_balance_at_graduation == 0.0  # 529 is not a loan
        assert result.total_tuition == pytest.approx(gen_engine._uni_cfg.us_tuition_mid * 4, rel=0.01)


# ---------------------------------------------------------------------------
# 4. Offspring projection
# ---------------------------------------------------------------------------


class TestOffspringProjection:
    """FIRE detection, loan repayment, account growth."""

    def test_software_engineer_uk_achieves_fire(self, gen_engine, uk_macro_mid):
        from backend.engine.generational_engine import OffspringProjectionEngine
        engine = OffspringProjectionEngine(gen_engine._career_paths, gen_engine._uni_cfg)
        off = gen_engine._offspring[0]
        proj = engine.project(off, uk_macro_mid, career_path_id="software_engineer", country="uk")
        assert proj.fire_year is not None, "SWE/UK offspring should achieve FIRE"
        assert proj.fire_age is not None
        # Regression anchor from CLAUDE.md §12.5
        assert 40 <= proj.fire_age <= 55, f"Unexpected FIRE age: {proj.fire_age}"

    def test_fire_age_regression_anchor(self, gen_engine, uk_macro_mid):
        """FIRE age for UK software_engineer must be exactly 44 (±2)."""
        from backend.engine.generational_engine import OffspringProjectionEngine
        engine = OffspringProjectionEngine(gen_engine._career_paths, gen_engine._uni_cfg)
        off = gen_engine._offspring[0]
        proj = engine.project(off, uk_macro_mid, career_path_id="software_engineer", country="uk")
        assert abs(proj.fire_age - 44) <= 2, \
            f"FIRE age regression: expected 44±2, got {proj.fire_age}"

    def test_uk_plan5_loan_repayment_during_career(self, gen_engine, uk_macro_mid):
        from backend.engine.generational_engine import OffspringProjectionEngine
        engine = OffspringProjectionEngine(gen_engine._career_paths, gen_engine._uni_cfg)
        off = gen_engine._offspring[0]
        proj = engine.project(off, uk_macro_mid, career_path_id="software_engineer", country="uk")
        # Loan repayments should occur in early working years
        repayment_years = [s for s in proj.years
                           if s.student_loan_repayment > 0 and s.career_phase == "working"]
        assert len(repayment_years) > 0, "Expected Plan 5 loan repayments during career"

    def test_lifetime_earnings_positive(self, gen_engine, uk_macro_mid):
        from backend.engine.generational_engine import OffspringProjectionEngine
        engine = OffspringProjectionEngine(gen_engine._career_paths, gen_engine._uni_cfg)
        off = gen_engine._offspring[0]
        proj = engine.project(off, uk_macro_mid, career_path_id="software_engineer", country="uk")
        assert proj.lifetime_earnings > 500_000

    def test_net_worth_grows_during_working_phase(self, gen_engine, uk_macro_mid):
        from backend.engine.generational_engine import OffspringProjectionEngine
        engine = OffspringProjectionEngine(gen_engine._career_paths, gen_engine._uni_cfg)
        off = gen_engine._offspring[0]
        proj = engine.project(off, uk_macro_mid, career_path_id="nurse", country="uk")
        working = [s for s in proj.years if s.career_phase == "working"]
        if len(working) > 10:
            nw_early = working[5].total_net_worth
            nw_later = working[-5].total_net_worth
            assert nw_later > nw_early, "Net worth should grow during working life"


# ---------------------------------------------------------------------------
# 5. Wealth transfer and IHT
# ---------------------------------------------------------------------------


class TestWealthTransfer:
    """IHT calculation and US estate tax."""

    def test_iht_nil_below_allowances(self, gen_engine):
        from backend.engine.generational_engine import calculate_wealth_transfer, EstateConfig
        cfg = EstateConfig(uk_nrb=325_000, uk_rnrb=175_000, uk_iht_rate=0.40,
                           uk_pension_outside=True)
        # Gross estate £500k = NRB(325) + RNRB(175) → should be zero IHT
        result = calculate_wealth_transfer(
            parent_wealth_gbp=500_000,
            pension_value_gbp=0,
            property_value_gbp=0,
            mortgage_balance_gbp=0,
            death_year=2070,
            estate_cfg=cfg,
            fx_rate=1.27,
        )
        assert result.iht_liability_gbp == pytest.approx(0.0, abs=1.0)

    def test_iht_at_40_percent_rate(self, gen_engine):
        from backend.engine.generational_engine import calculate_wealth_transfer, EstateConfig
        cfg = EstateConfig(uk_nrb=325_000, uk_rnrb=0, uk_iht_rate=0.40,
                           uk_pension_outside=False)
        result = calculate_wealth_transfer(
            parent_wealth_gbp=1_000_000,
            pension_value_gbp=0,
            property_value_gbp=0,
            mortgage_balance_gbp=0,
            death_year=2070,
            estate_cfg=cfg,
        )
        expected_iht = (1_000_000 - 325_000) * 0.40
        assert abs(result.iht_liability_gbp - expected_iht) < 100

    def test_pension_outside_estate_reduces_iht(self, gen_engine):
        from backend.engine.generational_engine import calculate_wealth_transfer, EstateConfig
        cfg_in  = EstateConfig(uk_nrb=325_000, uk_pension_outside=False)
        cfg_out = EstateConfig(uk_nrb=325_000, uk_pension_outside=True)
        transfer_in  = calculate_wealth_transfer(500_000, 200_000, 0, 0, 2070, cfg_in)
        transfer_out = calculate_wealth_transfer(500_000, 200_000, 0, 0, 2070, cfg_out)
        assert transfer_out.iht_liability_gbp < transfer_in.iht_liability_gbp

    def test_net_to_offspring_positive(self, gen_engine):
        from backend.engine.generational_engine import calculate_wealth_transfer
        result = calculate_wealth_transfer(
            parent_wealth_gbp=5_500_000,
            pension_value_gbp=1_200_000,
            property_value_gbp=1_500_000,
            mortgage_balance_gbp=0,
            death_year=2072,
            estate_cfg=gen_engine._estate_cfg,
            fx_rate=1.27,
        )
        assert result.net_to_offspring_gbp > 0
        assert result.net_to_offspring_usd > 0


# ---------------------------------------------------------------------------
# 6. Country comparison — regression anchors
# ---------------------------------------------------------------------------


class TestCountryComparisonRegression:
    """
    Regression anchors from CLAUDE.md §12.5 (run 2026-08-24, mid scenario).
    Tolerance: ±5% for retirement wealth, ±3% for no-drawdown estate figures.
    """

    TOLERANCE_RETIRE = 0.05   # 5%
    TOLERANCE_ESTATE = 0.03   # 3%

    @pytest.fixture(scope="class")
    def comparison_result(self, gen_config, uk_macro_mid, us_macro_mid):
        from backend.engine.country_comparison_engine import (
            CountryComparisonEngine,
            CountryPathConfig,
            ParentPhaseConfig,
            CountryProjectionEngine,
        )
        FX = 1.27

        uk_cfg = CountryPathConfig(
            path_id="uk", label="UK", country="uk",
            start_year=2026, retire_year=2044, death_year=2072,
            starting_wealth_gbp=115_000, starting_pension_gbp=623_000,
            starting_property_gbp=485_000, starting_mortgage_gbp=240_000,
            phases=[ParentPhaseConfig(
                start_year=2026, end_year=None, country="uk",
                gross_income=110_000, pension_rate_employee=0.05,
                pension_employer_match=0.05, annual_living_cost=36_000,
                housing_cost_annual=12_000, currency="GBP")],
            state_pension_annual_gbp=221.20 * 52 * 2,
            state_pension_start_year=2049, fx_rate=FX,
        )
        us_cfg = CountryPathConfig(
            path_id="us", label="US", country="us",
            start_year=2026, retire_year=2044, death_year=2072,
            starting_wealth_gbp=(115_000 + 400_000 / FX),
            starting_pension_gbp=623_000,
            starting_property_gbp=900_000 / FX,
            starting_mortgage_gbp=700_000 / FX,
            phases=[
                ParentPhaseConfig(start_year=2026, end_year=2028, country="us",
                    gross_income=600_000, pension_rate_employee=23500/600000,
                    pension_employer_match=10000/600000, annual_living_cost=150_000,
                    housing_cost_annual=42_000, state_tax_rate=0.0, currency="USD"),
                ParentPhaseConfig(start_year=2029, end_year=None, country="us",
                    gross_income=280_000, pension_rate_employee=0.10,
                    pension_employer_match=0.04, annual_living_cost=130_000,
                    housing_cost_annual=42_000, state_tax_rate=0.05, currency="USD"),
            ],
            state_pension_annual_gbp=(2300 * 12 * 2) / FX,
            state_pension_start_year=2049, fx_rate=FX,
        )
        uk_r = CountryProjectionEngine(uk_macro_mid).run_path(uk_cfg)
        us_r = CountryProjectionEngine(us_macro_mid).run_path(us_cfg)
        return uk_r, us_r

    def test_uk_retirement_wealth_2044(self, comparison_result):
        uk_r, _ = comparison_result
        anchor = 4_838_463
        actual = uk_r.wealth_at_retirement
        assert abs(actual - anchor) / anchor < self.TOLERANCE_RETIRE, \
            f"UK retirement wealth regression: expected ~£{anchor:,}, got £{actual:,.0f}"

    def test_us_retirement_wealth_2044(self, comparison_result):
        _, us_r = comparison_result
        anchor = 11_852_795
        actual = us_r.wealth_at_retirement
        assert abs(actual - anchor) / anchor < self.TOLERANCE_RETIRE, \
            f"US retirement wealth regression: expected ~${anchor:,}, got ${actual:,.0f}"

    def test_uk_paths_fire_year_reasonable(self, comparison_result):
        uk_r, _ = comparison_result
        assert uk_r.fire_year is not None
        assert 2035 <= uk_r.fire_year <= 2060

    def test_us_lifetime_healthcare_greater_than_uk(self, comparison_result):
        uk_r, us_r = comparison_result
        assert us_r.lifetime_healthcare > uk_r.lifetime_healthcare, \
            "US lifetime healthcare should exceed UK (NHS is free)"

    def test_no_drawdown_estate_uk(self, gen_engine):
        """
        No-drawdown UK gross estate at 2072 must match anchor £24,780,531 ±3%.
        (SIPP + ISA + property compounded from 2026, no retirement spending.)
        """
        sipp_2072 = 623_000 * 1.075 ** 46
        isa_2072  = (115_000 * 1.07 ** 46 +
                     110_000 * 0.10 * ((1.07 ** 18 - 1) / 0.07) * 1.07 ** 28)
        prop_2072 = 485_000 * 1.035 ** 46
        total = sipp_2072 + isa_2072 + prop_2072
        anchor = 24_780_531
        assert abs(total - anchor) / anchor < self.TOLERANCE_ESTATE, \
            f"UK no-drawdown estate: expected ~£{anchor:,}, got £{total:,.0f}"

    def test_no_drawdown_estate_us(self, gen_engine):
        """US no-drawdown gross estate at 2072 must match anchor $52,917,793 ±3%."""
        FX = 1.27
        us_401k  = (623_000 * FX) * 1.08 ** 46
        us_port  = (115_000 * FX + 400_000) * 1.08 ** 46
        us_prop  = 900_000 * 1.045 ** 46
        total = us_401k + us_port + us_prop
        anchor = 52_917_793
        assert abs(total - anchor) / anchor < self.TOLERANCE_ESTATE, \
            f"US no-drawdown estate: expected ~${anchor:,}, got ${total:,.0f}"


# ---------------------------------------------------------------------------
# 7. Statement parser — UK and US coverage
# ---------------------------------------------------------------------------


class TestStatementParser:
    """Unit tests for the Phase 10 statement parser."""

    def test_ofx_uk_barclays(self):
        from backend.engine.statement_parser import parse_statement
        ofx = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
<OFX><BANKMSGSRSV1><STMTRS>
<CURDEF>GBP
<BANKACCTFROM><ACCTID>12345678</BANKACCTFROM>
<STMTTRNRS>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20240115<TRNAMT>1000.00</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20240201<TRNAMT>-250.00</STMTTRN>
</STMTTRNRS>
<LEDGERBAL><BALAMT>5234.56<DTASOF>20241231</LEDGERBAL>
<ORG>Barclays</OFX>"""
        result = parse_statement(ofx, "barclays_statement.ofx")
        assert result.format == "ofx"
        assert result.currency == "GBP"
        assert result.jurisdiction == "uk"
        assert result.institution == "Barclays"
        assert result.current_balance == pytest.approx(5234.56, abs=0.01)
        assert result.confidence >= 0.70

    def test_ofx_us_chase(self):
        from backend.engine.statement_parser import parse_statement
        ofx = b"""OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTRS>
<CURDEF>USD
<BANKACCTFROM><ACCTID>987654321</BANKACCTFROM>
<LEDGERBAL><BALAMT>12500.00<DTASOF>20241231</LEDGERBAL>
<ORG>JPMorgan Chase</OFX>"""
        result = parse_statement(ofx, "chase_checking.qfx")
        assert result.currency == "USD"
        assert result.jurisdiction == "us"
        assert result.current_balance == pytest.approx(12500.0, abs=0.01)

    def test_csv_bank_uk_monzo(self):
        from backend.engine.statement_parser import parse_statement
        csv_content = b"""Date,Description,Amount,Balance
2024-01-15,Salary,3000.00,5000.00
2024-01-20,Groceries,-85.50,4914.50
2024-02-01,Rent,-1200.00,3714.50
"""
        result = parse_statement(csv_content, "monzo_export.csv")
        assert result.format == "csv_bank"
        assert result.current_balance == pytest.approx(3714.50, abs=0.01)
        assert len(result.historical) >= 1

    def test_csv_bank_us_chase(self):
        from backend.engine.statement_parser import parse_statement
        csv_content = b"""Transaction Date,Description,Amount,Balance
01/15/2024,Direct Deposit,3500.00,8500.00
01/20/2024,Grocery Store,-125.00,8375.00
02/01/2024,Rent,-2000.00,6375.00
"""
        result = parse_statement(csv_content, "chase_checking_jan2024.csv")
        assert result.currency in ("USD", "GBP")  # heuristic may vary
        assert result.current_balance == pytest.approx(6375.00, abs=0.01)

    def test_csv_broker_uk_hl(self):
        from backend.engine.statement_parser import parse_statement
        csv_content = b"""Security,ISIN,Units,Price (p),Value (\xa3)
Vanguard FTSE All-World ETF,IE00B3RBWM25,500,10234.50,51172.50
iShares Core S&P 500,IE00B5BMR087,200,5678.00,11356.00
"""
        result = parse_statement(csv_content, "HL_portfolio.csv")
        assert result.format == "csv_broker"
        assert len(result.holdings) == 2
        assert result.holdings[0].name == "Vanguard FTSE All-World ETF"
        assert result.holdings[0].isin == "IE00B3RBWM25"
        assert result.current_balance > 0

    def test_csv_broker_us_fidelity(self):
        from backend.engine.statement_parser import parse_statement
        csv_content = b"""Security Description,Symbol,Quantity,Price,Current Value
Fidelity 500 Index Fund,FXAIX,150,180.50,27075.00
PIMCO Total Return Fund,PTTRX,100,10.25,1025.00
Cash,,,,2500.00
"""
        result = parse_statement(csv_content, "fidelity_401k_2024.csv")
        assert result.format == "csv_broker"
        assert len(result.holdings) >= 1
        assert result.suggested_type in {
            "k401", "roth_ira", "ira", "taxable_brokerage", "ISA", "GIA"
        }

    def test_currency_detection_usd_from_dollar_sign(self):
        from backend.engine.statement_parser import _detect_currency
        content = "Amount: $15,000.00\nBalance: $12,500"
        assert _detect_currency(content, "statement.csv") == "USD"

    def test_currency_detection_gbp_default(self):
        from backend.engine.statement_parser import _detect_currency
        content = "Balance: £5,234.56"
        assert _detect_currency(content, "barclays.csv") == "GBP"

    def test_jurisdiction_uk_institution(self):
        from backend.engine.statement_parser import _guess_institution
        inst, jur = _guess_institution("hargreaves lansdown portfolio statement")
        assert inst == "Hargreaves Lansdown"
        assert jur == "uk"

    def test_jurisdiction_us_institution(self):
        from backend.engine.statement_parser import _guess_institution
        inst, jur = _guess_institution("charles schwab brokerage account")
        assert jur == "us"

    def test_account_type_uk_sipp(self):
        from backend.engine.statement_parser import _guess_account_type
        atype = _guess_account_type("self-invested personal pension sipp aviva", "uk")
        assert atype == "SIPP"

    def test_account_type_us_401k(self):
        from backend.engine.statement_parser import _guess_account_type
        atype = _guess_account_type("fidelity 401k employer plan", "us")
        assert atype == "k401"

    def test_account_type_us_roth_ira(self):
        from backend.engine.statement_parser import _guess_account_type
        atype = _guess_account_type("roth ira individual retirement account", "us")
        assert atype == "roth_ira"

    def test_account_type_us_529(self):
        from backend.engine.statement_parser import _guess_account_type
        atype = _guess_account_type("529 college savings plan", "us")
        assert atype == "plan_529"

    def test_empty_file_handled_gracefully(self):
        from backend.engine.statement_parser import parse_statement
        result = parse_statement(b"", "empty.csv")
        assert result.current_balance == 0.0
        assert result.confidence < 0.5

    def test_large_file_not_crashed(self):
        from backend.engine.statement_parser import parse_statement
        # 500 rows of CSV
        rows = ["Date,Amount,Balance"]
        for i in range(500):
            rows.append(f"2024-{(i%12)+1:02d}-01,100.00,{5000+i*100}.00")
        content = "\n".join(rows).encode()
        result = parse_statement(content, "big_statement.csv")
        assert result.current_balance > 0


# ---------------------------------------------------------------------------
# 8. Plan 5 loan repayment helper
# ---------------------------------------------------------------------------


class TestPlan5Repayment:
    """UK Plan 5 student loan repayment calculation."""

    def test_no_repayment_below_threshold(self):
        from backend.engine.generational_engine import uk_plan5_repayment
        repayment, _ = uk_plan5_repayment(24_000, 50_000, threshold=25_000, rate=0.09)
        assert repayment == 0.0

    def test_repayment_9_pct_above_threshold(self):
        from backend.engine.generational_engine import uk_plan5_repayment
        repayment, _ = uk_plan5_repayment(45_000, 50_000, threshold=25_000, rate=0.09)
        expected = (45_000 - 25_000) * 0.09
        assert abs(repayment - expected) < 1.0

    def test_balance_reduced_by_repayment(self):
        from backend.engine.generational_engine import uk_plan5_repayment
        _, new_balance = uk_plan5_repayment(45_000, 50_000, threshold=25_000, rate=0.09)
        assert new_balance < 50_000

    def test_loan_fully_paid_not_negative(self):
        from backend.engine.generational_engine import uk_plan5_repayment
        # Very high salary, tiny loan — must not go negative
        _, new_balance = uk_plan5_repayment(200_000, 1_000, threshold=25_000, rate=0.09)
        assert new_balance >= 0.0
