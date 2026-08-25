"""
@file planning_coach.py
@brief Phase 12 (partial) rule-based planning coach for LifeLedger.

Scans the scenario YAML and optional simulation result to produce a ranked
list of actionable alerts. Each alert has a priority, title, detail, and
optional action hint.

Rules implemented (10)
----------------------
1.  ISA season          — remaining ISA allowance before 5 April
2.  NI qualifying years — gap between current qualifying years and 35
3.  NI gap urgency      — Class 3 NI top-up deadline for recent gap years
4.  Emergency fund      — months of expenses covered by liquid savings
5.  Pension allowance   — remaining annual pension allowance (£60k)
6.  FIRE tracking       — current NW as % of target; years ahead/behind
7.  IHT alert           — estimated IHT liability and quick-wins
8.  Mortgage rate fix   — months until current fixed rate expires
9.  Tax year deadline   — days until 5 April (ISA + pension contributions)
10. PCLS reminder       — uncrystallised pension with no drawdown config

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("lifeledger.planning_coach")


# ─────────────────────────────────────────────────────────────────────────────
# Alert dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CoachAlert:
    """
    @brief One planning coach alert.

    @param rule_id    Unique rule identifier (e.g. 'isa_season').
    @param priority   'HIGH' | 'MEDIUM' | 'LOW'.
    @param title      Short headline (< 60 chars).
    @param detail     Full explanation with figures (1–3 sentences).
    @param action     Optional recommended next step.
    @param amount_gbp Optional monetary amount relevant to the alert.
    @param days_left  Optional days until a deadline.
    @param colour     Hex colour for the UI badge.
    @param icon       Emoji icon for the alert card.
    """
    rule_id: str
    priority: str
    title: str
    detail: str
    action: str = ""
    amount_gbp: Optional[float] = None
    days_left: Optional[int] = None
    colour: str = "#f0a500"
    icon: str = "💡"


@dataclass
class CoachResult:
    """
    @brief Full planning coach output.

    @param alerts           List of CoachAlert, sorted HIGH → MEDIUM → LOW.
    @param total_high       Number of HIGH priority alerts.
    @param total_medium     Number of MEDIUM priority alerts.
    @param total_low        Number of LOW priority alerts.
    @param scenario_year    Calendar year used for evaluation.
    @param warnings         Engine warning messages.
    """
    alerts: list[CoachAlert]
    total_high: int
    total_medium: int
    total_low: int
    scenario_year: int
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────

_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

_ISA_ANNUAL_LIMIT    = 20_000.0
_PENSION_AA          = 60_000.0   # 2024/25 annual allowance
_FULL_NI_YEARS       = 35
_NI_WEEKLY_FULL      = 221.20
_STATE_PENSION_AGE   = 67
_NI_CLASS3_WEEKLY    = 17.45      # 2024/25 Class 3 weekly NI rate
_EMERGENCY_MONTHS_TARGET = 6
_IHT_RATE            = 0.40
_NRB                 = 325_000.0
_RNRB                = 175_000.0


def _tax_year_end(today: date) -> date:
    """@brief Return the next 5 April after today."""
    ty_end = date(today.year, 4, 5)
    if today > ty_end:
        ty_end = date(today.year + 1, 4, 5)
    return ty_end


def _days_to_tax_year_end(today: date) -> int:
    """@brief Days until the next 5 April."""
    return (_tax_year_end(today) - today).days


class PlanningCoachEngine:
    """
    @brief Evaluates scenario data against 10 financial planning rules.

    Instantiate once; call run() with the raw scenario dict and optional
    simulation data.
    """

    def run(
        self,
        scenario: dict,
        current_net_worth: Optional[float] = None,
        fire_target: Optional[float] = None,
        fire_year_projected: Optional[int] = None,
        today: Optional[date] = None,
    ) -> CoachResult:
        """
        @brief Evaluate all 10 rules and return ranked alerts.

        @param scenario              Raw scenario YAML dict (top-level 'scenario' or root).
        @param current_net_worth     Current total net worth from latest simulation.
        @param fire_target           FIRE target net worth from scenario config.
        @param fire_year_projected   Projected FIRE year from latest simulation.
        @param today                 Reference date (default: date.today()).
        @return                      CoachResult.
        """
        today = today or date.today()
        sc    = scenario.get("scenario", scenario)
        warnings: list[str] = []
        alerts:   list[CoachAlert] = []

        people   = sc.get("people", [])
        primary  = people[0] if people else {}
        all_people = people

        income_sources  = sc.get("income_sources",  [])
        pensions        = sc.get("pension_funds",    [])
        savings         = sc.get("savings_accounts", [])
        investments     = sc.get("investment_accounts", [])
        expenses        = sc.get("expense_buckets",  [])
        mortgages       = sc.get("mortgages",        [])
        fire_cfg        = sc.get("fire_target",      {})

        # Derived values
        birth_year  = int(str(primary.get("date_of_birth", f"{today.year-40}-01-01"))[:4])
        retire_age  = int(primary.get("retirement_age", 60))
        retire_year = birth_year + retire_age
        current_age = today.year - birth_year

        annual_expenses = sum(
            float(e.get("annual_amount", 0))
            for e in expenses
            if e.get("end_date") is None
        )

        # ── Rule 1: ISA season ────────────────────────────────────────────────
        days_left = _days_to_tax_year_end(today)
        if days_left <= 90:
            # Estimate ISA contributions this tax year from routing rules
            isa_ids = {a.get("id", "") for a in investments
                       if "ISA" in str(a.get("account_type", "")).upper()}
            isa_ids |= {a.get("id", "") for a in savings
                        if "ISA" in str(a.get("account_type", "")).upper()}
            annual_isa_contrib = 0.0
            for isrc in income_sources:
                for contrib in isrc.get("contributions", []):
                    if contrib.get("destination_account_id") in isa_ids:
                        gross = float(isrc.get("gross_annual", 0))
                        rate  = float(contrib.get("rate", 0))
                        cap   = float(contrib.get("cap_annual", _ISA_ANNUAL_LIMIT))
                        annual_isa_contrib += min(gross * rate, cap)

            remaining = max(0.0, _ISA_ANNUAL_LIMIT - annual_isa_contrib)
            if remaining > 500:
                priority = "HIGH" if days_left <= 30 else "MEDIUM"
                alerts.append(CoachAlert(
                    rule_id="isa_season",
                    priority=priority,
                    title=f"£{remaining:,.0f} ISA allowance unused — {days_left} days left",
                    detail=(f"The £20,000 ISA allowance resets on 6 April. "
                            f"Estimated £{remaining:,.0f} of your allowance is unused "
                            f"this tax year. Unused allowance cannot be carried forward."),
                    action="Transfer cash to your Stocks & Shares ISA before 5 April.",
                    amount_gbp=remaining,
                    days_left=days_left,
                    colour="#2dbd7e" if days_left > 30 else "#e05252",
                    icon="💰",
                ))

        # ── Rule 2: NI qualifying years ───────────────────────────────────────
        for person in all_people:
            sp = person.get("state_pension", {})
            qualifying = int(sp.get("qualifying_years", 0))
            needed     = max(0, _FULL_NI_YEARS - qualifying)
            sp_age     = int(sp.get("expected_start_age", _STATE_PENSION_AGE))
            p_birth    = int(str(person.get("date_of_birth", f"{today.year-40}-01-01"))[:4])
            p_age      = today.year - p_birth
            years_to_sp = max(0, (p_birth + sp_age) - today.year)
            name       = person.get("name", "Person")

            if 0 < needed <= 10:
                weekly_loss = (_NI_WEEKLY_FULL * needed) / _FULL_NI_YEARS
                annual_loss = weekly_loss * 52
                alerts.append(CoachAlert(
                    rule_id=f"ni_gap_{person.get('id','p')}",
                    priority="MEDIUM",
                    title=f"{name}: {needed} NI year{'s' if needed > 1 else ''} short of full state pension",
                    detail=(f"{name} has {qualifying}/{_FULL_NI_YEARS} qualifying NI years. "
                            f"The shortfall costs ~£{annual_loss:,.0f}/yr in state pension "
                            f"(~£{annual_loss * 20:,.0f} over 20 years). "
                            f"Topping up {needed} year{'s' if needed > 1 else ''} costs "
                            f"~£{needed * _NI_CLASS3_WEEKLY * 52:,.0f}."),
                    action=f"Check for NI gaps at gov.uk/check-state-pension. "
                           f"{years_to_sp} years until state pension age.",
                    amount_gbp=annual_loss * 20,
                    colour="#f97316",
                    icon="🏛",
                ))
            elif needed > 10:
                alerts.append(CoachAlert(
                    rule_id=f"ni_gap_{person.get('id','p')}",
                    priority="LOW",
                    title=f"{name}: {needed} NI years needed for full state pension",
                    detail=(f"{name} has {qualifying}/{_FULL_NI_YEARS} qualifying NI years "
                            f"with {years_to_sp} years until state pension age. "
                            f"Continuing employment will fill the gap naturally."),
                    action="No immediate action needed — track annually.",
                    colour="#8b949e",
                    icon="🏛",
                ))

        # ── Rule 3: NI gap urgency (Class 3 deadline) ─────────────────────────
        # HMRC allows topping up NI gaps within the last 6 completed tax years.
        # Class 3 contributions must be paid before the 6-year window closes.
        for person in all_people:
            sp = person.get("state_pension", {})
            qualifying = int(sp.get("qualifying_years", 0))
            if qualifying < _FULL_NI_YEARS:
                # Oldest gap year still actionable
                oldest_gap_year = today.year - 7  # approximately 6 years back
                alerts.append(CoachAlert(
                    rule_id=f"ni_deadline_{person.get('id','p')}",
                    priority="LOW",
                    title=f"NI gaps from {oldest_gap_year} close in April {today.year + 1}",
                    detail=(f"HMRC allows topping up NI gaps from the last 6 completed tax "
                            f"years. The {oldest_gap_year}/{oldest_gap_year+1} gap year "
                            f"becomes ineligible for top-up after 5 April {today.year + 1}. "
                            f"Each missing year costs ~£{_NI_CLASS3_WEEKLY * 52:,.0f} to fill."),
                    action="Check gov.uk/pay-voluntary-class-3-national-insurance for current gaps.",
                    colour="#8b949e",
                    icon="⏰",
                ))
                break  # One reminder is enough

        # ── Rule 4: Emergency fund ────────────────────────────────────────────
        emergency_ids  = {"emergency_fund", "emergency", "current_account"}
        emergency_val  = sum(
            float(a.get("current_value", 0)) for a in savings
            if (a.get("account_type", "") in {"general", "savings"}
                or any(k in str(a.get("id","")).lower() for k in emergency_ids))
        )
        monthly_expenses = annual_expenses / 12 if annual_expenses > 0 else 3_000.0
        months_covered   = emergency_val / monthly_expenses if monthly_expenses > 0 else 0.0

        if months_covered < 3:
            alerts.append(CoachAlert(
                rule_id="emergency_fund",
                priority="HIGH",
                title=f"Emergency fund covers only {months_covered:.1f} months",
                detail=(f"Current liquid savings (£{emergency_val:,.0f}) cover "
                        f"{months_covered:.1f} months of expenses. The recommended minimum "
                        f"is 3 months (£{monthly_expenses*3:,.0f}); target is 6 months "
                        f"(£{monthly_expenses*6:,.0f})."),
                action=f"Build emergency fund to £{monthly_expenses*3:,.0f} (3-month minimum) "
                       f"before increasing ISA / pension contributions.",
                amount_gbp=monthly_expenses * 3 - emergency_val,
                colour="#e05252",
                icon="🛡",
            ))
        elif months_covered < _EMERGENCY_MONTHS_TARGET:
            alerts.append(CoachAlert(
                rule_id="emergency_fund",
                priority="MEDIUM",
                title=f"Emergency fund at {months_covered:.1f} months (target: 6)",
                detail=(f"Liquid savings (£{emergency_val:,.0f}) cover {months_covered:.1f} "
                        f"months. Target is {_EMERGENCY_MONTHS_TARGET} months "
                        f"(£{monthly_expenses * _EMERGENCY_MONTHS_TARGET:,.0f})."),
                action="Top up emergency fund to 6 months before ISA year end.",
                amount_gbp=monthly_expenses * _EMERGENCY_MONTHS_TARGET - emergency_val,
                colour="#f0a500",
                icon="🛡",
            ))

        # ── Rule 5: Pension annual allowance ──────────────────────────────────
        # Estimate pension contributions this tax year
        annual_pension_contrib = 0.0
        for isrc in income_sources:
            gross = float(isrc.get("gross_annual", 0))
            for contrib in isrc.get("contributions", []):
                dest = contrib.get("destination_account_id", "")
                if any(dest == p.get("id", "") for p in pensions):
                    rate      = float(contrib.get("rate", 0))
                    emp_match = float(contrib.get("employer_top_up", 0))
                    cap       = float(contrib.get("cap_annual", _PENSION_AA))
                    annual_pension_contrib += min(gross * (rate + emp_match), cap)

        remaining_aa = max(0.0, _PENSION_AA - annual_pension_contrib)
        if remaining_aa > 5_000 and days_left <= 90:
            alerts.append(CoachAlert(
                rule_id="pension_allowance",
                priority="MEDIUM",
                title=f"£{remaining_aa:,.0f} pension annual allowance unused",
                detail=(f"Estimated pension contributions this tax year: "
                        f"£{annual_pension_contrib:,.0f}. The £{_PENSION_AA:,.0f} "
                        f"annual allowance leaves £{remaining_aa:,.0f} unused. "
                        f"Unused allowance can be carried forward 3 years."),
                action=f"Consider a lump-sum SIPP contribution before 5 April "
                       f"({days_left} days). Tax relief at your marginal rate applies.",
                amount_gbp=remaining_aa,
                days_left=days_left,
                colour="#a78bfa",
                icon="🏦",
            ))

        # ── Rule 6: FIRE tracking ─────────────────────────────────────────────
        if current_net_worth is not None:
            target   = fire_target or float(fire_cfg.get("target_net_worth", 0))
            if target > 0:
                pct = current_net_worth / target * 100
                remaining_to_fire = max(0.0, target - current_net_worth)
                fire_proj = fire_year_projected

                if pct >= 100:
                    alerts.append(CoachAlert(
                        rule_id="fire_tracking",
                        priority="LOW",
                        title="🎉 FIRE target achieved",
                        detail=(f"Current net worth £{current_net_worth:,.0f} exceeds the "
                                f"£{target:,.0f} FIRE target ({pct:.0f}%). "
                                f"Ensure a sustainable drawdown strategy is in place."),
                        action="Review the Tax Optimiser for drawdown strategy.",
                        colour="#2dbd7e",
                        icon="🎉",
                    ))
                elif pct >= 75:
                    alerts.append(CoachAlert(
                        rule_id="fire_tracking",
                        priority="LOW",
                        title=f"FIRE {pct:.0f}% achieved — ~£{remaining_to_fire:,.0f} to go",
                        detail=(f"Net worth £{current_net_worth:,.0f} is {pct:.0f}% of the "
                                f"£{target:,.0f} FIRE target."
                                + (f" Projected FIRE year: {fire_proj}." if fire_proj else "")),
                        action="Stay the course. Consider increasing contributions to bring FIRE forward.",
                        colour="#2dbd7e",
                        icon="📈",
                    ))
                else:
                    alerts.append(CoachAlert(
                        rule_id="fire_tracking",
                        priority="LOW",
                        title=f"FIRE {pct:.0f}% achieved — £{remaining_to_fire:,.0f} remaining",
                        detail=(f"Net worth £{current_net_worth:,.0f} is {pct:.0f}% of the "
                                f"£{target:,.0f} FIRE target."
                                + (f" Projected FIRE year: {fire_proj}." if fire_proj else "")),
                        action="Run a simulation to see how contribution changes affect the FIRE date.",
                        colour="#0e9aad",
                        icon="🎯",
                    ))

        # ── Rule 7: IHT alert ─────────────────────────────────────────────────
        total_assets = sum(float(a.get("current_value", 0)) for a in (
            savings + investments + pensions
        ))
        properties = sc.get("properties", [])
        property_val = sum(float(p.get("current_value", 0)) for p in properties)
        mortgage_balance = sum(float(m.get("current_balance", 0)) for m in mortgages)
        net_property = max(0.0, property_val - mortgage_balance)

        # Pension is outside estate (pre-2027 rules)
        pension_val = sum(float(p.get("current_value", 0)) for p in pensions)
        estate = total_assets - pension_val + net_property

        couple = len(people) >= 2
        nrb_total  = _NRB  * (2 if couple else 1)
        rnrb_total = _RNRB * (2 if couple else 1)
        taxable_estate = max(0.0, estate - nrb_total - rnrb_total)
        iht_est = taxable_estate * _IHT_RATE

        if iht_est > 10_000:
            priority = "HIGH" if iht_est > 100_000 else "MEDIUM"
            alerts.append(CoachAlert(
                rule_id="iht_alert",
                priority=priority,
                title=f"Estimated IHT liability: £{iht_est:,.0f}",
                detail=(f"Gross estate ~£{estate:,.0f} (excl. pension). "
                        f"NRB+RNRB allowances: £{nrb_total+rnrb_total:,.0f}. "
                        f"Taxable estate: £{taxable_estate:,.0f} at 40% = £{iht_est:,.0f}. "
                        f"Pension (£{pension_val:,.0f}) is currently outside the estate."),
                action="Consider annual gift allowances (£3,000/yr per donor), "
                       "charitable giving (reduces rate to 36%), or trust structures. "
                       "See Estate Planner for detailed analysis.",
                amount_gbp=iht_est,
                colour="#e05252" if iht_est > 100_000 else "#f0a500",
                icon="🏛",
            ))

        # ── Rule 8: Mortgage fixed rate ending ────────────────────────────────
        for mort in mortgages:
            for period in mort.get("rate_periods", []):
                end_date_str = period.get("end_date")
                if end_date_str and period.get("rate_type") == "fixed":
                    try:
                        end_dt   = date.fromisoformat(str(end_date_str)[:10])
                        days_rem = (end_dt - today).days
                        if 0 < days_rem <= 180:
                            rate_pct = float(period.get("rate", 0)) * 100
                            alerts.append(CoachAlert(
                                rule_id=f"mortgage_fix_{mort.get('id','m')}",
                                priority="HIGH" if days_rem <= 60 else "MEDIUM",
                                title=f"Mortgage fixed rate ends in {days_rem} days ({end_dt})",
                                detail=(f"The fixed rate of {rate_pct:.2f}% on "
                                        f"'{mort.get('name', 'mortgage')}' expires {end_dt}. "
                                        f"Without remortgaging you revert to the SVR "
                                        f"which is typically 1–2% higher."),
                                action="Compare remortgage deals now — good deals require "
                                       "3–6 months to arrange.",
                                days_left=days_rem,
                                colour="#e05252" if days_rem <= 60 else "#f0a500",
                                icon="🏠",
                            ))
                    except (ValueError, TypeError):
                        pass

        # ── Rule 9: Tax year deadline (general) ───────────────────────────────
        if 0 < days_left <= 30:
            alerts.append(CoachAlert(
                rule_id="tax_year_end",
                priority="HIGH",
                title=f"Tax year ends in {days_left} days — 5 April checklist",
                detail=(f"Only {days_left} days remain in the tax year. "
                        f"Key deadlines: ISA contributions (£20k), "
                        f"pension contributions (£{_PENSION_AA:,.0f} AA), "
                        f"CGT harvest (£3k exemption), "
                        f"capital losses crystallisation."),
                action="Review ISA, pension, and CGT positions before 5 April.",
                days_left=days_left,
                colour="#e05252",
                icon="📅",
            ))
        elif 30 < days_left <= 60:
            alerts.append(CoachAlert(
                rule_id="tax_year_end",
                priority="MEDIUM",
                title=f"Tax year ends in {days_left} days",
                detail=(f"Approximately {days_left} days until the end of the tax year "
                        f"(5 April). Review ISA and pension contributions."),
                days_left=days_left,
                colour="#f0a500",
                icon="📅",
            ))

        # ── Rule 10: PCLS reminder ────────────────────────────────────────────
        uncrystallised = [
            p for p in pensions
            if not p.get("drawdown_config", {}).get("lump_sum_taken", False)
            and float(p.get("current_value", 0)) > 20_000
        ]
        if uncrystallised and current_age >= retire_age - 5:
            total_pcls = sum(
                float(p.get("current_value", 0)) *
                float(p.get("drawdown_config", {}).get("tax_free_lump_sum_pct", 0.25))
                for p in uncrystallised
            )
            alerts.append(CoachAlert(
                rule_id="pcls_reminder",
                priority="LOW",
                title=f"Pension tax-free cash available: ~£{total_pcls:,.0f}",
                detail=(f"{len(uncrystallised)} uncrystallised pension fund(s) with an "
                        f"estimated £{total_pcls:,.0f} in tax-free cash (25% PCLS). "
                        f"Compare UFPLS vs PCLS strategies in the Tax Optimiser before "
                        f"accessing your pension."),
                action="Review Tax Optimiser → UFPLS vs PCLS before crystallising.",
                amount_gbp=total_pcls,
                colour="#a78bfa",
                icon="🏦",
            ))

        # ── Sort and return ───────────────────────────────────────────────────
        alerts.sort(key=lambda a: (_PRIORITY_ORDER.get(a.priority, 9),))

        n_high   = sum(1 for a in alerts if a.priority == "HIGH")
        n_medium = sum(1 for a in alerts if a.priority == "MEDIUM")
        n_low    = sum(1 for a in alerts if a.priority == "LOW")

        logger.info(
            "PlanningCoach: %d alerts (%d H / %d M / %d L)",
            len(alerts), n_high, n_medium, n_low,
        )

        return CoachResult(
            alerts=alerts,
            total_high=n_high,
            total_medium=n_medium,
            total_low=n_low,
            scenario_year=today.year,
            warnings=warnings,
        )
