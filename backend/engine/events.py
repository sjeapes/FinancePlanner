"""
@file events.py
@brief Life events engine for LifeLedger.

Processes typed, year-triggered life events into structured ``EventMutation``
objects that the projection engine (calculator.py) can consume without needing
to understand the specifics of each event type.

Supported event types:

  property_sale        — sells a property, generates proceeds, optional CGT flag
  property_purchase    — buys a property, deposits equity, deducts stamp duty
  inheritance          — receives an inheritance with optional probability weight
  lump_sum_income      — one-off windfall (bonus, compensation, lottery)
  major_expense        — one-off large expense (car, wedding, renovation)
  job_change           — removes old income source, adds a new one
  career_break         — suspends income source for a configurable number of years
  emigration           — changes tax jurisdiction from a set year
  care_cost_start      — injects an ongoing annual care cost expense bucket
  care_cost_end        — removes a care cost expense bucket
  state_pension_start  — adds state pension as a new income source
  partner_death        — removes partner income, adjusts household expenses
  business_start       — adds self-employed income source
  redundancy           — removes income source, optionally adds a lump sum
  asset_contribution   — routes a lump sum into a specific account

Events are loaded from YAML and processed year by year.  Where a
``probability`` < 1.0 is set, the event is modelled at its full expected
value scaled by probability unless ``apply_probability_scaling`` is True
on the engine, in which case it is applied stochastically during Monte Carlo.

Integration with calculator.py:
    engine = EventsEngine(events)
    mutations = engine.mutations_for_year(year)
    for m in mutations:
        calculator.apply_mutation(m)   # apply account changes, income changes, etc.

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import yaml

logger = logging.getLogger("lifeledger.events")


# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

ET_PROPERTY_SALE        = "property_sale"
ET_PROPERTY_PURCHASE    = "property_purchase"
ET_INHERITANCE          = "inheritance"
ET_LUMP_SUM_INCOME      = "lump_sum_income"
ET_MAJOR_EXPENSE        = "major_expense"
ET_JOB_CHANGE           = "job_change"
ET_CAREER_BREAK         = "career_break"
ET_EMIGRATION           = "emigration"
ET_CARE_COST_START      = "care_cost_start"
ET_CARE_COST_END        = "care_cost_end"
ET_STATE_PENSION_START  = "state_pension_start"
ET_PARTNER_DEATH        = "partner_death"
ET_BUSINESS_START       = "business_start"
ET_REDUNDANCY           = "redundancy"
ET_ASSET_CONTRIBUTION   = "asset_contribution"

SUPPORTED_EVENT_TYPES: frozenset[str] = frozenset({
    ET_PROPERTY_SALE, ET_PROPERTY_PURCHASE, ET_INHERITANCE,
    ET_LUMP_SUM_INCOME, ET_MAJOR_EXPENSE, ET_JOB_CHANGE,
    ET_CAREER_BREAK, ET_EMIGRATION, ET_CARE_COST_START,
    ET_CARE_COST_END, ET_STATE_PENSION_START, ET_PARTNER_DEATH,
    ET_BUSINESS_START, ET_REDUNDANCY, ET_ASSET_CONTRIBUTION,
})


# ---------------------------------------------------------------------------
# Config dataclasses (mirror YAML schema)
# ---------------------------------------------------------------------------


@dataclass
class IncomeSourceSpec:
    """
    @brief Inline specification for a new income source created by an event.

    @param source_id          Unique identifier for the new income source.
    @param name               Display name.
    @param person_id          FK to the person this income belongs to.
    @param gross_annual       Gross annual amount in base currency.
    @param currency           ISO 4217 code.
    @param tax_treatment      'PAYE' | 'self_employed' | 'state_pension' | 'other'.
    @param start_date         When the income starts.
    @param end_date           When the income ends (None = indefinite).
    @param annual_growth_rate Annual growth rate as a decimal (0.03 = 3 %).
    """
    source_id: str
    name: str
    person_id: str
    gross_annual: float
    currency: str = "GBP"
    tax_treatment: str = "PAYE"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    annual_growth_rate: float = 0.0


@dataclass
class ExpenseBucketSpec:
    """
    @brief Inline specification for an expense bucket created by an event.

    @param bucket_id        Unique identifier.
    @param name             Display name.
    @param annual_amount    Annual cost in base currency.
    @param currency         ISO 4217 code.
    @param inflation_linked True to inflate each year.
    @param inflation_rate   Override inflation rate (uses config default if 0).
    @param applies_to       List of person_ids this applies to.
    @param start_date       Start date.
    @param end_date         End date (None = indefinite).
    """
    bucket_id: str
    name: str
    annual_amount: float
    currency: str = "GBP"
    inflation_linked: bool = True
    inflation_rate: float = 0.0
    applies_to: list[str] = field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


@dataclass
class LifeEventConfig:
    """
    @brief Configuration for a single life event, loaded from YAML.

    @param event_id                 Unique identifier string.
    @param label                    Human-readable display label.
    @param event_type               One of SUPPORTED_EVENT_TYPES.
    @param year                     Calendar year the event fires.
    @param enabled                  False to suppress without deleting the config.
    @param probability              Probability weight 0–1 (1.0 = certain).
                                    Used for expected-value scaling.
    @param currency                 ISO 4217 code for monetary amounts.

    --- property_sale / property_purchase ---
    @param property_id              FK to the property in the main config.
    @param expected_proceeds        Gross proceeds from the sale.
    @param stamp_duty               Stamp duty / SDLT on purchase.
    @param deposit_amount           Deposit paid on purchase.
    @param purchase_price           Total purchase price.
    @param cgt_exempt               True if CGT is exempt (e.g. PPR relief).
    @param cgt_cost_basis           Original purchase price for CGT calculation.
    @param mortgage_outstanding     Balance to repay on sale (reduces net proceeds).
    @param target_account_id        Account to deposit net proceeds into.

    --- inheritance / lump_sum_income / major_expense / redundancy ---
    @param amount                   Monetary amount.
    @param is_taxable               True if the amount is subject to income tax.
    @param source_account_id        Account to withdraw from (expenses).
    @param target_account_id        Account to deposit into (income events).

    --- job_change / business_start ---
    @param remove_income_id         Income source to remove.
    @param add_income               IncomeSourceSpec for the new income.

    --- career_break ---
    @param remove_income_id         Income source to suspend.
    @param duration_years           Number of years the break lasts.
    @param resume_gross_annual      Salary on return (None = same as before).

    --- emigration ---
    @param new_jurisdiction         New tax jurisdiction string.

    --- care_cost_start ---
    @param expense_spec             ExpenseBucketSpec for the care cost.

    --- care_cost_end ---
    @param remove_expense_id        Expense bucket ID to remove.

    --- state_pension_start ---
    @param person_id                Person whose state pension starts.
    @param annual_amount            Annual state pension amount.
    @param deferral_weeks           Weeks deferred (increases amount).

    --- partner_death ---
    @param partner_id               ID of the deceased partner.
    @param remove_income_ids        Income source IDs to remove.
    @param expense_reduction_rate   Fraction by which to reduce household expenses.
    @param inherited_accounts       List of account IDs transferred to survivor.

    --- asset_contribution ---
    @param target_account_id        Account to deposit into.
    @param amount                   Lump sum deposit amount.

    --- shared ---
    @param notes                    Free-text notes.
    """

    event_id: str
    label: str
    event_type: str
    year: int
    enabled: bool = True
    probability: float = 1.0
    currency: str = "GBP"

    # property
    property_id: Optional[str] = None
    expected_proceeds: float = 0.0
    stamp_duty: float = 0.0
    deposit_amount: float = 0.0
    purchase_price: float = 0.0
    cgt_exempt: bool = False
    cgt_cost_basis: float = 0.0
    mortgage_outstanding: float = 0.0
    target_account_id: Optional[str] = None

    # monetary events
    amount: float = 0.0
    is_taxable: bool = False
    source_account_id: Optional[str] = None

    # income changes
    remove_income_id: Optional[str] = None
    add_income: Optional[IncomeSourceSpec] = None
    duration_years: int = 0
    resume_gross_annual: Optional[float] = None

    # emigration
    new_jurisdiction: Optional[str] = None

    # care costs
    expense_spec: Optional[ExpenseBucketSpec] = None

    # care cost removal
    remove_expense_id: Optional[str] = None

    # state pension
    person_id: Optional[str] = None
    annual_amount: float = 0.0
    deferral_weeks: int = 0

    # partner death
    partner_id: Optional[str] = None
    remove_income_ids: list[str] = field(default_factory=list)
    expense_reduction_rate: float = 0.0
    inherited_accounts: list[str] = field(default_factory=list)

    notes: str = ""


# ---------------------------------------------------------------------------
# Mutation dataclass (output consumed by calculator.py)
# ---------------------------------------------------------------------------


@dataclass
class AccountChange:
    """
    @brief A deposit or withdrawal applied to a specific account.

    @param account_id   Target account identifier.
    @param delta        Positive = deposit, negative = withdrawal.
    @param label        Human-readable reason.
    """
    account_id: str
    delta: float
    label: str = ""


@dataclass
class CGTDisposalEvent:
    """
    @brief A CGT disposal triggered by a life event.

    Passed to the tax_wrappers CGTTracker for annual CGT computation.

    @param account_id   Account in which the disposal occurs.
    @param asset_id     Asset identifier.
    @param proceeds     Gross disposal proceeds.
    @param cost_basis   Original acquisition cost.
    @param exempt       True if CGT is exempt (PPR, ISA, etc.).
    @param label        Human-readable description.
    """
    account_id: str
    asset_id: str
    proceeds: float
    cost_basis: float
    exempt: bool = False
    label: str = ""

    @property
    def gain(self) -> float:
        """@brief Net gain (proceeds minus cost basis)."""
        return self.proceeds - self.cost_basis


@dataclass
class EventMutation:
    """
    @brief Structured set of projection-state changes produced by one life event.

    The projection engine applies this at the relevant year without needing
    to understand the event's internal logic.

    @param year                  Calendar year the mutation applies.
    @param event_id              Source event identifier.
    @param event_type            Source event type string.
    @param label                 Display label.
    @param probability           Effective probability (may be < 1.0).
    @param net_cash_generated    Net cash flow (positive = inflow to model).
    @param account_changes       List of AccountChange objects.
    @param cgt_disposals         List of CGTDisposalEvent objects.
    @param income_source_adds    New IncomeSourceSpec objects to inject.
    @param income_source_removes Source IDs to deactivate.
    @param expense_adds          New ExpenseBucketSpec objects to inject.
    @param expense_removes       Expense bucket IDs to remove.
    @param jurisdiction_change   New jurisdiction string if emigrating.
    @param is_taxable_income     True if net_cash_generated is subject to income tax.
    @param description           Human-readable summary.
    @param warnings              List of warning strings.
    """

    year: int
    event_id: str
    event_type: str
    label: str
    probability: float = 1.0
    net_cash_generated: float = 0.0
    account_changes: list[AccountChange] = field(default_factory=list)
    cgt_disposals: list[CGTDisposalEvent] = field(default_factory=list)
    income_source_adds: list[IncomeSourceSpec] = field(default_factory=list)
    income_source_removes: list[str] = field(default_factory=list)
    expense_adds: list[ExpenseBucketSpec] = field(default_factory=list)
    expense_removes: list[str] = field(default_factory=list)
    jurisdiction_change: Optional[str] = None
    is_taxable_income: bool = False
    description: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class EventsEngine:
    """
    @brief Life events processing engine.

    Holds a list of LifeEventConfig objects and produces EventMutation
    objects for each calendar year of the projection.

    Usage::

        engine = EventsEngine(events, apply_probability_scaling=False)
        for year in range(2025, 2075):
            for mutation in engine.mutations_for_year(year):
                projection.apply_mutation(mutation)
    """

    def __init__(
        self,
        events: list[LifeEventConfig],
        apply_probability_scaling: bool = False,
        base_inflation_rate: float = 0.025,
    ) -> None:
        """
        @brief Initialise the engine.

        @param events                    List of LifeEventConfig objects.
        @param apply_probability_scaling If True, scale monetary amounts by
                                         event probability (for expected-value
                                         projections).  If False, events either
                                         fire (probability=1) or use full amounts
                                         with a warning label.
        @param base_inflation_rate       Default inflation rate for expense specs
                                         that don't specify their own.
        @raises ValueError               If any event fails validation.
        """
        self._events = [e for e in events if e.enabled]
        self._apply_prob_scaling = apply_probability_scaling
        self._base_inflation = base_inflation_rate
        self._validate_all()
        # Track career break re-entries: event_id -> resume_year
        self._career_break_resumes: dict[str, int] = {}
        logger.info(
            "EventsEngine initialised: %d events (%d enabled)",
            len(events),
            len(self._events),
        )

    def mutations_for_year(self, year: int) -> list[EventMutation]:
        """
        @brief Return all EventMutation objects that fire in a given year.

        Also handles career break resumes (re-injection of income source
        at the end of a career break period).

        @param year  Calendar year to process.
        @return      List of EventMutation objects (may be empty).
        """
        mutations: list[EventMutation] = []

        for evt in self._events:
            if evt.year != year:
                continue
            try:
                mutation = self._process_event(evt)
                if mutation is not None:
                    mutations.append(mutation)
                    logger.debug(
                        "Year %d: fired event '%s' (%s)",
                        year, evt.event_id, evt.event_type,
                    )
            except Exception as exc:
                logger.error(
                    "Year %d: error processing event '%s': %s",
                    year, evt.event_id, exc, exc_info=True,
                )

        # Career break resumes
        for evt_id, resume_year in list(self._career_break_resumes.items()):
            if resume_year == year:
                src_evt = next((e for e in self._events if e.event_id == evt_id), None)
                if src_evt and src_evt.add_income:
                    spec = src_evt.add_income
                    if src_evt.resume_gross_annual:
                        spec = IncomeSourceSpec(
                            source_id=spec.source_id,
                            name=spec.name + " (return)",
                            person_id=spec.person_id,
                            gross_annual=src_evt.resume_gross_annual,
                            currency=spec.currency,
                            tax_treatment=spec.tax_treatment,
                            start_date=date(year, 1, 1),
                            end_date=spec.end_date,
                            annual_growth_rate=spec.annual_growth_rate,
                        )
                    mutations.append(EventMutation(
                        year=year,
                        event_id=f"{evt_id}_resume",
                        event_type=ET_JOB_CHANGE,
                        label=f"Return from career break: {src_evt.label}",
                        income_source_adds=[spec],
                        description=f"Income resumed after career break ({src_evt.duration_years} yr).",
                    ))
                    del self._career_break_resumes[evt_id]
                    logger.info("Year %d: career break resume for event '%s'", year, evt_id)

        return mutations

    def all_mutations(self, start_year: int, end_year: int) -> dict[int, list[EventMutation]]:
        """
        @brief Return all mutations indexed by year for a projection range.

        @param start_year  First year to process (inclusive).
        @param end_year    Last year to process (inclusive).
        @return            Dict mapping year -> list[EventMutation].
        """
        result: dict[int, list[EventMutation]] = {}
        for year in range(start_year, end_year + 1):
            muts = self.mutations_for_year(year)
            if muts:
                result[year] = muts
        return result

    # ------------------------------------------------------------------
    # Private — event processors
    # ------------------------------------------------------------------

    def _process_event(self, evt: LifeEventConfig) -> Optional[EventMutation]:
        """
        @brief Dispatch an event to its specific processor.

        @param evt  LifeEventConfig to process.
        @return     EventMutation or None.
        """
        dispatch = {
            ET_PROPERTY_SALE:       self._process_property_sale,
            ET_PROPERTY_PURCHASE:   self._process_property_purchase,
            ET_INHERITANCE:         self._process_inheritance,
            ET_LUMP_SUM_INCOME:     self._process_lump_sum_income,
            ET_MAJOR_EXPENSE:       self._process_major_expense,
            ET_JOB_CHANGE:          self._process_job_change,
            ET_CAREER_BREAK:        self._process_career_break,
            ET_EMIGRATION:          self._process_emigration,
            ET_CARE_COST_START:     self._process_care_cost_start,
            ET_CARE_COST_END:       self._process_care_cost_end,
            ET_STATE_PENSION_START: self._process_state_pension_start,
            ET_PARTNER_DEATH:       self._process_partner_death,
            ET_BUSINESS_START:      self._process_business_start,
            ET_REDUNDANCY:          self._process_redundancy,
            ET_ASSET_CONTRIBUTION:  self._process_asset_contribution,
        }
        fn = dispatch.get(evt.event_type)
        if fn is None:
            logger.warning("Unknown event type '%s' for event '%s'", evt.event_type, evt.event_id)
            return None
        return fn(evt)

    def _scale(self, amount: float, probability: float) -> float:
        """
        @brief Apply probability scaling if configured.

        @param amount      Nominal monetary amount.
        @param probability Event probability (0–1).
        @return            Scaled amount.
        """
        if self._apply_prob_scaling and probability < 1.0:
            return amount * probability
        return amount

    def _base_mutation(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Create a blank EventMutation pre-populated with event metadata.

        @param evt  Source event config.
        @return     Blank EventMutation.
        """
        return EventMutation(
            year=evt.year,
            event_id=evt.event_id,
            event_type=evt.event_type,
            label=evt.label,
            probability=evt.probability,
        )

    def _process_property_sale(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a property_sale event.

        Net proceeds = expected_proceeds - mortgage_outstanding.
        Optionally creates a CGTDisposalEvent if not cgt_exempt.

        @param evt  LifeEventConfig with property sale parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        proceeds = self._scale(evt.expected_proceeds, evt.probability)
        net_proceeds = max(0.0, proceeds - evt.mortgage_outstanding)
        m.net_cash_generated = net_proceeds
        m.description = (
            f"Property sale '{evt.property_id}': proceeds £{proceeds:,.0f}, "
            f"mortgage repaid £{evt.mortgage_outstanding:,.0f}, "
            f"net £{net_proceeds:,.0f}."
        )
        if evt.target_account_id:
            m.account_changes.append(AccountChange(
                account_id=evt.target_account_id,
                delta=net_proceeds,
                label=f"Property sale proceeds: {evt.label}",
            ))
        if not evt.cgt_exempt and evt.cgt_cost_basis > 0:
            m.cgt_disposals.append(CGTDisposalEvent(
                account_id=evt.target_account_id or "unallocated",
                asset_id=evt.property_id or evt.event_id,
                proceeds=proceeds,
                cost_basis=evt.cgt_cost_basis,
                exempt=False,
                label=f"Property sale: {evt.label}",
            ))
        elif evt.cgt_exempt:
            m.description += " CGT exempt (PPR relief or other)."
        logger.info(
            "property_sale '%s' year=%d net_proceeds=%.2f",
            evt.event_id, evt.year, net_proceeds,
        )
        return m

    def _process_property_purchase(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a property_purchase event.

        Deducts deposit + stamp duty from source account.

        @param evt  LifeEventConfig with purchase parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        total_outflow = evt.deposit_amount + evt.stamp_duty
        m.net_cash_generated = -total_outflow
        m.description = (
            f"Property purchase '{evt.property_id}': deposit £{evt.deposit_amount:,.0f}, "
            f"stamp duty £{evt.stamp_duty:,.0f}, total outflow £{total_outflow:,.0f}."
        )
        if evt.source_account_id:
            m.account_changes.append(AccountChange(
                account_id=evt.source_account_id,
                delta=-total_outflow,
                label=f"Property purchase deposit + SDLT: {evt.label}",
            ))
        logger.info(
            "property_purchase '%s' year=%d outflow=%.2f",
            evt.event_id, evt.year, total_outflow,
        )
        return m

    def _process_inheritance(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process an inheritance event.

        Amount may be probability-scaled.  Deposited into target_account_id.

        @param evt  LifeEventConfig with inheritance parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        amount = self._scale(evt.amount, evt.probability)
        m.net_cash_generated = amount
        m.is_taxable_income = evt.is_taxable
        m.description = f"Inheritance received: £{amount:,.0f} (p={evt.probability:.0%})."
        if evt.probability < 1.0 and not self._apply_prob_scaling:
            m.warnings.append(
                f"Inheritance '{evt.event_id}' has probability {evt.probability:.0%}. "
                f"Full amount modelled; consider a scenario for the 0% case."
            )
        if evt.target_account_id:
            m.account_changes.append(AccountChange(
                account_id=evt.target_account_id,
                delta=amount,
                label=f"Inheritance: {evt.label}",
            ))
        logger.info("inheritance '%s' year=%d amount=%.2f", evt.event_id, evt.year, amount)
        return m

    def _process_lump_sum_income(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a lump_sum_income event (bonus, windfall, compensation).

        @param evt  LifeEventConfig.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        amount = self._scale(evt.amount, evt.probability)
        m.net_cash_generated = amount
        m.is_taxable_income = evt.is_taxable
        m.description = f"Lump sum income '{evt.label}': £{amount:,.0f}."
        if evt.target_account_id:
            m.account_changes.append(AccountChange(
                account_id=evt.target_account_id,
                delta=amount,
                label=f"Lump sum income: {evt.label}",
            ))
        logger.info("lump_sum_income '%s' year=%d amount=%.2f", evt.event_id, evt.year, amount)
        return m

    def _process_major_expense(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a major_expense event (car, wedding, renovation).

        @param evt  LifeEventConfig.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        amount = self._scale(evt.amount, evt.probability)
        m.net_cash_generated = -amount
        m.description = f"Major expense '{evt.label}': £{amount:,.0f}."
        if evt.source_account_id:
            m.account_changes.append(AccountChange(
                account_id=evt.source_account_id,
                delta=-amount,
                label=f"Major expense: {evt.label}",
            ))
        logger.info("major_expense '%s' year=%d amount=%.2f", evt.event_id, evt.year, amount)
        return m

    def _process_job_change(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a job_change event.

        Removes old income source and optionally adds a new one.

        @param evt  LifeEventConfig with job change parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        if evt.remove_income_id:
            m.income_source_removes.append(evt.remove_income_id)
        if evt.add_income:
            m.income_source_adds.append(evt.add_income)
        m.description = (
            f"Job change '{evt.label}': "
            f"removed '{evt.remove_income_id or 'n/a'}', "
            f"added '{evt.add_income.source_id if evt.add_income else 'n/a'}'."
        )
        logger.info("job_change '%s' year=%d", evt.event_id, evt.year)
        return m

    def _process_career_break(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a career_break event.

        Suspends the income source for duration_years.  Registers a resume
        in self._career_break_resumes so mutations_for_year() re-injects it.

        @param evt  LifeEventConfig with career break parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        if evt.remove_income_id:
            m.income_source_removes.append(evt.remove_income_id)
        resume_year = evt.year + evt.duration_years
        if evt.duration_years > 0:
            self._career_break_resumes[evt.event_id] = resume_year
        m.description = (
            f"Career break '{evt.label}': '{evt.remove_income_id}' suspended "
            f"for {evt.duration_years} yr(s); resumes {resume_year}."
        )
        logger.info(
            "career_break '%s' year=%d duration=%d resume=%d",
            evt.event_id, evt.year, evt.duration_years, resume_year,
        )
        return m

    def _process_emigration(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process an emigration event.

        Sets a new tax jurisdiction from this year.

        @param evt  LifeEventConfig with emigration parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        m.jurisdiction_change = evt.new_jurisdiction
        m.description = f"Emigration '{evt.label}': jurisdiction → '{evt.new_jurisdiction}'."
        if not evt.new_jurisdiction:
            m.warnings.append(f"emigration event '{evt.event_id}' has no new_jurisdiction set.")
        logger.info(
            "emigration '%s' year=%d new_jurisdiction='%s'",
            evt.event_id, evt.year, evt.new_jurisdiction,
        )
        return m

    def _process_care_cost_start(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a care_cost_start event.

        Injects a new expense bucket for ongoing care costs.

        @param evt  LifeEventConfig with care cost parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        if evt.expense_spec is None:
            m.warnings.append(
                f"care_cost_start '{evt.event_id}' has no expense_spec — no expense added."
            )
            return m
        spec = evt.expense_spec
        if spec.inflation_rate == 0.0:
            spec.inflation_rate = self._base_inflation
        m.expense_adds.append(spec)
        m.description = (
            f"Care costs start '{evt.label}': £{spec.annual_amount:,.0f}/yr "
            f"({'inflation-linked' if spec.inflation_linked else 'fixed'})."
        )
        logger.info(
            "care_cost_start '%s' year=%d annual=%.2f",
            evt.event_id, evt.year, spec.annual_amount,
        )
        return m

    def _process_care_cost_end(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a care_cost_end event.

        Removes a previously-injected care cost expense bucket.

        @param evt  LifeEventConfig.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        if evt.remove_expense_id:
            m.expense_removes.append(evt.remove_expense_id)
        m.description = f"Care cost bucket '{evt.remove_expense_id}' removed."
        logger.info("care_cost_end '%s' year=%d", evt.event_id, evt.year)
        return m

    def _process_state_pension_start(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a state_pension_start event.

        Injects a new state pension income source.

        @param evt  LifeEventConfig with state pension parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        deferral_bonus = evt.deferral_weeks * (0.01 / 9.0)
        adjusted_amount = round(evt.annual_amount * (1 + deferral_bonus), 2)
        spec = IncomeSourceSpec(
            source_id=f"state_pension_{evt.person_id or evt.event_id}",
            name=f"State Pension ({evt.person_id or 'unknown'})",
            person_id=evt.person_id or "",
            gross_annual=adjusted_amount,
            currency=evt.currency,
            tax_treatment="state_pension",
            start_date=date(evt.year, 1, 1),
        )
        m.income_source_adds.append(spec)
        m.description = (
            f"State pension starts for '{evt.person_id}': £{adjusted_amount:,.2f}/yr "
            f"(deferral bonus {deferral_bonus:.1%})."
        )
        logger.info(
            "state_pension_start '%s' year=%d amount=%.2f",
            evt.event_id, evt.year, adjusted_amount,
        )
        return m

    def _process_partner_death(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a partner_death event.

        Removes partner income sources and records inherited accounts.

        @param evt  LifeEventConfig with partner death parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        m.income_source_removes.extend(evt.remove_income_ids)
        m.description = (
            f"Partner death '{evt.partner_id}': removed income sources "
            f"{evt.remove_income_ids}."
        )
        if evt.expense_reduction_rate > 0:
            m.warnings.append(
                f"partner_death '{evt.event_id}': expense reduction "
                f"{evt.expense_reduction_rate:.0%} must be applied manually "
                f"in the expense config or via a scenario diff."
            )
        if evt.inherited_accounts:
            m.description += f" Inherited accounts: {evt.inherited_accounts}."
        logger.info(
            "partner_death '%s' year=%d partner='%s'",
            evt.event_id, evt.year, evt.partner_id,
        )
        return m

    def _process_business_start(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a business_start event.

        Adds a self-employed income source.

        @param evt  LifeEventConfig with business start parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        if evt.add_income:
            m.income_source_adds.append(evt.add_income)
        m.description = f"Business start '{evt.label}': income added."
        logger.info("business_start '%s' year=%d", evt.event_id, evt.year)
        return m

    def _process_redundancy(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process a redundancy event.

        Removes income source and optionally pays a lump sum redundancy payment.

        @param evt  LifeEventConfig with redundancy parameters.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        if evt.remove_income_id:
            m.income_source_removes.append(evt.remove_income_id)
        if evt.amount > 0:
            # UK: first £30k redundancy is tax-free
            taxable_threshold = 30_000.0
            taxable = max(0.0, evt.amount - taxable_threshold)
            m.net_cash_generated = evt.amount
            m.is_taxable_income = taxable > 0
            if evt.target_account_id:
                m.account_changes.append(AccountChange(
                    account_id=evt.target_account_id,
                    delta=evt.amount,
                    label=f"Redundancy payment: {evt.label}",
                ))
            if taxable > 0:
                m.warnings.append(
                    f"Redundancy payment £{evt.amount:,.0f}: £{taxable_threshold:,.0f} "
                    f"tax-free, £{taxable:,.0f} taxable. Apply via tax engine."
                )
        m.description = f"Redundancy '{evt.label}': income removed, payment £{evt.amount:,.0f}."
        logger.info(
            "redundancy '%s' year=%d amount=%.2f", evt.event_id, evt.year, evt.amount
        )
        return m

    def _process_asset_contribution(self, evt: LifeEventConfig) -> EventMutation:
        """
        @brief Process an asset_contribution event (lump sum into an account).

        @param evt  LifeEventConfig.
        @return     EventMutation.
        """
        m = self._base_mutation(evt)
        amount = self._scale(evt.amount, evt.probability)
        m.net_cash_generated = 0.0   # internal reallocation — no net change
        if evt.target_account_id:
            m.account_changes.append(AccountChange(
                account_id=evt.target_account_id,
                delta=amount,
                label=f"Asset contribution: {evt.label}",
            ))
        m.description = f"Asset contribution '{evt.label}': £{amount:,.0f} → {evt.target_account_id}."
        logger.info(
            "asset_contribution '%s' year=%d amount=%.2f", evt.event_id, evt.year, amount
        )
        return m

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_all(self) -> None:
        """
        @brief Validate all enabled events on init and log any issues.

        Does not raise — logs warnings for non-critical issues and errors
        for critical ones so the engine can still run with partial config.
        """
        ids_seen: set[str] = set()
        for evt in self._events:
            if evt.event_id in ids_seen:
                logger.error(
                    "Duplicate event_id '%s' — only first occurrence will fire.", evt.event_id
                )
            ids_seen.add(evt.event_id)

            if evt.event_type not in SUPPORTED_EVENT_TYPES:
                logger.error(
                    "Event '%s' has unsupported type '%s'.", evt.event_id, evt.event_type
                )
            if not (0.0 <= evt.probability <= 1.0):
                logger.warning(
                    "Event '%s' probability %.2f is outside [0, 1].",
                    evt.event_id, evt.probability,
                )
            if evt.year < 2000 or evt.year > 2200:
                logger.warning(
                    "Event '%s' year %d looks unreasonable.", evt.event_id, evt.year
                )


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def _parse_date(value) -> Optional[date]:
    """
    @brief Coerce a YAML value to a Python date or return None.

    @param value  Raw YAML value.
    @return       Python date or None.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_income_source_spec(raw: dict) -> Optional[IncomeSourceSpec]:
    """
    @brief Parse an inline income source spec from a raw YAML dict.

    @param raw  Dict from YAML.
    @return     IncomeSourceSpec or None if missing required fields.
    """
    if not raw or "source_id" not in raw:
        return None
    return IncomeSourceSpec(
        source_id=str(raw["source_id"]),
        name=str(raw.get("name", raw["source_id"])),
        person_id=str(raw.get("person_id", "")),
        gross_annual=float(raw.get("gross_annual", 0)),
        currency=str(raw.get("currency", "GBP")),
        tax_treatment=str(raw.get("tax_treatment", "PAYE")),
        start_date=_parse_date(raw.get("start_date")),
        end_date=_parse_date(raw.get("end_date")),
        annual_growth_rate=float(raw.get("annual_growth_rate", 0)),
    )


def _parse_expense_spec(raw: dict) -> Optional[ExpenseBucketSpec]:
    """
    @brief Parse an inline expense bucket spec from a raw YAML dict.

    @param raw  Dict from YAML.
    @return     ExpenseBucketSpec or None.
    """
    if not raw or "bucket_id" not in raw:
        return None
    return ExpenseBucketSpec(
        bucket_id=str(raw["bucket_id"]),
        name=str(raw.get("name", raw["bucket_id"])),
        annual_amount=float(raw.get("annual_amount", 0)),
        currency=str(raw.get("currency", "GBP")),
        inflation_linked=bool(raw.get("inflation_linked", True)),
        inflation_rate=float(raw.get("inflation_rate", 0)),
        applies_to=list(raw.get("applies_to", [])),
        start_date=_parse_date(raw.get("start_date")),
        end_date=_parse_date(raw.get("end_date")),
    )


def load_events_from_yaml(path: str) -> list[LifeEventConfig]:
    """
    @brief Load a list of LifeEventConfig objects from a YAML file.

    Expected top-level key: ``events`` (a list).

    @param path  Filesystem path to the YAML file.
    @return      List of LifeEventConfig objects.
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file is not valid YAML.
    @raises ValueError         If the top-level structure is wrong.
    """
    logger.info("Loading events from: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Events config not found: %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise

    if not isinstance(raw, dict) or "events" not in raw:
        raise ValueError(f"YAML file '{path}' must have a top-level 'events' list key.")

    events: list[LifeEventConfig] = []
    for item in raw["events"]:
        try:
            add_income_raw = item.get("add_income")
            expense_spec_raw = item.get("expense_spec")
            evt = LifeEventConfig(
                event_id=str(item["event_id"]),
                label=str(item.get("label", item["event_id"])),
                event_type=str(item["event_type"]),
                year=int(item["year"]),
                enabled=bool(item.get("enabled", True)),
                probability=float(item.get("probability", 1.0)),
                currency=str(item.get("currency", "GBP")),
                property_id=item.get("property_id"),
                expected_proceeds=float(item.get("expected_proceeds", 0)),
                stamp_duty=float(item.get("stamp_duty", 0)),
                deposit_amount=float(item.get("deposit_amount", 0)),
                purchase_price=float(item.get("purchase_price", 0)),
                cgt_exempt=bool(item.get("cgt_exempt", False)),
                cgt_cost_basis=float(item.get("cgt_cost_basis", 0)),
                mortgage_outstanding=float(item.get("mortgage_outstanding", 0)),
                target_account_id=item.get("target_account_id"),
                amount=float(item.get("amount", 0)),
                is_taxable=bool(item.get("is_taxable", False)),
                source_account_id=item.get("source_account_id"),
                remove_income_id=item.get("remove_income_id"),
                add_income=_parse_income_source_spec(add_income_raw) if add_income_raw else None,
                duration_years=int(item.get("duration_years", 0)),
                resume_gross_annual=float(item["resume_gross_annual"]) if item.get("resume_gross_annual") else None,
                new_jurisdiction=item.get("new_jurisdiction"),
                expense_spec=_parse_expense_spec(expense_spec_raw) if expense_spec_raw else None,
                remove_expense_id=item.get("remove_expense_id"),
                person_id=item.get("person_id"),
                annual_amount=float(item.get("annual_amount", 0)),
                deferral_weeks=int(item.get("deferral_weeks", 0)),
                partner_id=item.get("partner_id"),
                remove_income_ids=list(item.get("remove_income_ids", [])),
                expense_reduction_rate=float(item.get("expense_reduction_rate", 0)),
                inherited_accounts=list(item.get("inherited_accounts", [])),
                notes=str(item.get("notes", "")),
            )
            events.append(evt)
        except (KeyError, TypeError, ValueError) as exc:
            logger.error("Failed to parse event '%s': %s", item.get("event_id", "?"), exc)

    logger.info("Loaded %d events from %s", len(events), path)
    return events
