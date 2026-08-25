"""
@file insight_engine.py
@brief Phase 12 insight engine — Monte Carlo insight surfacing and annual review automation.

Monte Carlo Insights
--------------------
Analyses an existing MC result to surface actionable insights without
re-running the simulation. Applies heuristic rules based on financial
planning theory to generate 3-7 prioritised insights per scenario.

Annual Review Automation
------------------------
Compares two timestamped simulation snapshots stored in SQLite and
generates a narrative summary of what changed year-over-year:
  - Net worth change vs projected
  - FIRE timeline delta
  - Account-level changes
  - Key ratios (savings rate, SWR coverage, etc.)

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger("lifeledger.insight_engine")


# ─────────────────────────────────────────────────────────────────────────────
# MC Insight dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MCInsight:
    """
    @brief One Monte Carlo planning insight.

    @param category   'survival' | 'sequence_risk' | 'savings' | 'allocation'
                      | 'withdrawal' | 'timeline' | 'estate'.
    @param priority   'HIGH' | 'MEDIUM' | 'LOW'.
    @param title      Short headline (< 70 chars).
    @param detail     2-3 sentence explanation with numbers.
    @param action     Recommended next step.
    @param impact     Quantified impact estimate (e.g. '+8% survival probability').
    @param colour     Hex colour for UI badge.
    @param icon       Emoji icon.
    """
    category: str
    priority: str
    title: str
    detail: str
    action: str = ""
    impact: str = ""
    colour: str = "#f0a500"
    icon: str = "💡"


@dataclass
class MCInsightResult:
    """
    @brief Full MC insight analysis result.

    @param scenario_path    Path to the scenario analysed.
    @param prob_fire        Current MC survival probability (0-1).
    @param n_simulations    Number of MC runs used.
    @param insights         Ranked list of insights.
    @param overall_health   'excellent' | 'good' | 'caution' | 'at_risk'.
    @param summary          One-line overall plan assessment.
    @param warnings         Engine warnings.
    """
    scenario_path: str
    prob_fire: float
    n_simulations: int
    insights: list[MCInsight]
    overall_health: str
    summary: str
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# MC Insight engine
# ─────────────────────────────────────────────────────────────────────────────

_HEALTH_THRESHOLDS = [
    (0.95, "excellent"),
    (0.85, "good"),
    (0.70, "caution"),
    (0.00, "at_risk"),
]

_HEALTH_COLOURS = {
    "excellent": "#2dbd7e",
    "good":      "#0e9aad",
    "caution":   "#f0a500",
    "at_risk":   "#e05252",
}

_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def generate_mc_insights(
    prob_fire: float,
    n_simulations: int,
    scenario: dict,
    fire_year: Optional[int] = None,
    current_nw: Optional[float] = None,
    fire_target_nw: Optional[float] = None,
    annual_spending: Optional[float] = None,
    years_to_fire: Optional[int] = None,
    equity_fraction: float = 0.70,
    scenario_path: str = "",
) -> MCInsightResult:
    """
    @brief Generate prioritised insights from Monte Carlo results.

    @param prob_fire        Survival probability from MC (0-1).
    @param n_simulations    Number of MC runs.
    @param scenario         Raw scenario dict.
    @param fire_year        Projected FIRE year.
    @param current_nw       Current net worth from latest simulation.
    @param fire_target_nw   FIRE target net worth.
    @param annual_spending  Annual spending target.
    @param years_to_fire    Years until FIRE.
    @param equity_fraction  Fraction of portfolio in equities.
    @param scenario_path    Path for labelling.
    @return                 MCInsightResult.
    """
    sc = scenario.get("scenario", scenario)
    warnings: list[str] = []
    insights: list[MCInsight] = []

    # Derived values
    swr = (annual_spending / current_nw) if current_nw and annual_spending else 0.04
    fire_pct = (current_nw / fire_target_nw * 100) if current_nw and fire_target_nw else None
    people = sc.get("people", [])
    pensions = sc.get("pension_funds", [])
    savings_accts = sc.get("savings_accounts", [])
    income_sources = sc.get("income_sources", [])

    total_pension = sum(float(p.get("current_value", 0)) for p in pensions)
    total_savings = sum(float(s.get("current_value", 0)) for s in savings_accts)

    emergency_fund = next(
        (sum(float(s.get("current_value", 0)) for s in savings_accts
             if s.get("account_type") in ("general", "savings")), None),
        None,
    )
    monthly_expenses = (annual_spending / 12) if annual_spending else 3_000
    emergency_months = emergency_fund / monthly_expenses if emergency_fund else 0

    # ── 1. Survival probability ───────────────────────────────────────────────
    if prob_fire < 0.70:
        insights.append(MCInsight(
            category="survival", priority="HIGH",
            title=f"Plan survives in only {prob_fire*100:.0f}% of simulations",
            detail=(f"Out of {n_simulations:,} Monte Carlo scenarios, your portfolio was "
                    f"exhausted before the end of the projection in "
                    f"{(1-prob_fire)*100:.0f}% of runs. The most common cause is a "
                    f"poor sequence of returns in the early retirement years."),
            action="Reduce planned withdrawal rate, extend working years by 1-2, "
                   "or increase equity allocation to improve resilience.",
            impact=f"Target > 85% for a robust plan",
            colour="#e05252", icon="⚠",
        ))
    elif prob_fire < 0.85:
        insights.append(MCInsight(
            category="survival", priority="MEDIUM",
            title=f"Plan survives in {prob_fire*100:.0f}% of simulations — approaching target",
            detail=(f"{prob_fire*100:.0f}% survival across {n_simulations:,} simulations. "
                    f"The 15-30% failure scenarios typically involve a market crash in the "
                    f"first 5 years of retirement. Small adjustments could close this gap."),
            action="Consider a flexible spending rule — reduce withdrawals by 10% "
                   "in any year the portfolio falls more than 15%.",
            impact="Flexible spending typically adds 5-12% to survival probability",
            colour="#f0a500", icon="⚡",
        ))
    else:
        insights.append(MCInsight(
            category="survival", priority="LOW",
            title=f"Plan survives in {prob_fire*100:.0f}% of simulations ✓",
            detail=(f"Strong result: {prob_fire*100:.0f}% survival across {n_simulations:,} "
                    f"simulations. Your plan is resilient to most historical market sequences. "
                    f"Maintain this by reviewing allocation annually."),
            action="Run the historical backtest (Timeline → Backtest tab) to verify against "
                   "1929 and 1966 scenarios.",
            impact="Sustain by keeping equity allocation ≥ 60% in early retirement",
            colour="#2dbd7e", icon="✓",
        ))

    # ── 2. Safe withdrawal rate ───────────────────────────────────────────────
    if swr > 0.045:
        insights.append(MCInsight(
            category="withdrawal", priority="HIGH",
            title=f"Withdrawal rate of {swr*100:.1f}% is above the safe threshold",
            detail=(f"Withdrawing {swr*100:.1f}% of your portfolio annually significantly "
                    f"increases the risk of running out of money, especially if early retirement "
                    f"years see poor returns. The research consensus is 3.5-4% for 30+ year "
                    f"retirements."),
            action=f"Aim to reduce annual withdrawals by £{(annual_spending or 40_000)*(swr-0.04)/swr:,.0f} "
                   f"or grow the portfolio before retiring to lower the effective rate.",
            impact=f"Reducing to 4.0% SWR typically adds 10-20% to survival probability",
            colour="#e05252", icon="📉",
        ))
    elif swr < 0.03 and current_nw and current_nw > 1_000_000:
        insights.append(MCInsight(
            category="withdrawal", priority="LOW",
            title=f"Very conservative withdrawal rate of {swr*100:.1f}% — scope to spend more",
            detail=(f"At {swr*100:.1f}% SWR you have a very large safety margin. "
                    f"Most studies show 3.5-4% is sustainable across a 30-year retirement "
                    f"in the vast majority of historical sequences."),
            action="Consider whether there are goals (travel, gifts, charitable giving) "
                   "where you'd benefit from spending more in early retirement.",
            impact="At 3.5% SWR you could withdraw an additional "
                   f"£{(current_nw*(0.035-swr)):,.0f}/yr",
            colour="#2dbd7e", icon="💚",
        ))

    # ── 3. Sequence-of-returns risk ───────────────────────────────────────────
    if prob_fire < 0.90 and years_to_fire and years_to_fire < 10:
        insights.append(MCInsight(
            category="sequence_risk", priority="MEDIUM",
            title="Within 10 years of FIRE — sequence risk window is open",
            detail=(f"With FIRE {years_to_fire} years away, you are entering the "
                    f"'fragile decade' — the 5 years before and after retirement where a market "
                    f"crash has the most impact on lifetime outcomes. A 40% drawdown now "
                    f"affects every subsequent year of retirement."),
            action="Consider a 'glide path' — gradually reducing equity allocation from "
                   f"{equity_fraction*100:.0f}% toward 50-60% over the next "
                   f"{min(years_to_fire, 7)} years.",
            impact="Gradual de-risking reduces worst-case shortfall by 15-30%",
            colour="#f97316", icon="🎯",
        ))

    # ── 4. Emergency fund ─────────────────────────────────────────────────────
    if emergency_months < 3:
        insights.append(MCInsight(
            category="savings", priority="HIGH",
            title=f"Emergency fund covers only {emergency_months:.1f} months of expenses",
            detail=(f"Liquid cash ({emergency_months:.1f} months) is below the recommended "
                    f"3-month minimum. Without a buffer, a job loss or emergency forces you "
                    f"to sell investments — potentially at a market low, permanently "
                    f"damaging long-term returns."),
            action=f"Build liquid savings to £{monthly_expenses*3:,.0f} (3 months) "
                   f"before increasing ISA or pension contributions.",
            impact="Emergency fund prevents forced selling at market lows",
            colour="#e05252", icon="🛡",
        ))
    elif emergency_months < 6:
        insights.append(MCInsight(
            category="savings", priority="MEDIUM",
            title=f"Emergency fund at {emergency_months:.1f} months — target is 6",
            detail=f"Current liquid savings cover {emergency_months:.1f} months of expenses. "
                   f"The 6-month target provides resilience for longer periods of reduced income.",
            action=f"Top up by £{monthly_expenses*(6-emergency_months):,.0f} to reach 6-month cover.",
            impact=f"£{monthly_expenses*(6-emergency_months):,.0f} additional liquid savings needed",
            colour="#f0a500", icon="🛡",
        ))

    # ── 5. Pension vs ISA balance ─────────────────────────────────────────────
    if current_nw and total_pension > 0:
        pension_pct = total_pension / current_nw
        if pension_pct > 0.80 and current_nw > 500_000:
            insights.append(MCInsight(
                category="allocation", priority="MEDIUM",
                title=f"{pension_pct*100:.0f}% of wealth is in pension — consider ISA diversification",
                detail=(f"With {pension_pct*100:.0f}% in pension funds, most of your wealth is "
                        f"locked until at least age 57 (rising to 57 in 2028). A higher ISA "
                        f"balance gives tax-free income flexibility in early retirement and "
                        f"reduces the risk of being forced into high-tax pension drawdowns."),
                action="Redirect up to £20k/year into a Stocks & Shares ISA to build "
                       "tax-free flexibility.",
                impact="ISA withdrawals don't count toward the income tax personal allowance",
                colour="#a78bfa", icon="⚖",
            ))

    # ── 6. FIRE timeline ──────────────────────────────────────────────────────
    if fire_pct and fire_pct < 75 and years_to_fire and years_to_fire > 5:
        monthly_gap = (fire_target_nw - current_nw) / (years_to_fire * 12) if fire_target_nw else 0
        insights.append(MCInsight(
            category="timeline", priority="LOW",
            title=f"FIRE {years_to_fire} years away — on track at {fire_pct:.0f}%",
            detail=(f"Current net worth is {fire_pct:.0f}% of the FIRE target. "
                    f"You need the portfolio to grow by a further "
                    f"£{max(0, (fire_target_nw or 0) - (current_nw or 0)):,.0f} "
                    f"to reach independence. Compound growth will do most of the work."),
            action="Run the scenario sliders on the Dashboard to see how an extra "
                   f"£{min(monthly_gap, 2000):,.0f}/month affects the FIRE date.",
            impact=f"Extra £500/month typically brings FIRE 1-2 years closer",
            colour="#0e9aad", icon="📈",
        ))

    # ── 7. Estate / IHT ───────────────────────────────────────────────────────
    if current_nw and current_nw > 900_000 and len(people) > 0:
        est_iht = max(0, (current_nw - 650_000)) * 0.40
        if est_iht > 50_000:
            insights.append(MCInsight(
                category="estate", priority="MEDIUM",
                title=f"Estimated IHT liability: £{est_iht:,.0f}",
                detail=(f"Based on current net worth, your estate may face a "
                        f"substantial IHT bill. Annual gift allowances (£3,000/donor/year), "
                        f"pension funds (currently outside the estate), and charitable "
                        f"giving can reduce this significantly."),
                action="Review the Estate Planner screen for detailed IHT analysis and "
                       "mitigation strategies.",
                impact=f"RNRB and pension trust could reduce liability by up to £{min(est_iht, 350_000):,.0f}",
                colour="#f97316", icon="🏛",
            ))

    # Sort by priority
    insights.sort(key=lambda i: _PRIORITY_ORDER.get(i.priority, 9))

    # Overall health
    health = next(h for t, h in _HEALTH_THRESHOLDS if prob_fire >= t)
    summaries = {
        "excellent": f"Excellent: {prob_fire*100:.0f}% survival — your plan is robust across most market scenarios.",
        "good":      f"Good: {prob_fire*100:.0f}% survival — solid foundation with room for minor improvements.",
        "caution":   f"Caution: {prob_fire*100:.0f}% survival — meaningful risk of portfolio exhaustion; action recommended.",
        "at_risk":   f"At risk: {prob_fire*100:.0f}% survival — significant changes needed to the plan.",
    }

    logger.info("MCInsights: prob=%.2f health=%s insights=%d", prob_fire, health, len(insights))

    return MCInsightResult(
        scenario_path=scenario_path,
        prob_fire=round(prob_fire, 4),
        n_simulations=n_simulations,
        insights=insights,
        overall_health=health,
        summary=summaries[health],
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Annual review dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReviewMetric:
    """@brief One changed metric in the annual review."""
    label: str
    current: float
    previous: float
    delta: float
    delta_pct: float
    unit: str = "£"
    better: bool = True


@dataclass
class AnnualReview:
    """
    @brief Annual review comparison result.

    @param review_date     Date this review was generated.
    @param baseline_date   Date of the baseline snapshot being compared against.
    @param period_label    Human-readable period (e.g. '12 months').
    @param metrics         List of changed metrics.
    @param narrative       Plain-English narrative summary.
    @param headline        One-line headline.
    @param fire_delta_months  FIRE date moved (positive = closer, negative = further).
    @param warnings        Warning messages.
    """
    review_date: str
    baseline_date: str
    period_label: str
    metrics: list[ReviewMetric]
    narrative: str
    headline: str
    fire_delta_months: int
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Review snapshot storage (SQLite)
# ─────────────────────────────────────────────────────────────────────────────

def _db_path(db_file: str) -> str:
    return db_file


def save_review_snapshot(
    db_file: str,
    scenario_path: str,
    net_worth: float,
    fire_year: Optional[int],
    pension_value: float,
    isa_value: float,
    savings_value: float,
    annual_spending: float,
    prob_fire: float,
) -> str:
    """
    @brief Persist a simulation snapshot for later annual review comparison.

    @param db_file       Path to the SQLite database.
    @param scenario_path Scenario path key.
    @return              Snapshot ID (ISO date string).
    """
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS review_snapshots (
            id TEXT PRIMARY KEY,
            scenario_path TEXT,
            snapshot_date TEXT,
            net_worth REAL,
            fire_year INTEGER,
            pension_value REAL,
            isa_value REAL,
            savings_value REAL,
            annual_spending REAL,
            prob_fire REAL
        )
    """)
    snap_id = date.today().isoformat()
    conn.execute("""
        INSERT OR REPLACE INTO review_snapshots
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (snap_id, scenario_path, snap_id, net_worth, fire_year,
          pension_value, isa_value, savings_value, annual_spending, prob_fire))
    conn.commit()
    conn.close()
    logger.info("review_snapshot saved: %s nw=£%.0f", snap_id, net_worth)
    return snap_id


def load_review_snapshots(db_file: str, scenario_path: str) -> list[dict]:
    """
    @brief Load all review snapshots for a scenario, newest first.

    @param db_file       Path to the SQLite database.
    @param scenario_path Scenario path key.
    @return              List of snapshot dicts.
    """
    if not os.path.exists(db_file):
        return []
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM review_snapshots WHERE scenario_path=? ORDER BY snapshot_date DESC",
        (scenario_path,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def generate_annual_review(
    current_nw: float,
    current_fire_year: Optional[int],
    current_pension: float,
    current_isa: float,
    current_savings: float,
    current_spending: float,
    current_prob_fire: float,
    baseline_snapshot: dict,
) -> AnnualReview:
    """
    @brief Generate a narrative annual review comparing current to a baseline.

    @param current_*         Current simulation values.
    @param baseline_snapshot Snapshot dict from save_review_snapshot.
    @return                  AnnualReview.
    """
    prev_date = baseline_snapshot.get("snapshot_date", "unknown")
    prev_nw   = float(baseline_snapshot.get("net_worth", current_nw))
    prev_fire = baseline_snapshot.get("fire_year")
    prev_prob = float(baseline_snapshot.get("prob_fire", current_prob_fire))

    # Period
    try:
        months = round((date.today() - date.fromisoformat(prev_date)).days / 30.44)
        period = f"{months} months" if months < 24 else f"{months//12} years"
    except ValueError:
        period = "since last snapshot"
        months = 12

    # Metrics
    metrics: list[ReviewMetric] = []

    def metric(label, curr, prev, unit="£", higher_better=True):
        delta = curr - prev
        delta_pct = (delta / abs(prev) * 100) if abs(prev) > 0.01 else 0.0
        better = delta > 0 if higher_better else delta < 0
        metrics.append(ReviewMetric(
            label=label, current=curr, previous=prev,
            delta=round(delta, 2), delta_pct=round(delta_pct, 1),
            unit=unit, better=better,
        ))

    metric("Net worth",      current_nw,          prev_nw)
    metric("Pension value",  current_pension,     float(baseline_snapshot.get("pension_value", current_pension)))
    metric("ISA value",      current_isa,         float(baseline_snapshot.get("isa_value", current_isa)))
    metric("MC survival",    current_prob_fire*100, prev_prob*100, unit="%")

    # FIRE delta
    fire_delta_months = 0
    if current_fire_year and prev_fire:
        fire_delta_months = round((prev_fire - current_fire_year) * 12)

    # Narrative
    nw_delta = current_nw - prev_nw
    nw_sign = "grew" if nw_delta >= 0 else "fell"
    fire_line = ""
    if fire_delta_months > 0:
        fire_line = (f" The FIRE date moved {fire_delta_months} months closer "
                     f"(now {current_fire_year}).")
    elif fire_delta_months < 0:
        fire_line = (f" The FIRE date moved {abs(fire_delta_months)} months further "
                     f"out (now {current_fire_year}).")

    prob_line = ""
    prob_delta = current_prob_fire - prev_prob
    if abs(prob_delta) > 0.02:
        prob_line = (f" Monte Carlo survival probability "
                     f"{'improved' if prob_delta > 0 else 'fell'} "
                     f"by {abs(prob_delta)*100:.0f} percentage points to "
                     f"{current_prob_fire*100:.0f}%.")

    narrative = (
        f"Over the past {period}, your net worth {nw_sign} by "
        f"£{abs(nw_delta):,.0f} ({'+' if nw_delta >= 0 else ''}"
        f"{(nw_delta/prev_nw*100) if prev_nw else 0:.1f}%), "
        f"reaching £{current_nw:,.0f}."
        f"{fire_line}{prob_line}"
    )

    nw_pct = (nw_delta / prev_nw * 100) if prev_nw else 0
    headline = (
        f"Net worth {'up' if nw_delta >= 0 else 'down'} "
        f"£{abs(nw_delta):,.0f} ({'+' if nw_delta >= 0 else ''}{nw_pct:.1f}%) "
        f"over {period}"
        + (f" · FIRE {fire_delta_months} months closer" if fire_delta_months > 0 else "")
        + (f" · FIRE {abs(fire_delta_months)} months further" if fire_delta_months < 0 else "")
    )

    logger.info("AnnualReview: nw_delta=£%.0f fire_delta=%d months", nw_delta, fire_delta_months)

    return AnnualReview(
        review_date=date.today().isoformat(),
        baseline_date=prev_date,
        period_label=period,
        metrics=metrics,
        narrative=narrative,
        headline=headline,
        fire_delta_months=fire_delta_months,
    )
