"""
@file pydantic_models.py
@brief Pydantic v2 API schemas mirroring every dataclass from models.py.

These models are used exclusively for FastAPI request/response serialisation.
The underlying dataclasses in models.py are kept untouched; these Pydantic
models provide validation, JSON schema generation, and API I/O.

Each model includes:
  - A ``from_dataclass`` classmethod for converting from the dataclass equivalent.
  - A ``to_dataclass`` method (on request models) for converting back.
"""

import logging
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from backend.models.models import (
    AccountType,
    AppConfig,
    Checkpoint,
    Contribution,
    DrawdownConfig,
    DrawdownMode,
    EventType,
    ExpenseBucket,
    FIRETarget,
    IncomeSource,
    InterestRatePeriod,
    InvestmentAccount,
    InvestmentHolding,
    Jurisdiction,
    LifeEvent,
    LumpSumPayment,
    Mortgage,
    MortgageType,
    PensionFund,
    PensionType,
    Person,
    PropertyAsset,
    RatePeriod,
    SavingsAccount,
    Scenario,
    StatePension,
    SymbolLink,
    TaxBand,
    TaxProfile,
    TaxTreatment,
    TrackingMode,
)

logger = logging.getLogger(__name__)


# ── Sub-models ────────────────────────────────────────────────────────────────

class StatePensionModel(BaseModel):
    """
    @brief Pydantic model for StatePension.
    Mirrors the StatePension dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    eligible: bool = True
    qualifying_years: int = 0
    full_qualifying_years: int = 35
    expected_start_age: int = 67
    weekly_amount: float = 221.20
    deferral_years: int = 0

    @classmethod
    def from_dataclass(cls, obj: StatePension) -> "StatePensionModel":
        """
        @brief Convert a StatePension dataclass instance to this Pydantic model.
        @param obj StatePension dataclass instance.
        @return StatePensionModel instance.
        """
        try:
            return cls(
                eligible=obj.eligible,
                qualifying_years=obj.qualifying_years,
                full_qualifying_years=obj.full_qualifying_years,
                expected_start_age=obj.expected_start_age,
                weekly_amount=obj.weekly_amount,
                deferral_years=obj.deferral_years,
            )
        except Exception as exc:
            logger.error("StatePensionModel.from_dataclass error: %s", exc)
            return cls()

    def to_dataclass(self) -> StatePension:
        """
        @brief Convert this Pydantic model to a StatePension dataclass.
        @return StatePension dataclass instance.
        """
        return StatePension(
            eligible=self.eligible,
            qualifying_years=self.qualifying_years,
            full_qualifying_years=self.full_qualifying_years,
            expected_start_age=self.expected_start_age,
            weekly_amount=self.weekly_amount,
            deferral_years=self.deferral_years,
        )


class InterestRatePeriodModel(BaseModel):
    """
    @brief Pydantic model for InterestRatePeriod.
    Mirrors the InterestRatePeriod dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    rate: float = 0.0

    @classmethod
    def from_dataclass(cls, obj: InterestRatePeriod) -> "InterestRatePeriodModel":
        """
        @brief Convert an InterestRatePeriod dataclass to this model.
        @param obj InterestRatePeriod dataclass instance.
        @return InterestRatePeriodModel instance.
        """
        try:
            return cls(start_date=obj.start_date, end_date=obj.end_date, rate=obj.rate)
        except Exception as exc:
            logger.error("InterestRatePeriodModel.from_dataclass error: %s", exc)
            return cls()

    def to_dataclass(self) -> InterestRatePeriod:
        """
        @brief Convert this Pydantic model to an InterestRatePeriod dataclass.
        @return InterestRatePeriod dataclass instance.
        """
        return InterestRatePeriod(
            start_date=self.start_date,
            end_date=self.end_date,
            rate=self.rate,
        )


class RatePeriodModel(BaseModel):
    """
    @brief Pydantic model for RatePeriod.
    Mirrors the RatePeriod dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    rate: float = 0.0
    rate_type: str = "fixed"

    @classmethod
    def from_dataclass(cls, obj: RatePeriod) -> "RatePeriodModel":
        """
        @brief Convert a RatePeriod dataclass to this model.
        @param obj RatePeriod dataclass instance.
        @return RatePeriodModel instance.
        """
        try:
            return cls(
                start_date=obj.start_date,
                end_date=obj.end_date,
                rate=obj.rate,
                rate_type=obj.rate_type,
            )
        except Exception as exc:
            logger.error("RatePeriodModel.from_dataclass error: %s", exc)
            return cls()

    def to_dataclass(self) -> RatePeriod:
        """
        @brief Convert this Pydantic model to a RatePeriod dataclass.
        @return RatePeriod dataclass instance.
        """
        return RatePeriod(
            start_date=self.start_date,
            end_date=self.end_date,
            rate=self.rate,
            rate_type=self.rate_type,
        )


class LumpSumPaymentModel(BaseModel):
    """
    @brief Pydantic model for LumpSumPayment.
    Mirrors the LumpSumPayment dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    date: Optional[date] = None
    amount: float = 0.0
    label: str = ""

    @classmethod
    def from_dataclass(cls, obj: LumpSumPayment) -> "LumpSumPaymentModel":
        """
        @brief Convert a LumpSumPayment dataclass to this model.
        @param obj LumpSumPayment dataclass instance.
        @return LumpSumPaymentModel instance.
        """
        try:
            return cls(date=obj.date, amount=obj.amount, label=obj.label)
        except Exception as exc:
            logger.error("LumpSumPaymentModel.from_dataclass error: %s", exc)
            return cls()

    def to_dataclass(self) -> LumpSumPayment:
        """
        @brief Convert this Pydantic model to a LumpSumPayment dataclass.
        @return LumpSumPayment dataclass instance.
        """
        return LumpSumPayment(date=self.date, amount=self.amount, label=self.label)


class ContributionModel(BaseModel):
    """
    @brief Pydantic model for Contribution.
    Mirrors the Contribution dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    destination_account_id: str
    rate: float = 0.0
    cap_annual: Optional[float] = None
    employer_top_up: float = 0.0

    @classmethod
    def from_dataclass(cls, obj: Contribution) -> "ContributionModel":
        """
        @brief Convert a Contribution dataclass to this model.
        @param obj Contribution dataclass instance.
        @return ContributionModel instance.
        """
        try:
            return cls(
                destination_account_id=obj.destination_account_id,
                rate=obj.rate,
                cap_annual=obj.cap_annual,
                employer_top_up=obj.employer_top_up,
            )
        except Exception as exc:
            logger.error("ContributionModel.from_dataclass error: %s", exc)
            return cls(destination_account_id="")

    def to_dataclass(self) -> Contribution:
        """
        @brief Convert this Pydantic model to a Contribution dataclass.
        @return Contribution dataclass instance.
        """
        return Contribution(
            destination_account_id=self.destination_account_id,
            rate=self.rate,
            cap_annual=self.cap_annual,
            employer_top_up=self.employer_top_up,
        )


class DrawdownConfigModel(BaseModel):
    """
    @brief Pydantic model for DrawdownConfig.
    Mirrors the DrawdownConfig dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    mode: DrawdownMode = DrawdownMode.PCT_SWR
    rate: float = 0.04
    fixed_amount: Optional[float] = None
    start_date: Optional[date] = None
    tax_free_lump_sum_pct: float = 0.25
    lump_sum_taken: bool = False

    @classmethod
    def from_dataclass(cls, obj: DrawdownConfig) -> "DrawdownConfigModel":
        """
        @brief Convert a DrawdownConfig dataclass to this model.
        @param obj DrawdownConfig dataclass instance.
        @return DrawdownConfigModel instance.
        """
        try:
            return cls(
                mode=obj.mode,
                rate=obj.rate,
                fixed_amount=obj.fixed_amount,
                start_date=obj.start_date,
                tax_free_lump_sum_pct=obj.tax_free_lump_sum_pct,
                lump_sum_taken=obj.lump_sum_taken,
            )
        except Exception as exc:
            logger.error("DrawdownConfigModel.from_dataclass error: %s", exc)
            return cls()

    def to_dataclass(self) -> DrawdownConfig:
        """
        @brief Convert this Pydantic model to a DrawdownConfig dataclass.
        @return DrawdownConfig dataclass instance.
        """
        return DrawdownConfig(
            mode=self.mode,
            rate=self.rate,
            fixed_amount=self.fixed_amount,
            start_date=self.start_date,
            tax_free_lump_sum_pct=self.tax_free_lump_sum_pct,
            lump_sum_taken=self.lump_sum_taken,
        )


class SymbolLinkModel(BaseModel):
    """
    @brief Pydantic model for SymbolLink.
    Mirrors the SymbolLink dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    provider: str = "yfinance"
    symbol: str = ""
    isin: Optional[str] = None
    auto_refresh: bool = True
    refresh_schedule: str = "on_app_open"
    last_fetched_at: Optional[datetime] = None
    last_fetched_price: Optional[float] = None

    @classmethod
    def from_dataclass(cls, obj: SymbolLink) -> "SymbolLinkModel":
        """
        @brief Convert a SymbolLink dataclass to this model.
        @param obj SymbolLink dataclass instance.
        @return SymbolLinkModel instance.
        """
        try:
            return cls(
                provider=obj.provider,
                symbol=obj.symbol,
                isin=obj.isin,
                auto_refresh=obj.auto_refresh,
                refresh_schedule=obj.refresh_schedule,
                last_fetched_at=obj.last_fetched_at,
                last_fetched_price=obj.last_fetched_price,
            )
        except Exception as exc:
            logger.error("SymbolLinkModel.from_dataclass error: %s", exc)
            return cls()

    def to_dataclass(self) -> SymbolLink:
        """
        @brief Convert this Pydantic model to a SymbolLink dataclass.
        @return SymbolLink dataclass instance.
        """
        return SymbolLink(
            provider=self.provider,
            symbol=self.symbol,
            isin=self.isin,
            auto_refresh=self.auto_refresh,
            refresh_schedule=self.refresh_schedule,
            last_fetched_at=self.last_fetched_at,
            last_fetched_price=self.last_fetched_price,
        )


class TaxBandModel(BaseModel):
    """
    @brief Pydantic model for TaxBand.
    Mirrors the TaxBand dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    limit: Optional[float] = None
    rate: float = 0.0
    label: str = ""

    @classmethod
    def from_dataclass(cls, obj: TaxBand) -> "TaxBandModel":
        """
        @brief Convert a TaxBand dataclass to this model.
        @param obj TaxBand dataclass instance.
        @return TaxBandModel instance.
        """
        try:
            return cls(limit=obj.limit, rate=obj.rate, label=obj.label)
        except Exception as exc:
            logger.error("TaxBandModel.from_dataclass error: %s", exc)
            return cls()

    def to_dataclass(self) -> TaxBand:
        """
        @brief Convert this Pydantic model to a TaxBand dataclass.
        @return TaxBand dataclass instance.
        """
        return TaxBand(limit=self.limit, rate=self.rate, label=self.label)


# ── Primary models ────────────────────────────────────────────────────────────

class PersonModel(BaseModel):
    """
    @brief Pydantic model for Person.
    Mirrors the Person dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    date_of_birth: date
    retirement_age: int = 65
    life_expectancy: int = 90
    tax_profile_id: str = "uk_standard"
    state_pension: StatePensionModel = StatePensionModel()

    @classmethod
    def from_dataclass(cls, obj: Person) -> "PersonModel":
        """
        @brief Convert a Person dataclass to this model.
        @param obj Person dataclass instance.
        @return PersonModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                date_of_birth=obj.date_of_birth,
                retirement_age=obj.retirement_age,
                life_expectancy=obj.life_expectancy,
                tax_profile_id=obj.tax_profile_id,
                state_pension=StatePensionModel.from_dataclass(obj.state_pension),
            )
        except Exception as exc:
            logger.error("PersonModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> Person:
        """
        @brief Convert this Pydantic model to a Person dataclass.
        @return Person dataclass instance.
        """
        return Person(
            id=self.id,
            name=self.name,
            date_of_birth=self.date_of_birth,
            retirement_age=self.retirement_age,
            life_expectancy=self.life_expectancy,
            tax_profile_id=self.tax_profile_id,
            state_pension=self.state_pension.to_dataclass(),
        )


class IncomeSourceModel(BaseModel):
    """
    @brief Pydantic model for IncomeSource.
    Mirrors the IncomeSource dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    person_id: str
    gross_annual: float
    currency: str = "GBP"
    tax_treatment: TaxTreatment = TaxTreatment.PAYE
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    annual_growth_rate: float = 0.0
    contributions: list[ContributionModel] = []

    @classmethod
    def from_dataclass(cls, obj: IncomeSource) -> "IncomeSourceModel":
        """
        @brief Convert an IncomeSource dataclass to this model.
        @param obj IncomeSource dataclass instance.
        @return IncomeSourceModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                person_id=obj.person_id,
                gross_annual=obj.gross_annual,
                currency=obj.currency,
                tax_treatment=obj.tax_treatment,
                start_date=obj.start_date,
                end_date=obj.end_date,
                annual_growth_rate=obj.annual_growth_rate,
                contributions=[ContributionModel.from_dataclass(c) for c in obj.contributions],
            )
        except Exception as exc:
            logger.error("IncomeSourceModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> IncomeSource:
        """
        @brief Convert this Pydantic model to an IncomeSource dataclass.
        @return IncomeSource dataclass instance.
        """
        return IncomeSource(
            id=self.id,
            name=self.name,
            person_id=self.person_id,
            gross_annual=self.gross_annual,
            currency=self.currency,
            tax_treatment=self.tax_treatment,
            start_date=self.start_date,
            end_date=self.end_date,
            annual_growth_rate=self.annual_growth_rate,
            contributions=[c.to_dataclass() for c in self.contributions],
        )


class InvestmentHoldingModel(BaseModel):
    """
    @brief Pydantic model for InvestmentHolding.
    Mirrors the InvestmentHolding dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    instrument_type: str = "ETF"
    tracking_mode: TrackingMode = TrackingMode.UNITS
    total_value: Optional[float] = None
    units: Optional[float] = None
    price_per_unit: Optional[float] = None
    currency: str = "GBP"
    assumed_growth_rate: float = 0.07
    symbol_link: Optional[SymbolLinkModel] = None

    @classmethod
    def from_dataclass(cls, obj: InvestmentHolding) -> "InvestmentHoldingModel":
        """
        @brief Convert an InvestmentHolding dataclass to this model.
        @param obj InvestmentHolding dataclass instance.
        @return InvestmentHoldingModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                instrument_type=obj.instrument_type,
                tracking_mode=obj.tracking_mode,
                total_value=obj.total_value,
                units=obj.units,
                price_per_unit=obj.price_per_unit,
                currency=obj.currency,
                assumed_growth_rate=obj.assumed_growth_rate,
                symbol_link=SymbolLinkModel.from_dataclass(obj.symbol_link)
                if obj.symbol_link
                else None,
            )
        except Exception as exc:
            logger.error("InvestmentHoldingModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> InvestmentHolding:
        """
        @brief Convert this Pydantic model to an InvestmentHolding dataclass.
        @return InvestmentHolding dataclass instance.
        """
        return InvestmentHolding(
            id=self.id,
            name=self.name,
            instrument_type=self.instrument_type,
            tracking_mode=self.tracking_mode,
            total_value=self.total_value,
            units=self.units,
            price_per_unit=self.price_per_unit,
            currency=self.currency,
            assumed_growth_rate=self.assumed_growth_rate,
            symbol_link=self.symbol_link.to_dataclass() if self.symbol_link else None,
        )


class SavingsAccountModel(BaseModel):
    """
    @brief Pydantic model for SavingsAccount.
    Mirrors the SavingsAccount dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    account_type: AccountType = AccountType.GENERAL
    current_value: float = 0.0
    currency: str = "GBP"
    owner_id: str = ""
    interest_rate_periods: list[InterestRatePeriodModel] = []
    annual_contribution: float = 0.0
    isa_allowance_used: float = 0.0

    @classmethod
    def from_dataclass(cls, obj: SavingsAccount) -> "SavingsAccountModel":
        """
        @brief Convert a SavingsAccount dataclass to this model.
        @param obj SavingsAccount dataclass instance.
        @return SavingsAccountModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                account_type=obj.account_type,
                current_value=obj.current_value,
                currency=obj.currency,
                owner_id=obj.owner_id,
                interest_rate_periods=[
                    InterestRatePeriodModel.from_dataclass(p)
                    for p in obj.interest_rate_periods
                ],
                annual_contribution=obj.annual_contribution,
                isa_allowance_used=obj.isa_allowance_used,
            )
        except Exception as exc:
            logger.error("SavingsAccountModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> SavingsAccount:
        """
        @brief Convert this Pydantic model to a SavingsAccount dataclass.
        @return SavingsAccount dataclass instance.
        """
        return SavingsAccount(
            id=self.id,
            name=self.name,
            account_type=self.account_type,
            current_value=self.current_value,
            currency=self.currency,
            owner_id=self.owner_id,
            interest_rate_periods=[p.to_dataclass() for p in self.interest_rate_periods],
            annual_contribution=self.annual_contribution,
            isa_allowance_used=self.isa_allowance_used,
        )


class InvestmentAccountModel(BaseModel):
    """
    @brief Pydantic model for InvestmentAccount.
    Mirrors the InvestmentAccount dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    account_type: AccountType = AccountType.ISA
    current_value: float = 0.0
    currency: str = "GBP"
    owner_id: str = ""
    assumed_growth_rate: float = 0.07
    holdings: list[InvestmentHoldingModel] = []

    @classmethod
    def from_dataclass(cls, obj: InvestmentAccount) -> "InvestmentAccountModel":
        """
        @brief Convert an InvestmentAccount dataclass to this model.
        @param obj InvestmentAccount dataclass instance.
        @return InvestmentAccountModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                account_type=obj.account_type,
                current_value=obj.current_value,
                currency=obj.currency,
                owner_id=obj.owner_id,
                assumed_growth_rate=obj.assumed_growth_rate,
                holdings=[InvestmentHoldingModel.from_dataclass(h) for h in obj.holdings],
            )
        except Exception as exc:
            logger.error("InvestmentAccountModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> InvestmentAccount:
        """
        @brief Convert this Pydantic model to an InvestmentAccount dataclass.
        @return InvestmentAccount dataclass instance.
        """
        return InvestmentAccount(
            id=self.id,
            name=self.name,
            account_type=self.account_type,
            current_value=self.current_value,
            currency=self.currency,
            owner_id=self.owner_id,
            assumed_growth_rate=self.assumed_growth_rate,
            holdings=[h.to_dataclass() for h in self.holdings],
        )


class PensionFundModel(BaseModel):
    """
    @brief Pydantic model for PensionFund.
    Mirrors the PensionFund dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    pension_type: PensionType = PensionType.SIPP
    current_value: float = 0.0
    currency: str = "GBP"
    owner_id: str = ""
    assumed_growth_rate: float = 0.07
    drawdown_config: Optional[DrawdownConfigModel] = None

    @classmethod
    def from_dataclass(cls, obj: PensionFund) -> "PensionFundModel":
        """
        @brief Convert a PensionFund dataclass to this model.
        @param obj PensionFund dataclass instance.
        @return PensionFundModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                pension_type=obj.pension_type,
                current_value=obj.current_value,
                currency=obj.currency,
                owner_id=obj.owner_id,
                assumed_growth_rate=obj.assumed_growth_rate,
                drawdown_config=DrawdownConfigModel.from_dataclass(obj.drawdown_config)
                if obj.drawdown_config
                else None,
            )
        except Exception as exc:
            logger.error("PensionFundModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> PensionFund:
        """
        @brief Convert this Pydantic model to a PensionFund dataclass.
        @return PensionFund dataclass instance.
        """
        return PensionFund(
            id=self.id,
            name=self.name,
            pension_type=self.pension_type,
            current_value=self.current_value,
            currency=self.currency,
            owner_id=self.owner_id,
            assumed_growth_rate=self.assumed_growth_rate,
            drawdown_config=self.drawdown_config.to_dataclass()
            if self.drawdown_config
            else None,
        )


class PropertyAssetModel(BaseModel):
    """
    @brief Pydantic model for PropertyAsset.
    Mirrors the PropertyAsset dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    property_type: str = "residential"
    current_value: float = 0.0
    currency: str = "GBP"
    owner_ids: list[str] = []
    purchase_date: Optional[date] = None
    purchase_price: float = 0.0
    assumed_growth_rate: float = 0.035
    rental_income_annual: float = 0.0
    mortgage_id: Optional[str] = None

    @classmethod
    def from_dataclass(cls, obj: PropertyAsset) -> "PropertyAssetModel":
        """
        @brief Convert a PropertyAsset dataclass to this model.
        @param obj PropertyAsset dataclass instance.
        @return PropertyAssetModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                property_type=obj.property_type,
                current_value=obj.current_value,
                currency=obj.currency,
                owner_ids=obj.owner_ids,
                purchase_date=obj.purchase_date,
                purchase_price=obj.purchase_price,
                assumed_growth_rate=obj.assumed_growth_rate,
                rental_income_annual=obj.rental_income_annual,
                mortgage_id=obj.mortgage_id,
            )
        except Exception as exc:
            logger.error("PropertyAssetModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> PropertyAsset:
        """
        @brief Convert this Pydantic model to a PropertyAsset dataclass.
        @return PropertyAsset dataclass instance.
        """
        return PropertyAsset(
            id=self.id,
            name=self.name,
            property_type=self.property_type,
            current_value=self.current_value,
            currency=self.currency,
            owner_ids=self.owner_ids,
            purchase_date=self.purchase_date,
            purchase_price=self.purchase_price,
            assumed_growth_rate=self.assumed_growth_rate,
            rental_income_annual=self.rental_income_annual,
            mortgage_id=self.mortgage_id,
        )


class MortgageModel(BaseModel):
    """
    @brief Pydantic model for Mortgage.
    Mirrors the Mortgage dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    property_id: str = ""
    mortgage_type: MortgageType = MortgageType.REPAYMENT
    original_principal: float = 0.0
    current_balance: float = 0.0
    currency: str = "GBP"
    start_date: Optional[date] = None
    term_years: int = 25
    rate_periods: list[RatePeriodModel] = []
    lump_sum_payments: list[LumpSumPaymentModel] = []

    @classmethod
    def from_dataclass(cls, obj: Mortgage) -> "MortgageModel":
        """
        @brief Convert a Mortgage dataclass to this model.
        @param obj Mortgage dataclass instance.
        @return MortgageModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                property_id=obj.property_id,
                mortgage_type=obj.mortgage_type,
                original_principal=obj.original_principal,
                current_balance=obj.current_balance,
                currency=obj.currency,
                start_date=obj.start_date,
                term_years=obj.term_years,
                rate_periods=[RatePeriodModel.from_dataclass(p) for p in obj.rate_periods],
                lump_sum_payments=[
                    LumpSumPaymentModel.from_dataclass(p) for p in obj.lump_sum_payments
                ],
            )
        except Exception as exc:
            logger.error("MortgageModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> Mortgage:
        """
        @brief Convert this Pydantic model to a Mortgage dataclass.
        @return Mortgage dataclass instance.
        """
        return Mortgage(
            id=self.id,
            name=self.name,
            property_id=self.property_id,
            mortgage_type=self.mortgage_type,
            original_principal=self.original_principal,
            current_balance=self.current_balance,
            currency=self.currency,
            start_date=self.start_date,
            term_years=self.term_years,
            rate_periods=[p.to_dataclass() for p in self.rate_periods],
            lump_sum_payments=[p.to_dataclass() for p in self.lump_sum_payments],
        )


class LifeEventModel(BaseModel):
    """
    @brief Pydantic model for LifeEvent.
    Mirrors the LifeEvent dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    event_type: EventType = EventType.OTHER
    date: Optional[date] = None
    amount: float = 0.0
    currency: str = "GBP"
    affects_account_id: Optional[str] = None
    probability: float = 1.0

    @classmethod
    def from_dataclass(cls, obj: LifeEvent) -> "LifeEventModel":
        """
        @brief Convert a LifeEvent dataclass to this model.
        @param obj LifeEvent dataclass instance.
        @return LifeEventModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                event_type=obj.event_type,
                date=obj.date,
                amount=obj.amount,
                currency=obj.currency,
                affects_account_id=obj.affects_account_id,
                probability=obj.probability,
            )
        except Exception as exc:
            logger.error("LifeEventModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> LifeEvent:
        """
        @brief Convert this Pydantic model to a LifeEvent dataclass.
        @return LifeEvent dataclass instance.
        """
        return LifeEvent(
            id=self.id,
            name=self.name,
            event_type=self.event_type,
            date=self.date,
            amount=self.amount,
            currency=self.currency,
            affects_account_id=self.affects_account_id,
            probability=self.probability,
        )


class ExpenseBucketModel(BaseModel):
    """
    @brief Pydantic model for ExpenseBucket.
    Mirrors the ExpenseBucket dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    annual_amount: float = 0.0
    currency: str = "GBP"
    applies_to: list[str] = []
    inflation_linked: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @classmethod
    def from_dataclass(cls, obj: ExpenseBucket) -> "ExpenseBucketModel":
        """
        @brief Convert an ExpenseBucket dataclass to this model.
        @param obj ExpenseBucket dataclass instance.
        @return ExpenseBucketModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                annual_amount=obj.annual_amount,
                currency=obj.currency,
                applies_to=obj.applies_to,
                inflation_linked=obj.inflation_linked,
                start_date=obj.start_date,
                end_date=obj.end_date,
            )
        except Exception as exc:
            logger.error("ExpenseBucketModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> ExpenseBucket:
        """
        @brief Convert this Pydantic model to an ExpenseBucket dataclass.
        @return ExpenseBucket dataclass instance.
        """
        return ExpenseBucket(
            id=self.id,
            name=self.name,
            annual_amount=self.annual_amount,
            currency=self.currency,
            applies_to=self.applies_to,
            inflation_linked=self.inflation_linked,
            start_date=self.start_date,
            end_date=self.end_date,
        )


class FIRETargetModel(BaseModel):
    """
    @brief Pydantic model for FIRETarget.
    Mirrors the FIRETarget dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    target_net_worth: float = 1_000_000.0
    annual_expenses_target: float = 40_000.0
    swr: float = 0.04
    fire_type: str = "fire"

    @classmethod
    def from_dataclass(cls, obj: FIRETarget) -> "FIRETargetModel":
        """
        @brief Convert a FIRETarget dataclass to this model.
        @param obj FIRETarget dataclass instance.
        @return FIRETargetModel instance.
        """
        try:
            return cls(
                target_net_worth=obj.target_net_worth,
                annual_expenses_target=obj.annual_expenses_target,
                swr=obj.swr,
                fire_type=obj.fire_type,
            )
        except Exception as exc:
            logger.error("FIRETargetModel.from_dataclass error: %s", exc)
            return cls()

    def to_dataclass(self) -> FIRETarget:
        """
        @brief Convert this Pydantic model to a FIRETarget dataclass.
        @return FIRETarget dataclass instance.
        """
        return FIRETarget(
            target_net_worth=self.target_net_worth,
            annual_expenses_target=self.annual_expenses_target,
            swr=self.swr,
            fire_type=self.fire_type,
        )


class TaxProfileModel(BaseModel):
    """
    @brief Pydantic model for TaxProfile.
    Mirrors the TaxProfile dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    jurisdiction: Jurisdiction = Jurisdiction.GENERIC
    income_tax_bands: list[TaxBandModel] = []
    ni_bands: list[TaxBandModel] = []
    personal_allowance: float = 12570.0
    cgt: dict[str, Any] = {}
    allowances: dict[str, Any] = {}

    @classmethod
    def from_dataclass(cls, obj: TaxProfile) -> "TaxProfileModel":
        """
        @brief Convert a TaxProfile dataclass to this model.
        @param obj TaxProfile dataclass instance.
        @return TaxProfileModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                jurisdiction=obj.jurisdiction,
                income_tax_bands=[TaxBandModel.from_dataclass(b) for b in obj.income_tax_bands],
                ni_bands=[TaxBandModel.from_dataclass(b) for b in obj.ni_bands],
                personal_allowance=obj.personal_allowance,
                cgt=obj.cgt,
                allowances=obj.allowances,
            )
        except Exception as exc:
            logger.error("TaxProfileModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> TaxProfile:
        """
        @brief Convert this Pydantic model to a TaxProfile dataclass.
        @return TaxProfile dataclass instance.
        """
        return TaxProfile(
            id=self.id,
            name=self.name,
            jurisdiction=self.jurisdiction,
            income_tax_bands=[b.to_dataclass() for b in self.income_tax_bands],
            ni_bands=[b.to_dataclass() for b in self.ni_bands],
            personal_allowance=self.personal_allowance,
            cgt=self.cgt,
            allowances=self.allowances,
        )


class ScenarioModel(BaseModel):
    """
    @brief Pydantic model for Scenario.
    Mirrors the Scenario dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str = ""
    is_base: bool = False
    colour: str = "#0e9aad"
    people: list[PersonModel] = []
    income_sources: list[IncomeSourceModel] = []
    savings_accounts: list[SavingsAccountModel] = []
    investment_accounts: list[InvestmentAccountModel] = []
    pension_funds: list[PensionFundModel] = []
    properties: list[PropertyAssetModel] = []
    mortgages: list[MortgageModel] = []
    expense_buckets: list[ExpenseBucketModel] = []
    life_events: list[LifeEventModel] = []
    fire_target: Optional[FIRETargetModel] = None

    @classmethod
    def from_dataclass(cls, obj: Scenario) -> "ScenarioModel":
        """
        @brief Convert a Scenario dataclass to this model.
        @param obj Scenario dataclass instance.
        @return ScenarioModel instance.
        """
        try:
            return cls(
                id=obj.id,
                name=obj.name,
                description=obj.description,
                is_base=obj.is_base,
                colour=obj.colour,
                people=[PersonModel.from_dataclass(p) for p in obj.people],
                income_sources=[IncomeSourceModel.from_dataclass(s) for s in obj.income_sources],
                savings_accounts=[
                    SavingsAccountModel.from_dataclass(a) for a in obj.savings_accounts
                ],
                investment_accounts=[
                    InvestmentAccountModel.from_dataclass(a) for a in obj.investment_accounts
                ],
                pension_funds=[PensionFundModel.from_dataclass(p) for p in obj.pension_funds],
                properties=[PropertyAssetModel.from_dataclass(p) for p in obj.properties],
                mortgages=[MortgageModel.from_dataclass(m) for m in obj.mortgages],
                expense_buckets=[
                    ExpenseBucketModel.from_dataclass(e) for e in obj.expense_buckets
                ],
                life_events=[LifeEventModel.from_dataclass(e) for e in obj.life_events],
                fire_target=FIRETargetModel.from_dataclass(obj.fire_target)
                if obj.fire_target
                else None,
            )
        except Exception as exc:
            logger.error("ScenarioModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> Scenario:
        """
        @brief Convert this Pydantic model to a Scenario dataclass.
        @return Scenario dataclass instance.
        """
        return Scenario(
            id=self.id,
            name=self.name,
            description=self.description,
            is_base=self.is_base,
            colour=self.colour,
            people=[p.to_dataclass() for p in self.people],
            income_sources=[s.to_dataclass() for s in self.income_sources],
            savings_accounts=[a.to_dataclass() for a in self.savings_accounts],
            investment_accounts=[a.to_dataclass() for a in self.investment_accounts],
            pension_funds=[p.to_dataclass() for p in self.pension_funds],
            properties=[p.to_dataclass() for p in self.properties],
            mortgages=[m.to_dataclass() for m in self.mortgages],
            expense_buckets=[e.to_dataclass() for e in self.expense_buckets],
            life_events=[e.to_dataclass() for e in self.life_events],
            fire_target=self.fire_target.to_dataclass() if self.fire_target else None,
        )


class CheckpointModel(BaseModel):
    """
    @brief Pydantic model for Checkpoint.
    Mirrors the Checkpoint dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    date: date
    total_net_worth: float = 0.0
    account_values: dict[str, float] = {}
    notes: str = ""

    @classmethod
    def from_dataclass(cls, obj: Checkpoint) -> "CheckpointModel":
        """
        @brief Convert a Checkpoint dataclass to this model.
        @param obj Checkpoint dataclass instance.
        @return CheckpointModel instance.
        """
        try:
            return cls(
                id=obj.id,
                date=obj.date,
                total_net_worth=obj.total_net_worth,
                account_values=obj.account_values,
                notes=obj.notes,
            )
        except Exception as exc:
            logger.error("CheckpointModel.from_dataclass error: %s", exc)
            raise

    def to_dataclass(self) -> Checkpoint:
        """
        @brief Convert this Pydantic model to a Checkpoint dataclass.
        @return Checkpoint dataclass instance.
        """
        return Checkpoint(
            id=self.id,
            date=self.date,
            total_net_worth=self.total_net_worth,
            account_values=self.account_values,
            notes=self.notes,
        )


class AppConfigModel(BaseModel):
    """
    @brief Pydantic model for AppConfig.
    Mirrors the AppConfig dataclass for API I/O.
    """

    model_config = ConfigDict(from_attributes=True)

    base_currency: str = "GBP"
    log_level: str = "INFO"
    projection_start_year: int = 2025
    projection_end_year: int = 2075
    inflation_base_rate: float = 0.025
    monte_carlo_simulations: int = 1000
    monte_carlo_seed: Optional[int] = 42

    @classmethod
    def from_dataclass(cls, obj: AppConfig) -> "AppConfigModel":
        """
        @brief Convert an AppConfig dataclass to this model.
        @param obj AppConfig dataclass instance.
        @return AppConfigModel instance.
        """
        try:
            return cls(
                base_currency=obj.base_currency,
                log_level=obj.log_level,
                projection_start_year=obj.projection_start_year,
                projection_end_year=obj.projection_end_year,
                inflation_base_rate=obj.inflation_base_rate,
                monte_carlo_simulations=obj.monte_carlo_simulations,
                monte_carlo_seed=obj.monte_carlo_seed,
            )
        except Exception as exc:
            logger.error("AppConfigModel.from_dataclass error: %s", exc)
            return cls()
