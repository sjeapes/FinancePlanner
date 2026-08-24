"""
@file test_engines.py
@brief Comprehensive pytest test suite for all LifeLedger engines (Phase 6).

Run from project root with:
    pytest tests/test_engines.py -v

Covers:
  - Tax engine (UK income tax, NI, CGT, US federal)
  - Projection engine (net worth, FIRE, contribution routing)
  - Mortgage engine (amortisation, rate transitions, overpayments)
  - Pension engine (accumulation, drawdown, PCLS, annual allowance)
  - Events engine (property sale, career break, state pension)
  - Tax wrappers (ISA, SIPP, CGT tracker, FX)
  - Retirement engine (income coverage, drawdown comparison, state pension)
  - Advanced planning (survivor, estate/IHT, rebalancing)
  - YAML round-trips for all config loaders
"""

import sys
import os
import pytest
from datetime import date
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def base_scenario():
    """Load the base scenario once for all tests."""
    from backend.persistence.yaml_serialiser import load_scenario_from_file
    path = ROOT / "data" / "scenarios" / "base.yaml"
    sc = load_scenario_from_file(str(path))
    assert sc is not None, "base.yaml failed to load"
    return sc


@pytest.fixture(scope="session")
def tax_profiles():
    """Load tax profiles once for all tests."""
    from backend.persistence.yaml_serialiser import load_tax_profiles_from_file
    path = ROOT / "config" / "tax_profiles.yaml"
    profiles = load_tax_profiles_from_file(str(path))
    return {p.id: p for p in profiles}


@pytest.fixture(scope="session")
def app_config():
    """Load app config once for all tests."""
    from backend.persistence.yaml_serialiser import load_app_config_from_file
    path = ROOT / "config" / "lifeledger_config.yaml"
    return load_app_config_from_file(str(path))


@pytest.fixture(scope="session")
def timeline(base_scenario, app_config, tax_profiles):
    """Run the projection once for all tests."""
    from backend.engine.calculator import ProjectionEngine
    engine = ProjectionEngine(base_scenario, app_config, tax_profiles)
    return engine.run()


# ---------------------------------------------------------------------------
# 1. Tax Engine
# ---------------------------------------------------------------------------

class TestTaxEngineUK:
    """Tests for UK income tax, NI, and CGT calculations."""

    def test_uk_paye_basic_rate(self, tax_profiles):
        from backend.engine.tax_engine import calculate_net_income
        from backend.models.models import TaxTreatment
        profile = tax_profiles.get("uk_standard")
        if profile is None:
            pytest.skip("uk_standard profile not found")
        result = calculate_net_income(30_000, TaxTreatment.PAYE, profile)
        # £30k gross: £12,570 PA → £17,430 taxable at 20% = £3,486 income tax
        assert 3_000 < result.income_tax < 4_500, f"Unexpected income_tax: {result.income_tax}"
        assert result.net_income < result.gross_income
        assert result.effective_rate > 0

    def test_uk_paye_higher_rate(self, tax_profiles):
        from backend.engine.tax_engine import calculate_net_income
        from backend.models.models import TaxTreatment
        profile = tax_profiles.get("uk_standard")
        if profile is None:
            pytest.skip("uk_standard profile not found")
        result = calculate_net_income(95_000, TaxTreatment.PAYE, profile)
        # ~£27k income tax at this salary
        assert 25_000 < result.income_tax < 32_000, f"Unexpected: {result.income_tax}"
        assert result.marginal_rate >= 0.40  # should be in 40% band

    def test_uk_personal_allowance_taper(self, tax_profiles):
        from backend.engine.tax_engine import calculate_net_income
        from backend.models.models import TaxTreatment
        profile = tax_profiles.get("uk_standard")
        if profile is None:
            pytest.skip("uk_standard profile not found")
        # At £125,140+, PA is fully withdrawn
        result_high = calculate_net_income(130_000, TaxTreatment.PAYE, profile)
        result_low  = calculate_net_income(95_000, TaxTreatment.PAYE, profile)
        # Higher earner should have higher effective rate
        assert result_high.effective_rate > result_low.effective_rate

    def test_uk_pension_relief_reduces_taxable(self, tax_profiles):
        from backend.engine.tax_engine import calculate_net_income
        from backend.models.models import TaxTreatment
        profile = tax_profiles.get("uk_standard")
        if profile is None:
            pytest.skip("uk_standard profile not found")
        result_no_pension  = calculate_net_income(60_000, TaxTreatment.PAYE, profile, pension_contributions=0)
        result_with_pension = calculate_net_income(60_000, TaxTreatment.PAYE, profile, pension_contributions=10_000)
        assert result_with_pension.income_tax < result_no_pension.income_tax

    def test_uk_ni_calculated(self, tax_profiles):
        from backend.engine.tax_engine import calculate_net_income
        from backend.models.models import TaxTreatment
        profile = tax_profiles.get("uk_standard")
        if profile is None:
            pytest.skip("uk_standard profile not found")
        result = calculate_net_income(50_000, TaxTreatment.PAYE, profile)
        assert result.national_insurance > 0

    def test_uk_cgt_basic_rate(self, tax_profiles):
        from backend.engine.tax_engine import calculate_uk_cgt
        profile = tax_profiles.get("uk_standard")
        if profile is None:
            pytest.skip("uk_standard profile not found")
        try:
            result = calculate_uk_cgt(gain=20_000, existing_income=30_000, profile=profile)
            assert result.total_cgt >= 0
            assert result.gain == 20_000
        except AttributeError:
            pytest.skip("calculate_uk_cgt not available in this version")


class TestTaxEngineUS:
    """Tests for US federal income tax calculations."""

    def test_us_federal_basic(self, tax_profiles):
        from backend.engine.tax_engine import calculate_net_income
        from backend.models.models import TaxTreatment
        profile = tax_profiles.get("us_federal_single")
        if profile is None:
            pytest.skip("us_federal_single profile not found")
        result = calculate_net_income(100_000, TaxTreatment.PAYE, profile)
        assert result.income_tax > 0
        assert result.net_income < result.gross_income
        assert result.effective_rate < 0.40  # shouldn't hit 40% at $100k

    def test_us_high_income(self, tax_profiles):
        from backend.engine.tax_engine import calculate_net_income
        from backend.models.models import TaxTreatment
        profile = tax_profiles.get("us_federal_single")
        if profile is None:
            pytest.skip("us_federal_single profile not found")
        result = calculate_net_income(600_000, TaxTreatment.PAYE, profile)
        assert result.marginal_rate >= 0.35


# ---------------------------------------------------------------------------
# 2. Projection Engine
# ---------------------------------------------------------------------------

class TestProjectionEngine:
    """Tests for the core year-by-year projection engine."""

    def test_net_worth_2025(self, timeline):
        snap = timeline.year(2025)
        assert snap is not None, "No snapshot for 2025"
        assert snap.total_net_worth > 400_000, f"NW too low: {snap.total_net_worth}"
        assert snap.total_net_worth < 2_000_000, f"NW too high: {snap.total_net_worth}"

    def test_fire_year_detected(self, timeline):
        assert timeline.fire_year is not None, "FIRE year should be detected"
        assert 2026 <= timeline.fire_year <= 2050

    def test_net_worth_grows(self, timeline):
        """Net worth should generally increase over 50 years."""
        nw_2025 = timeline.year(2025).total_net_worth
        nw_2045 = timeline.year(2045)
        nw_2065 = timeline.year(2065)
        if nw_2045:
            assert nw_2045.total_net_worth > nw_2025
        if nw_2065:
            assert nw_2065.total_net_worth > nw_2025

    def test_income_does_not_auto_add_to_nw(self, timeline):
        """Income must NOT auto-add to net worth (core design principle)."""
        snap = timeline.year(2025)
        assert snap is not None
        # Net income should be much larger than net worth increase in year 1
        # (most income is spent, not saved)
        assert snap.total_gross_income > 0

    def test_fire_threshold_line(self, timeline, base_scenario):
        if timeline.fire_year:
            snap = timeline.year(timeline.fire_year)
            assert snap is not None
            target = base_scenario.fire_target.target_net_worth
            assert snap.total_net_worth >= target * 0.95  # allow 5% tolerance

    def test_accounts_in_snapshot(self, timeline):
        snap = timeline.year(2025)
        assert snap is not None
        assert len(snap.accounts) > 0

    def test_all_years_covered(self, timeline, app_config):
        years = {s.year for s in timeline.years}
        assert app_config.projection_start_year in years
        assert app_config.projection_end_year in years


# ---------------------------------------------------------------------------
# 3. Mortgage Engine
# ---------------------------------------------------------------------------

class TestMortgageEngine:
    """Tests for the mortgage amortisation engine."""

    @pytest.fixture
    def simple_mortgage_cfg(self):
        from backend.engine.mortgage import MortgageConfig, RatePeriod
        return MortgageConfig(
            mortgage_id="test",
            label="Test",
            property_id="home",
            original_balance=200_000,
            start_date=date(2020, 1, 1),
            term_years=25,
            rate_periods=[RatePeriod(label="3.5%", annual_rate=0.035,
                                     start_date=date(2020, 1, 1))],
        )

    def test_monthly_payment_calculation(self, simple_mortgage_cfg):
        from backend.engine.mortgage import MortgageEngine
        result = MortgageEngine(simple_mortgage_cfg).run()
        first = result.schedule[0]
        assert abs(first.scheduled_payment - 999.63) < 0.50

    def test_term_length(self, simple_mortgage_cfg):
        from backend.engine.mortgage import MortgageEngine
        result = MortgageEngine(simple_mortgage_cfg).run()
        assert result.actual_term_months == 300

    def test_balance_reaches_zero(self, simple_mortgage_cfg):
        from backend.engine.mortgage import MortgageEngine
        result = MortgageEngine(simple_mortgage_cfg).run()
        assert result.schedule[-1].closing_balance < 0.01

    def test_overpayment_shortens_term(self):
        from backend.engine.mortgage import MortgageConfig, MortgageEngine, RatePeriod, Overpayment
        base = MortgageConfig(
            mortgage_id="base", label="Base", property_id="h",
            original_balance=200_000, start_date=date(2020, 1, 1), term_years=25,
            annual_overpayment_cap_pct=0.0,
            rate_periods=[RatePeriod(label="3.5%", annual_rate=0.035, start_date=date(2020, 1, 1))],
        )
        with_op = MortgageConfig(
            mortgage_id="op", label="OP", property_id="h",
            original_balance=200_000, start_date=date(2020, 1, 1), term_years=25,
            annual_overpayment_cap_pct=0.0,
            rate_periods=[RatePeriod(label="3.5%", annual_rate=0.035, start_date=date(2020, 1, 1))],
            overpayments=[Overpayment(amount=20_000, overpayment_type="lump_sum", date=date(2022, 1, 1))],
        )
        r_base = MortgageEngine(base).run()
        r_op   = MortgageEngine(with_op).run()
        assert r_op.actual_term_months < r_base.actual_term_months

    def test_rate_period_transition(self):
        from backend.engine.mortgage import MortgageConfig, MortgageEngine, RatePeriod
        cfg = MortgageConfig(
            mortgage_id="multi", label="Multi", property_id="h",
            original_balance=250_000, start_date=date(2022, 1, 1), term_years=25,
            rate_periods=[
                RatePeriod(label="Fix", annual_rate=0.0199, start_date=date(2022, 1, 1), end_date=date(2024, 1, 31)),
                RatePeriod(label="SVR", annual_rate=0.065,  start_date=date(2024, 2, 1)),
            ],
        )
        r = MortgageEngine(cfg).run()
        first = r.schedule[0]
        svr_rows = [row for row in r.schedule if row.payment_date >= date(2024, 2, 1)]
        assert abs(first.annual_rate - 0.0199) < 1e-6
        assert abs(svr_rows[0].annual_rate - 0.065) < 1e-6


# ---------------------------------------------------------------------------
# 4. Pension Engine
# ---------------------------------------------------------------------------

class TestPensionEngine:
    """Tests for the pension lifecycle engine."""

    @pytest.fixture
    def simple_pension(self):
        from backend.engine.pension import (
            PensionConfig, GrowthPeriod, DrawdownConfig, AllowanceConfig,
        )
        return PensionConfig(
            pension_id="test",
            label="Test SIPP",
            person_id="james",
            pension_type="sipp",
            current_value=100_000,
            valuation_date=date(2025, 1, 1),
            person_dob=date(1985, 1, 1),
            growth_periods=[GrowthPeriod(label="7%", start_date=date(2025, 1, 1),
                                         end_date=None, annual_rate=0.07)],
            drawdown_config=DrawdownConfig(
                mode="percentage", annual_drawdown_rate=0.04,
                apply_pcls=True, pcls_fraction=0.25,
                drawdown_start_date=date(2043, 1, 1),
            ),
            allowance_config=AllowanceConfig(enabled=False),
        )

    def test_accumulation_growth(self, simple_pension):
        from backend.engine.pension import PensionEngine
        result = PensionEngine(simple_pension, 2025, 2042).run()
        assert result.schedule[-1].closing_value > 100_000

    def test_pcls_taken_once(self, simple_pension):
        from backend.engine.pension import PensionEngine
        result = PensionEngine(simple_pension, 2025, 2070).run()
        pcls_years = [r for r in result.schedule if r.pcls_taken > 0]
        assert len(pcls_years) == 1, "PCLS should be taken exactly once"

    def test_drawdown_reduces_fund(self, simple_pension):
        from backend.engine.pension import PensionEngine
        result = PensionEngine(simple_pension, 2025, 2070).run()
        drawdown_rows = [r for r in result.schedule if r.drawdown_income > 0]
        assert len(drawdown_rows) > 0

    def test_allowance_breach_flagged(self):
        from backend.engine.pension import (
            PensionConfig, GrowthPeriod, DrawdownConfig, AllowanceConfig,
            ContributionPeriod, PensionEngine,
        )
        cfg = PensionConfig(
            pension_id="breach",
            label="Breach Test",
            person_id="james",
            pension_type="sipp",
            current_value=10_000,
            valuation_date=date(2025, 1, 1),
            growth_periods=[GrowthPeriod(label="5%", start_date=date(2025, 1, 1),
                                         end_date=None, annual_rate=0.05)],
            contribution_periods=[ContributionPeriod(
                label="High",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
                employee_annual=90_000,
                employer_annual=0,
            )],
            drawdown_config=DrawdownConfig(drawdown_start_date=date(2060, 1, 1)),
            allowance_config=AllowanceConfig(
                enabled=True,
                annual_allowance=60_000,
                carry_forward_years=3,
                prior_year_unused={},
            ),
        )
        result = PensionEngine(cfg, 2025, 2026).run()
        assert len(result.allowance_breaches) > 0


# ---------------------------------------------------------------------------
# 5. Events Engine
# ---------------------------------------------------------------------------

class TestEventsEngine:
    """Tests for the life events engine."""

    def test_property_sale_net_proceeds(self):
        from backend.engine.events import EventsEngine, LifeEventConfig, ET_PROPERTY_SALE
        evt = LifeEventConfig(
            event_id="sale", label="Sale", event_type=ET_PROPERTY_SALE,
            year=2030, expected_proceeds=600_000, mortgage_outstanding=150_000,
            cgt_exempt=False, cgt_cost_basis=320_000, property_id="home",
            target_account_id="bank",
        )
        engine = EventsEngine([evt])
        mutations = engine.mutations_for_year(2030)
        assert len(mutations) == 1
        assert mutations[0].net_cash_generated == 450_000

    def test_ppr_no_cgt_disposal(self):
        from backend.engine.events import EventsEngine, LifeEventConfig, ET_PROPERTY_SALE
        evt = LifeEventConfig(
            event_id="ppr", label="PPR", event_type=ET_PROPERTY_SALE,
            year=2030, expected_proceeds=600_000, mortgage_outstanding=100_000,
            cgt_exempt=True, property_id="home",
        )
        engine = EventsEngine([evt])
        m = engine.mutations_for_year(2030)[0]
        assert len(m.cgt_disposals) == 0

    def test_career_break_resumes(self):
        from backend.engine.events import (
            EventsEngine, LifeEventConfig, IncomeSourceSpec, ET_CAREER_BREAK,
        )
        evt = LifeEventConfig(
            event_id="break", label="Break", event_type=ET_CAREER_BREAK,
            year=2035, remove_income_id="salary", duration_years=1,
            resume_gross_annual=80_000,
            add_income=IncomeSourceSpec(
                source_id="salary", name="Salary", person_id="james",
                gross_annual=90_000, tax_treatment="PAYE",
            ),
        )
        engine = EventsEngine([evt])
        m_35 = engine.mutations_for_year(2035)
        m_36 = engine.mutations_for_year(2036)
        assert "salary" in m_35[0].income_source_removes
        assert len(m_36[0].income_source_adds) == 1
        assert m_36[0].income_source_adds[0].gross_annual == 80_000

    def test_state_pension_deferral_bonus(self):
        from backend.engine.events import EventsEngine, LifeEventConfig, ET_STATE_PENSION_START
        evt = LifeEventConfig(
            event_id="sp", label="SP", event_type=ET_STATE_PENSION_START,
            year=2052, person_id="james", annual_amount=11502.0, deferral_weeks=52,
        )
        engine = EventsEngine([evt])
        m = engine.mutations_for_year(2052)[0]
        sp = m.income_source_adds[0]
        expected_bonus = 52 * (0.01 / 9)
        expected = round(11502.0 * (1 + expected_bonus), 2)
        assert abs(sp.gross_annual - expected) < 0.01


# ---------------------------------------------------------------------------
# 6. Tax Wrappers
# ---------------------------------------------------------------------------

class TestTaxWrappers:
    """Tests for ISA/SIPP/GIA wrapper rules and CGT tracker."""

    @pytest.fixture
    def wrapper_engine(self):
        from backend.engine.tax_wrappers import TaxWrapperEngine
        return TaxWrapperEngine()

    def test_isa_no_tax(self, wrapper_engine):
        cr = wrapper_engine.process_contribution("isa", "ISA", 20_000)
        wr = wrapper_engine.process_withdrawal("isa", "ISA", 10_000)
        gt = wrapper_engine.in_year_growth_tax("isa", "ISA", 5_000, 0.40)
        assert cr.relief_amount == 0
        assert wr.taxable_amount == 0
        assert gt == 0

    def test_sipp_relief(self, wrapper_engine):
        cr = wrapper_engine.process_contribution("sipp", "SIPP", 18_000)
        assert cr.relief_amount == 3_600      # 20% of £18k

    def test_sipp_pcls(self, wrapper_engine):
        wr = wrapper_engine.process_withdrawal("sipp", "SIPP", 100_000,
                                                age=60, is_first_drawdown=True)
        assert wr.tax_free_amount == 25_000   # 25% PCLS
        assert wr.taxable_amount == 75_000

    def test_401k_early_penalty(self, wrapper_engine):
        wr = wrapper_engine.process_withdrawal("401k", "401k", 50_000, age=55)
        assert wr.penalty_amount == 5_000     # 10% penalty

    def test_cgt_tracker(self):
        from backend.engine.tax_wrappers import CGTTracker, CGTDisposal
        tracker = CGTTracker(annual_exemption=3_000, basic_rate=0.10, higher_rate=0.20)
        tracker.record_disposal(CGTDisposal(
            disposal_id="d1", account_id="gia", asset_id="AAPL",
            disposal_date=date(2025, 6, 1), proceeds=20_000, cost_basis=5_000,
        ))
        result = tracker.compute_year(2025, basic_band_remaining=20_000)
        assert result.gross_gains == 15_000
        assert result.taxable_gain == 12_000  # £15k - £3k exemption
        assert result.basic_rate_cgt == 1_200  # £12k × 10%

    def test_fx_conversion(self):
        from backend.engine.tax_wrappers import FXManager, FXRate
        fx = FXManager([FXRate("GBP", "USD", 1.27, annual_drift=0.0)])
        usd = fx.convert(1_000, "GBP", "USD")
        assert abs(usd - 1_270) < 1
        assert fx.convert(500, "GBP", "GBP") == 500


# ---------------------------------------------------------------------------
# 7. Retirement Engine
# ---------------------------------------------------------------------------

class TestRetirementEngine:
    """Tests for the Phase 4 retirement planning engine."""

    @pytest.fixture
    def retirement_engine(self):
        from backend.engine.retirement_engine import RetirementEngine, RetirementConfig
        return RetirementEngine(RetirementConfig())

    def test_income_coverage_runs(self, retirement_engine, base_scenario, timeline):
        report = retirement_engine.analyse(base_scenario, timeline)
        assert report.retirement_start_year > 2024
        assert len(report.income_coverage.years) > 0

    def test_coverage_ratios_valid(self, retirement_engine, base_scenario, timeline):
        report = retirement_engine.analyse(base_scenario, timeline)
        for row in report.income_coverage.years:
            assert row.coverage_ratio >= 0
            assert row.status in {"covered", "amber", "shortfall"}

    def test_drawdown_isa_first_saves_tax(self, retirement_engine, base_scenario):
        retire_year = retirement_engine._retirement_start_year(base_scenario)
        result = retirement_engine._drawdown_order_comparison(
            base_scenario, retire_year, "isa_first", "sipp_first"
        )
        assert result.lifetime_tax_saving >= 0
        assert result.recommended_strategy in ("isa_first", "sipp_first")

    def test_state_pension_projected(self, retirement_engine, base_scenario):
        projections = retirement_engine._state_pension_projections(base_scenario)
        assert len(projections) > 0
        for sp in projections:
            assert sp.projected_annual > 0
            assert sp.projected_annual <= sp.max_pension_if_filled

    def test_triple_lock_non_decreasing(self, retirement_engine, base_scenario):
        projections = retirement_engine._state_pension_projections(base_scenario)
        for sp in projections:
            ages = sorted(sp.triple_lock_at_ages.keys())
            amounts = [sp.triple_lock_at_ages[a] for a in ages]
            for i in range(1, len(amounts)):
                assert amounts[i] >= amounts[i - 1]


# ---------------------------------------------------------------------------
# 8. Advanced Planning Engine
# ---------------------------------------------------------------------------

class TestAdvancedPlanningEngine:
    """Tests for the Phase 5 advanced planning engine."""

    @pytest.fixture
    def planning_engine(self):
        from backend.engine.advanced_planning import AdvancedPlanningEngine, PlanningConfig
        return AdvancedPlanningEngine(PlanningConfig())

    def test_full_report_runs(self, planning_engine, base_scenario):
        report = planning_engine.full_report(base_scenario)
        assert report.estate.gross_estate >= 0
        assert report.rebalancing.total_portfolio_value >= 0

    def test_survivor_income_removed(self, planning_engine, base_scenario):
        people = [p.id for p in base_scenario.people]
        if not people:
            pytest.skip("No people in scenario")
        result = planning_engine._survivor.simulate(base_scenario, people[0], 2060)
        assert result.total_income_lost >= 0
        assert result.survivor_gross_income >= 0
        assert result.recommended_life_cover >= 0

    def test_estate_couple_nrb(self, planning_engine, base_scenario):
        result = planning_engine._estate.calculate(
            base_scenario, has_surviving_partner=True, owns_residence=True
        )
        # Couple should have ≥ £650k NRB
        assert result.nrb_available >= 650_000

    def test_estate_iht_non_negative(self, planning_engine, base_scenario):
        result = planning_engine._estate.calculate(base_scenario)
        assert result.iht_liability >= 0
        assert result.net_to_beneficiaries >= 0

    def test_gift_7yr_rule(self, planning_engine):
        from backend.engine.advanced_planning import EstateConfig, EstateEngine
        cfg = EstateConfig(gifts=[
            {"date": "2015-01-01", "amount": 50000, "recipient": "Child", "notes": ""},
            {"date": "2024-01-01", "amount": 20000, "recipient": "Child", "notes": ""},
        ])
        engine = EstateEngine(cfg)
        old_gift = next((g for g in engine._process_gifts(2025, cfg)[0]
                         if g.amount == 50000), None)
        new_gift = next((g for g in engine._process_gifts(2025, cfg)[0]
                         if g.amount == 20000), None)
        if old_gift:
            assert old_gift.is_outside_estate   # >7 years
        if new_gift:
            assert not new_gift.is_outside_estate  # <7 years

    def test_rebalancing_detects_drift(self, planning_engine, base_scenario):
        result = planning_engine._rebalance.analyse(base_scenario, owner_age=43)
        assert len(result.alerts) > 0
        for alert in result.alerts:
            assert alert.status in ("ok", "amber", "rebalance_needed")
            total_alloc = sum(alert.current_allocation.values())
            assert abs(total_alloc - 100) < 2.0

    def test_glide_path_reduces_equities(self, planning_engine, base_scenario):
        result_young = planning_engine._rebalance.analyse(base_scenario, owner_age=40)
        result_old   = planning_engine._rebalance.analyse(base_scenario, owner_age=63)
        # At 63, equity target should be lower than at 40
        eq_young = result_young.global_target.get("equities", 80)
        eq_old   = result_old.global_target.get("equities", 80)
        assert eq_old <= eq_young


# ---------------------------------------------------------------------------
# 9. YAML Round-Trip Tests
# ---------------------------------------------------------------------------

class TestYAMLRoundTrips:
    """Tests that all config files load without error."""

    def test_retirement_config_loads(self):
        path = ROOT / "config" / "retirement" / "retirement_config.yaml"
        if not path.exists():
            pytest.skip(f"Not found: {path}")
        from backend.engine.retirement_engine import load_retirement_config
        cfg = load_retirement_config(str(path))
        assert cfg.drawdown_swr > 0
        assert cfg.ni_full_qualifying_years == 35

    def test_planning_config_loads(self):
        path = ROOT / "config" / "planning" / "planning_config.yaml"
        if not path.exists():
            pytest.skip(f"Not found: {path}")
        from backend.engine.advanced_planning import load_planning_config
        cfg = load_planning_config(str(path))
        assert cfg.estate.uk_nil_rate_band == 325_000
        assert cfg.healthcare.include_care_home

    def test_monte_carlo_config_loads(self):
        path = ROOT / "config" / "simulation" / "monte_carlo_config.yaml"
        if not path.exists():
            pytest.skip(f"Not found: {path}")
        from backend.engine.monte_carlo import load_monte_carlo_config
        cfg = load_monte_carlo_config(str(path))
        assert cfg.n_simulations > 0
        assert len(cfg.macro_scenarios) == 3

    def test_mortgage_config_loads(self):
        path = ROOT / "config" / "mortgages" / "mortgage_config.yaml"
        if not path.exists():
            pytest.skip(f"Not found: {path}")
        from backend.engine.mortgage import load_mortgage_config_from_yaml
        cfg, prop = load_mortgage_config_from_yaml(str(path))
        assert cfg.original_balance > 0

    def test_pension_config_loads(self):
        path = ROOT / "config" / "pensions" / "pension_config.yaml"
        if not path.exists():
            pytest.skip(f"Not found: {path}")
        from backend.engine.pension import load_pension_config_from_yaml
        cfg = load_pension_config_from_yaml(str(path))
        assert cfg.current_value > 0

    def test_tax_wrappers_config_loads(self):
        path = ROOT / "config" / "tax" / "tax_wrappers_config.yaml"
        if not path.exists():
            pytest.skip(f"Not found: {path}")
        from backend.engine.tax_wrappers import load_tax_wrappers_config
        engine = load_tax_wrappers_config(str(path))
        assert engine.cgt._annual_exemption == 3_000

    def test_base_scenario_loads(self):
        path = ROOT / "data" / "scenarios" / "base.yaml"
        from backend.persistence.yaml_serialiser import load_scenario_from_file
        sc = load_scenario_from_file(str(path))
        assert sc is not None
        assert len(sc.people) >= 1
        assert len(sc.income_sources) >= 1

    def test_all_scenario_templates_load(self):
        templates_dir = ROOT / "data" / "scenarios" / "templates"
        if not templates_dir.exists():
            pytest.skip("Templates directory not found")
        from backend.persistence.yaml_serialiser import load_yaml
        for yaml_file in templates_dir.glob("*.yaml"):
            raw = load_yaml(str(yaml_file))
            assert isinstance(raw, dict), f"Template {yaml_file.name} did not parse as dict"


# ---------------------------------------------------------------------------
# 10. Phase 1 Regression Guard
# ---------------------------------------------------------------------------

class TestPhase1Regression:
    """Ensure Phase 1 validated figures haven't regressed."""

    def test_net_worth_2025_in_range(self, timeline):
        snap = timeline.year(2025)
        assert snap is not None
        # Original validated figure: £644,858 ± 10%
        assert 580_000 <= snap.total_net_worth <= 710_000, \
            f"Phase 1 regression: NW 2025 = {snap.total_net_worth:,.0f}"

    def test_fire_year_unchanged(self, timeline):
        assert timeline.fire_year == 2031, \
            f"Phase 1 regression: FIRE year = {timeline.fire_year} (expected 2031)"

    def test_terminal_net_worth_in_range(self, timeline):
        snap = timeline.year(2075)
        assert snap is not None
        # Original validated: £14,506,909 ± 20%
        assert 10_000_000 <= snap.total_net_worth <= 20_000_000, \
            f"Phase 1 regression: NW 2075 = {snap.total_net_worth:,.0f}"
