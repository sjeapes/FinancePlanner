"""
@file yaml_serialiser.py
@brief YAML serialisation / deserialisation for all LifeLedger models.

Converts YAML dicts (loaded from Google Drive or local files) into
typed dataclass instances and back. Performs validation and logs
all parsing errors without raising so that partial configs degrade
gracefully.
"""

import logging
from datetime import date, datetime
from typing import Any, Optional

import yaml

from backend.models.models import (
    AccountType, AppConfig, Checkpoint, Contribution, DrawdownConfig,
    DrawdownMode, EventType, ExpenseBucket, FIRETarget, IncomeSource,
    InterestRatePeriod, InvestmentAccount, InvestmentHolding, Jurisdiction,
    LifeEvent, LumpSumPayment, Mortgage, MortgageType, PensionFund,
    PensionType, Person, PropertyAsset, RatePeriod, SavingsAccount,
    Scenario, StatePension, SymbolLink, TaxBand, TaxProfile, TaxTreatment,
    TrackingMode,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(value: Any) -> Optional[date]:
    """
    @brief Parse a YAML date value into a Python date object.
    @param value String, date, or datetime.
    @return Parsed date or None on failure.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError) as exc:
        logger.warning("_parse_date: could not parse '%s': %s", value, exc)
        return None


def _float(value: Any, default: float = 0.0) -> float:
    """
    @brief Safely coerce a value to float.
    @param value Input value.
    @param default Fallback if coercion fails.
    @return Float value.
    """
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        logger.warning("_float: could not coerce '%s': %s", value, exc)
        return default


def _int(value: Any, default: int = 0) -> int:
    """
    @brief Safely coerce a value to int.
    @param value Input value.
    @param default Fallback if coercion fails.
    @return Int value.
    """
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        logger.warning("_int: could not coerce '%s': %s", value, exc)
        return default


def _enum(enum_class, value: Any, default):
    """
    @brief Safely parse a string into an Enum, falling back to default.
    @param enum_class Target Enum class.
    @param value String value.
    @param default Default enum member.
    @return Enum member or default.
    """
    if value is None:
        return default
    try:
        return enum_class(str(value))
    except ValueError:
        logger.warning("_enum: '%s' is not a valid %s — using default %s",
                       value, enum_class.__name__, default)
        return default


# ── Sub-model parsers ─────────────────────────────────────────────────────────

def _parse_state_pension(d: dict) -> StatePension:
    """
    @brief Parse a state pension dict into a StatePension dataclass.
    @param d Raw dict from YAML.
    @return StatePension instance.
    """
    if not d:
        return StatePension()
    return StatePension(
        eligible=bool(d.get("eligible", True)),
        qualifying_years=_int(d.get("qualifying_years", 0)),
        full_qualifying_years=_int(d.get("full_qualifying_years", 35)),
        expected_start_age=_int(d.get("expected_start_age", 67)),
        weekly_amount=_float(d.get("weekly_amount", 221.20)),
        deferral_years=_int(d.get("deferral_years", 0)),
    )


def _parse_contribution(d: dict) -> Optional[Contribution]:
    """
    @brief Parse a contribution routing rule.
    @param d Raw dict.
    @return Contribution or None if malformed.
    """
    try:
        return Contribution(
            destination_account_id=str(d["destination_account_id"]),
            rate=_float(d.get("rate", 0.0)),
            cap_annual=_float(d["cap_annual"]) if d.get("cap_annual") else None,
            employer_top_up=_float(d.get("employer_top_up", 0.0)),
        )
    except KeyError as exc:
        logger.error("_parse_contribution: missing required key %s in %s", exc, d)
        return None


def _parse_interest_rate_period(d: dict) -> Optional[InterestRatePeriod]:
    """
    @brief Parse an interest rate period dict.
    @param d Raw dict.
    @return InterestRatePeriod or None.
    """
    try:
        return InterestRatePeriod(
            start_date=_parse_date(d.get("start_date")),
            end_date=_parse_date(d.get("end_date")),
            rate=_float(d.get("rate", 0.0)),
        )
    except Exception as exc:
        logger.error("_parse_interest_rate_period: %s in %s", exc, d)
        return None


def _parse_rate_period(d: dict) -> Optional[RatePeriod]:
    """
    @brief Parse a mortgage rate period dict.
    @param d Raw dict.
    @return RatePeriod or None.
    """
    try:
        return RatePeriod(
            start_date=_parse_date(d.get("start_date")),
            end_date=_parse_date(d.get("end_date")),
            rate=_float(d.get("rate", 0.0)),
            rate_type=str(d.get("rate_type", "fixed")),
        )
    except Exception as exc:
        logger.error("_parse_rate_period: %s in %s", exc, d)
        return None


def _parse_lump_sum_payment(d: dict) -> Optional[LumpSumPayment]:
    """
    @brief Parse a lump sum payment dict.
    @param d Raw dict.
    @return LumpSumPayment or None.
    """
    try:
        return LumpSumPayment(
            date=_parse_date(d["date"]),
            amount=_float(d["amount"]),
            label=str(d.get("label", "")),
        )
    except KeyError as exc:
        logger.error("_parse_lump_sum_payment: missing key %s in %s", exc, d)
        return None


def _parse_drawdown_config(d: dict) -> Optional[DrawdownConfig]:
    """
    @brief Parse pension drawdown configuration.
    @param d Raw dict.
    @return DrawdownConfig or None.
    """
    if not d:
        return None
    try:
        return DrawdownConfig(
            mode=_enum(DrawdownMode, d.get("mode"), DrawdownMode.PCT_SWR),
            rate=_float(d.get("rate", 0.04)),
            fixed_amount=_float(d["fixed_amount"]) if d.get("fixed_amount") else None,
            start_date=_parse_date(d.get("start_date")),
            tax_free_lump_sum_pct=_float(d.get("tax_free_lump_sum_pct", 0.25)),
            lump_sum_taken=bool(d.get("lump_sum_taken", False)),
        )
    except Exception as exc:
        logger.error("_parse_drawdown_config: %s", exc)
        return None


def _parse_symbol_link(d: dict) -> Optional[SymbolLink]:
    """
    @brief Parse market data symbol link configuration.
    @param d Raw dict.
    @return SymbolLink or None.
    """
    if not d:
        return None
    try:
        return SymbolLink(
            provider=str(d.get("provider", "yfinance")),
            symbol=str(d.get("symbol", "")),
            isin=d.get("isin"),
            auto_refresh=bool(d.get("auto_refresh", True)),
            refresh_schedule=str(d.get("refresh_schedule", "on_app_open")),
            last_fetched_at=None,
            last_fetched_price=_float(d["last_fetched_price"]) if d.get("last_fetched_price") else None,
        )
    except Exception as exc:
        logger.error("_parse_symbol_link: %s", exc)
        return None


def _parse_tax_band(d: dict) -> Optional[TaxBand]:
    """
    @brief Parse a tax band dict.
    @param d Raw dict.
    @return TaxBand or None.
    """
    try:
        return TaxBand(
            limit=_float(d["limit"]) if d.get("limit") is not None else None,
            rate=_float(d["rate"]),
            label=str(d.get("label", "")),
        )
    except Exception as exc:
        logger.error("_parse_tax_band: %s in %s", exc, d)
        return None


# ── Primary model parsers ─────────────────────────────────────────────────────

def parse_person(d: dict) -> Optional[Person]:
    """
    @brief Parse a person dict into a Person dataclass.
    @param d Raw dict from YAML.
    @return Person or None if required fields missing.
    """
    try:
        return Person(
            id=str(d["id"]),
            name=str(d["name"]),
            date_of_birth=_parse_date(d["date_of_birth"]),
            retirement_age=_int(d.get("retirement_age", 65)),
            life_expectancy=_int(d.get("life_expectancy", 90)),
            tax_profile_id=str(d.get("tax_profile_id", "uk_standard")),
            state_pension=_parse_state_pension(d.get("state_pension", {})),
        )
    except KeyError as exc:
        logger.error("parse_person: missing required key %s in %s", exc, d)
        return None


def parse_income_source(d: dict) -> Optional[IncomeSource]:
    """
    @brief Parse an income source dict.
    @param d Raw dict.
    @return IncomeSource or None.
    """
    try:
        contributions = [
            c for c in (
                _parse_contribution(cd)
                for cd in d.get("contributions", [])
            ) if c is not None
        ]
        return IncomeSource(
            id=str(d["id"]),
            name=str(d["name"]),
            person_id=str(d["person_id"]),
            gross_annual=_float(d["gross_annual"]),
            currency=str(d.get("currency", "GBP")),
            tax_treatment=_enum(TaxTreatment, d.get("tax_treatment"), TaxTreatment.PAYE),
            start_date=_parse_date(d.get("start_date")),
            end_date=_parse_date(d.get("end_date")),
            annual_growth_rate=_float(d.get("annual_growth_rate", 0.0)),
            contributions=contributions,
        )
    except KeyError as exc:
        logger.error("parse_income_source: missing key %s in %s", exc, d)
        return None


def parse_savings_account(d: dict) -> Optional[SavingsAccount]:
    """
    @brief Parse a savings account dict.
    @param d Raw dict.
    @return SavingsAccount or None.
    """
    try:
        periods = [
            p for p in (
                _parse_interest_rate_period(pd)
                for pd in d.get("interest_rate_periods", [])
            ) if p is not None
        ]
        return SavingsAccount(
            id=str(d["id"]),
            name=str(d["name"]),
            account_type=_enum(AccountType, d.get("account_type"), AccountType.GENERAL),
            current_value=_float(d.get("current_value", 0.0)),
            currency=str(d.get("currency", "GBP")),
            owner_id=str(d.get("owner_id", "")),
            interest_rate_periods=periods,
            annual_contribution=_float(d.get("annual_contribution", 0.0)),
            isa_allowance_used=_float(d.get("isa_allowance_used", 0.0)),
        )
    except KeyError as exc:
        logger.error("parse_savings_account: missing key %s in %s", exc, d)
        return None


def parse_investment_holding(d: dict) -> Optional[InvestmentHolding]:
    """
    @brief Parse an investment holding dict.
    @param d Raw dict.
    @return InvestmentHolding or None.
    """
    try:
        return InvestmentHolding(
            id=str(d["id"]),
            name=str(d["name"]),
            instrument_type=str(d.get("instrument_type", "ETF")),
            tracking_mode=_enum(TrackingMode, d.get("tracking_mode"), TrackingMode.TOTAL_VALUE),
            total_value=_float(d["total_value"]) if d.get("total_value") else None,
            units=_float(d["units"]) if d.get("units") is not None else None,
            price_per_unit=_float(d["price_per_unit"]) if d.get("price_per_unit") else None,
            currency=str(d.get("currency", "GBP")),
            assumed_growth_rate=_float(d.get("assumed_growth_rate", 0.07)),
            symbol_link=_parse_symbol_link(d.get("symbol_link")),
        )
    except KeyError as exc:
        logger.error("parse_investment_holding: missing key %s in %s", exc, d)
        return None


def parse_investment_account(d: dict) -> Optional[InvestmentAccount]:
    """
    @brief Parse an investment account dict.
    @param d Raw dict.
    @return InvestmentAccount or None.
    """
    try:
        holdings = [
            h for h in (
                parse_investment_holding(hd)
                for hd in d.get("holdings", [])
            ) if h is not None
        ]
        return InvestmentAccount(
            id=str(d["id"]),
            name=str(d["name"]),
            account_type=_enum(AccountType, d.get("account_type"), AccountType.ISA),
            current_value=_float(d.get("current_value", 0.0)),
            currency=str(d.get("currency", "GBP")),
            owner_id=str(d.get("owner_id", "")),
            assumed_growth_rate=_float(d.get("assumed_growth_rate", 0.07)),
            holdings=holdings,
        )
    except KeyError as exc:
        logger.error("parse_investment_account: missing key %s in %s", exc, d)
        return None


def parse_pension_fund(d: dict) -> Optional[PensionFund]:
    """
    @brief Parse a pension fund dict.
    @param d Raw dict.
    @return PensionFund or None.
    """
    try:
        return PensionFund(
            id=str(d["id"]),
            name=str(d["name"]),
            pension_type=_enum(PensionType, d.get("pension_type"), PensionType.SIPP),
            current_value=_float(d.get("current_value", 0.0)),
            currency=str(d.get("currency", "GBP")),
            owner_id=str(d.get("owner_id", "")),
            assumed_growth_rate=_float(d.get("assumed_growth_rate", 0.07)),
            drawdown_config=_parse_drawdown_config(d.get("drawdown_config")),
        )
    except KeyError as exc:
        logger.error("parse_pension_fund: missing key %s in %s", exc, d)
        return None


def parse_property(d: dict) -> Optional[PropertyAsset]:
    """
    @brief Parse a property asset dict.
    @param d Raw dict.
    @return PropertyAsset or None.
    """
    try:
        return PropertyAsset(
            id=str(d["id"]),
            name=str(d["name"]),
            property_type=str(d.get("property_type", "residential")),
            current_value=_float(d.get("current_value", 0.0)),
            currency=str(d.get("currency", "GBP")),
            owner_ids=d.get("owner_ids", []),
            purchase_date=_parse_date(d.get("purchase_date")),
            purchase_price=_float(d.get("purchase_price", 0.0)),
            assumed_growth_rate=_float(d.get("assumed_growth_rate", 0.035)),
            rental_income_annual=_float(d.get("rental_income_annual", 0.0)),
            mortgage_id=d.get("mortgage_id"),
        )
    except KeyError as exc:
        logger.error("parse_property: missing key %s in %s", exc, d)
        return None


def parse_mortgage(d: dict) -> Optional[Mortgage]:
    """
    @brief Parse a mortgage dict.
    @param d Raw dict.
    @return Mortgage or None.
    """
    try:
        rate_periods = [
            p for p in (
                _parse_rate_period(pd) for pd in d.get("rate_periods", [])
            ) if p is not None
        ]
        lump_sums = [
            p for p in (
                _parse_lump_sum_payment(pd) for pd in d.get("lump_sum_payments", [])
            ) if p is not None
        ]
        return Mortgage(
            id=str(d["id"]),
            name=str(d["name"]),
            property_id=str(d.get("property_id", "")),
            mortgage_type=_enum(MortgageType, d.get("mortgage_type"), MortgageType.REPAYMENT),
            original_principal=_float(d.get("original_principal", 0.0)),
            current_balance=_float(d.get("current_balance", 0.0)),
            currency=str(d.get("currency", "GBP")),
            start_date=_parse_date(d.get("start_date")),
            term_years=_int(d.get("term_years", 25)),
            rate_periods=rate_periods,
            lump_sum_payments=lump_sums,
        )
    except KeyError as exc:
        logger.error("parse_mortgage: missing key %s in %s", exc, d)
        return None


def parse_life_event(d: dict) -> Optional[LifeEvent]:
    """
    @brief Parse a life event dict.
    @param d Raw dict.
    @return LifeEvent or None.
    """
    try:
        return LifeEvent(
            id=str(d["id"]),
            name=str(d["name"]),
            event_type=_enum(EventType, d.get("event_type"), EventType.OTHER),
            date=_parse_date(d.get("date")),
            amount=_float(d.get("amount", 0.0)),
            currency=str(d.get("currency", "GBP")),
            affects_account_id=d.get("affects_account_id"),
            probability=_float(d.get("probability", 1.0)),
        )
    except KeyError as exc:
        logger.error("parse_life_event: missing key %s in %s", exc, d)
        return None


def parse_expense_bucket(d: dict) -> Optional[ExpenseBucket]:
    """
    @brief Parse an expense bucket dict.
    @param d Raw dict.
    @return ExpenseBucket or None.
    """
    try:
        return ExpenseBucket(
            id=str(d["id"]),
            name=str(d["name"]),
            annual_amount=_float(d.get("annual_amount", 0.0)),
            currency=str(d.get("currency", "GBP")),
            applies_to=d.get("applies_to", []),
            inflation_linked=bool(d.get("inflation_linked", True)),
            start_date=_parse_date(d.get("start_date")),
            end_date=_parse_date(d.get("end_date")),
        )
    except KeyError as exc:
        logger.error("parse_expense_bucket: missing key %s in %s", exc, d)
        return None


def parse_fire_target(d: dict) -> Optional[FIRETarget]:
    """
    @brief Parse FIRE target dict.
    @param d Raw dict.
    @return FIRETarget or None.
    """
    if not d:
        return None
    return FIRETarget(
        target_net_worth=_float(d.get("target_net_worth", 1_000_000.0)),
        annual_expenses_target=_float(d.get("annual_expenses_target", 40_000.0)),
        swr=_float(d.get("swr", 0.04)),
        fire_type=str(d.get("fire_type", "fire")),
    )


def parse_tax_profile(d: dict) -> Optional[TaxProfile]:
    """
    @brief Parse a tax profile dict.
    @param d Raw dict.
    @return TaxProfile or None.
    """
    try:
        income_bands = [
            b for b in (_parse_tax_band(bd) for bd in d.get("income_tax_bands", [])) if b
        ]
        ni_bands = [
            b for b in (_parse_tax_band(bd) for bd in d.get("ni_bands", [])) if b
        ]
        return TaxProfile(
            id=str(d["id"]),
            name=str(d["name"]),
            jurisdiction=_enum(Jurisdiction, d.get("jurisdiction"), Jurisdiction.GENERIC),
            income_tax_bands=income_bands,
            ni_bands=ni_bands,
            personal_allowance=_float(d.get("personal_allowance", 0.0)),
            cgt=d.get("cgt", {}),
            allowances=d.get("allowances", {}),
        )
    except KeyError as exc:
        logger.error("parse_tax_profile: missing key %s in %s", exc, d)
        return None


def parse_scenario(d: dict) -> Optional[Scenario]:
    """
    @brief Parse a full scenario YAML dict into a Scenario dataclass.
    @param d Raw dict containing 'scenario' key.
    @return Scenario or None on failure.
    """
    try:
        meta = d.get("scenario", d)
        sc = Scenario(
            id=str(meta.get("id", "unnamed")),
            name=str(meta.get("name", "Unnamed Scenario")),
            description=str(meta.get("description", "")),
            is_base=bool(meta.get("is_base", False)),
            colour=str(meta.get("colour", "#0e9aad")),
        )

        # People
        for pd in d.get("people", []):
            p = parse_person(pd)
            if p:
                sc.people.append(p)

        # Income sources
        for inc in d.get("income_sources", []):
            s = parse_income_source(inc)
            if s:
                sc.income_sources.append(s)

        # Savings accounts
        for acc in d.get("savings_accounts", []):
            s = parse_savings_account(acc)
            if s:
                sc.savings_accounts.append(s)

        # Investment accounts
        for acc in d.get("investment_accounts", []):
            s = parse_investment_account(acc)
            if s:
                sc.investment_accounts.append(s)

        # Pension funds
        for pen in d.get("pension_funds", []):
            p = parse_pension_fund(pen)
            if p:
                sc.pension_funds.append(p)

        # Properties
        for prop in d.get("properties", []):
            p = parse_property(prop)
            if p:
                sc.properties.append(p)

        # Mortgages
        for mort in d.get("mortgages", []):
            m = parse_mortgage(mort)
            if m:
                sc.mortgages.append(m)

        # Expense buckets
        for exp in d.get("expense_buckets", []):
            e = parse_expense_bucket(exp)
            if e:
                sc.expense_buckets.append(e)

        # Life events
        for ev in d.get("life_events", []):
            e = parse_life_event(ev)
            if e:
                sc.life_events.append(e)

        # FIRE target
        sc.fire_target = parse_fire_target(d.get("fire_target"))

        logger.info(
            "parse_scenario: loaded '%s' — %d people, %d income, %d savings, "
            "%d investments, %d pensions, %d properties",
            sc.name, len(sc.people), len(sc.income_sources),
            len(sc.savings_accounts), len(sc.investment_accounts),
            len(sc.pension_funds), len(sc.properties),
        )
        return sc

    except Exception as exc:
        logger.error("parse_scenario: unexpected error: %s", exc, exc_info=True)
        return None


def parse_app_config(d: dict) -> AppConfig:
    """
    @brief Parse application config YAML dict.
    @param d Raw dict.
    @return AppConfig instance with defaults for missing keys.
    """
    try:
        app = d.get("app", {})
        proj = d.get("projection", {})
        inf = d.get("inflation", {})
        mc = d.get("monte_carlo", {})
        return AppConfig(
            base_currency=str(app.get("base_currency", "GBP")),
            log_level=str(app.get("log_level", "INFO")),
            projection_start_year=_int(proj.get("start_year", 2025)),
            projection_end_year=_int(proj.get("end_year", 2075)),
            inflation_base_rate=_float(inf.get("base_rate", 0.025)),
            monte_carlo_simulations=_int(mc.get("simulations", 1000)),
            monte_carlo_seed=mc.get("seed"),
            raw=d,
        )
    except Exception as exc:
        logger.error("parse_app_config: %s", exc, exc_info=True)
        return AppConfig(raw=d)


# ── File I/O ──────────────────────────────────────────────────────────────────

def load_yaml(path: str) -> dict:
    """
    @brief Load a YAML file from disk and return the parsed dict.
    @param path File path.
    @return Parsed dict; empty dict on error.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                logger.error("load_yaml: %s did not contain a YAML mapping", path)
                return {}
            return data
    except FileNotFoundError:
        logger.error("load_yaml: file not found: %s", path)
        return {}
    except yaml.YAMLError as exc:
        logger.error("load_yaml: YAML parse error in %s: %s", path, exc)
        return {}


def dump_yaml(data: dict, path: str) -> bool:
    """
    @brief Dump a dict to a YAML file.
    @param data Dict to serialise.
    @param path Output file path.
    @return True on success, False on error.
    """
    try:
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False, allow_unicode=True)
        logger.info("dump_yaml: saved %s", path)
        return True
    except Exception as exc:
        logger.error("dump_yaml: failed to write %s: %s", path, exc)
        return False


def load_scenario_from_file(path: str) -> Optional[Scenario]:
    """
    @brief Convenience function: load and parse a scenario YAML file.
    @param path Path to scenario .yaml file.
    @return Scenario or None.
    """
    data = load_yaml(path)
    if not data:
        return None
    return parse_scenario(data)


def load_app_config_from_file(path: str) -> AppConfig:
    """
    @brief Convenience function: load and parse the main app config YAML.
    @param path Path to lifeledger_config.yaml.
    @return AppConfig (with defaults if file is missing or malformed).
    """
    data = load_yaml(path)
    return parse_app_config(data)


def load_tax_profiles_from_file(path: str) -> list:
    """
    @brief Load all tax profiles from tax_profiles.yaml.
    @param path Path to tax_profiles.yaml.
    @return List of TaxProfile objects.
    """
    data = load_yaml(path)
    profiles = []
    for pd in data.get("profiles", []):
        p = parse_tax_profile(pd)
        if p:
            profiles.append(p)
    logger.info("load_tax_profiles_from_file: loaded %d profiles from %s",
                len(profiles), path)
    return profiles
