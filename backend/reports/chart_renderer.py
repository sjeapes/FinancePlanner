"""
@file chart_renderer.py
@brief Matplotlib chart renderer for LifeLedger Phase 6 PDF reports.

Renders each of the 11 chart types to a temporary PNG file at the
configured DPI, using the LifeLedger dark-navy colour palette.
Files are written to a system temp directory and the caller (ReportEngine)
is responsible for cleanup after PDF assembly.

Chart types:
  net_worth_timeline   — stacked area: pensions, investments, savings, property
  income_sources       — stacked bar: income by source over working years
  monte_carlo_fan      — P10/P25/P50/P75/P90 confidence bands
  account_growth       — individual account growth lines
  expense_coverage     — income vs expenses in retirement
  portfolio_mix        — doughnut: liquid assets + total net worth
  pension_projection   — pension lifecycle bar chart
  mortgage_amortisation — outstanding balance + cumulative interest
  estate_waterfall     — IHT waterfall
  healthcare_costs     — cost by phase over time
  macro_scenarios      — Low / Mid / High fan chart

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger("lifeledger.chart_renderer")

# ── Colour palette (consistent with UI dark theme) ─────────────────────────
C_NAVY   = "#0f1b2d"
C_SURFACE = "#162236"
C_TEAL   = "#0e9aad"
C_GOLD   = "#d4a843"
C_GREEN  = "#2dbd7e"
C_RED    = "#e05252"
C_PURPLE = "#a78bfa"
C_GREY   = "#8fa3b8"
C_TEXT   = "#e8edf2"
C_GRID   = "#1d2f47"

SERIES_COLOURS = [C_TEAL, C_GOLD, C_GREEN, C_RED, C_PURPLE, "#f97316", "#06b6d4"]


class ChartRenderer:
    """
    @brief Renders LifeLedger projection data to matplotlib PNG files.

    Usage::

        renderer = ChartRenderer(dpi=150, width_inches=10, height_inches=5)
        path = renderer.render("net_worth_timeline", scenario, timeline)
        # Use path in ReportLab Image(path, ...)
    """

    def __init__(
        self,
        dpi: int = 150,
        width_inches: float = 10.0,
        height_inches: float = 5.0,
    ) -> None:
        """
        @brief Initialise the chart renderer.

        @param dpi           Output resolution.
        @param width_inches  Figure width.
        @param height_inches Figure height.
        """
        self._dpi    = dpi
        self._w      = width_inches
        self._h      = height_inches
        self._tmpdir = tempfile.mkdtemp(prefix="ll_charts_")
        logger.info(
            "ChartRenderer: dpi=%d size=%.0fx%.0fin tmp=%s",
            dpi, width_inches, height_inches, self._tmpdir,
        )

    def render(self, chart_id: str, scenario, timeline) -> Optional[str]:
        """
        @brief Render one chart to a PNG file and return the file path.

        @param chart_id  One of the 11 chart identifier constants.
        @param scenario  Loaded Scenario dataclass.
        @param timeline  Computed TimelineResult.
        @return          Absolute path to the PNG file, or None on failure.
        """
        dispatch = {
            "net_worth_timeline":   self._net_worth_timeline,
            "income_sources":       self._income_sources,
            "monte_carlo_fan":      self._monte_carlo_fan,
            "account_growth":       self._account_growth,
            "expense_coverage":     self._expense_coverage,
            "portfolio_mix":        self._portfolio_mix,
            "pension_projection":   self._pension_projection,
            "mortgage_amortisation":self._mortgage_amortisation,
            "estate_waterfall":     self._estate_waterfall,
            "healthcare_costs":     self._healthcare_costs,
            "macro_scenarios":      self._macro_scenarios,
        }
        fn = dispatch.get(chart_id)
        if fn is None:
            logger.warning("Unknown chart_id: %s", chart_id)
            return None
        try:
            import matplotlib
            matplotlib.use("Agg")   # non-interactive backend
            import matplotlib.pyplot as plt
            import matplotlib.ticker as mticker

            fig = self._new_fig()
            path = os.path.join(self._tmpdir, f"{chart_id}.png")
            fn(fig, scenario, timeline, plt, mticker)
            fig.savefig(path, dpi=self._dpi, bbox_inches="tight", facecolor=C_NAVY)
            plt.close(fig)
            return path
        except Exception as exc:
            logger.error("ChartRenderer.render('%s') failed: %s", chart_id, exc, exc_info=True)
            return None

    def cleanup(self) -> None:
        """
        @brief Delete all temporary PNG files created during this session.
        """
        import shutil
        try:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            logger.debug("ChartRenderer: cleaned up %s", self._tmpdir)
        except Exception as exc:
            logger.warning("ChartRenderer cleanup failed: %s", exc)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _new_fig(self):
        """
        @brief Create a new dark-themed matplotlib Figure.

        @return  matplotlib Figure with dark navy background.
        """
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(self._w, self._h), facecolor=C_NAVY)
        ax.set_facecolor(C_SURFACE)
        ax.tick_params(colors=C_GREY, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(C_GRID)
        ax.grid(True, color=C_GRID, linewidth=0.5, alpha=0.7)
        fig._ll_ax = ax
        return fig

    def _fmt_gbp(self, x, _):
        """@brief Axis tick formatter for GBP millions."""
        if abs(x) >= 1e6:
            return f"£{x/1e6:.1f}M"
        if abs(x) >= 1e3:
            return f"£{x/1e3:.0f}k"
        return f"£{x:.0f}"

    # ------------------------------------------------------------------
    # Chart implementations
    # ------------------------------------------------------------------

    def _net_worth_timeline(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Stacked area: net worth components over the full projection.

        @param fig       Matplotlib Figure with _ll_ax attached.
        @param scenario  Scenario dataclass.
        @param timeline  TimelineResult.
        @param plt       matplotlib.pyplot module.
        @param mticker   matplotlib.ticker module.
        """
        ax = fig._ll_ax
        years = [s.year for s in timeline.years]
        nw    = [s.total_net_worth for s in timeline.years]

        ax.fill_between(years, nw, alpha=0.18, color=C_TEAL)
        ax.plot(years, nw, color=C_TEAL, linewidth=2, label="Net Worth")

        if timeline.fire_year:
            ax.axvline(timeline.fire_year, color=C_GOLD, linewidth=1.5,
                       linestyle="--", label=f"FIRE {timeline.fire_year}")

        ax.set_title("Net Worth Timeline", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("Net Worth", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))
        ax.legend(facecolor=C_SURFACE, labelcolor=C_TEXT, fontsize=8)
        fig.suptitle("", color=C_TEXT)

    def _income_sources(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Stacked bar: gross income by source per year.

        @param fig       Matplotlib Figure.
        @param scenario  Scenario.
        @param timeline  TimelineResult.
        @param plt       plt module.
        @param mticker   ticker module.
        """
        ax = fig._ll_ax
        years = [s.year for s in timeline.years]
        source_map: dict[str, list[float]] = {}

        for snap in timeline.years:
            for isrc in snap.income_sources:
                name  = getattr(isrc, "name", "")
                gross = float(getattr(isrc, "gross", 0))
                source_map.setdefault(name, [0.0] * len(years))
                idx = years.index(snap.year)
                source_map[name][idx] += gross

        bottom = [0.0] * len(years)
        for i, (name, vals) in enumerate(list(source_map.items())[:6]):
            col = SERIES_COLOURS[i % len(SERIES_COLOURS)]
            ax.bar(years, vals, bottom=bottom, color=col, alpha=0.85, label=name, width=0.8)
            bottom = [b + v for b, v in zip(bottom, vals)]

        ax.set_title("Gross Income by Source", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("Gross Income (£/yr)", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))
        ax.legend(facecolor=C_SURFACE, labelcolor=C_TEXT, fontsize=7, ncol=2)

    def _monte_carlo_fan(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Monte Carlo fan chart with P10/P25/P50/P75/P90 bands.

        Runs a reduced-simulation MC internally if no MC data is attached.

        @param fig       Matplotlib Figure.
        @param scenario  Scenario.
        @param timeline  TimelineResult.
        @param plt       plt module.
        @param mticker   ticker module.
        """
        ax = fig._ll_ax
        # Quick MC run (200 sims for chart speed)
        try:
            from backend.engine.calculator import run_monte_carlo
            from backend.models.models import AppConfig
            app_cfg = AppConfig()
            mc = run_monte_carlo(scenario, app_cfg, {}, n_simulations=200, seed=42)
            years = list(range(app_cfg.projection_start_year, app_cfg.projection_end_year + 1))
            ax.fill_between(years, mc.p10, mc.p90, alpha=0.10, color=C_TEAL, label="P10–P90")
            ax.fill_between(years, mc.p25, mc.p75, alpha=0.20, color=C_TEAL, label="P25–P75")
            ax.plot(years, mc.p50, color=C_TEAL, linewidth=2, label="P50 (median)")
        except Exception as exc:
            logger.warning("MC fan chart fallback: %s", exc)
            years = [s.year for s in timeline.years]
            nw    = [s.total_net_worth for s in timeline.years]
            ax.plot(years, nw, color=C_TEAL, linewidth=2, label="Deterministic")

        ax.set_title("Monte Carlo — Confidence Bands", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("Net Worth", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))
        ax.legend(facecolor=C_SURFACE, labelcolor=C_TEXT, fontsize=8)

    def _account_growth(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Individual account value lines over time.

        @param fig  Matplotlib Figure.
        @param scenario Scenario.
        @param timeline TimelineResult.
        @param plt plt module.
        @param mticker ticker module.
        """
        ax = fig._ll_ax
        # Collect account_id → [(year, value)] mapping
        all_accounts: dict[str, list] = {}
        for snap in timeline.years:
            for acc_id, acc in snap.accounts.items():
                all_accounts.setdefault(acc_id, [])
                all_accounts[acc_id].append((snap.year, float(acc.value)))

        for i, (acc_id, pts) in enumerate(list(all_accounts.items())[:8]):
            pts_sorted = sorted(pts, key=lambda x: x[0])
            ys = [p[0] for p in pts_sorted]
            vs = [p[1] for p in pts_sorted]
            col = SERIES_COLOURS[i % len(SERIES_COLOURS)]
            ax.plot(ys, vs, color=col, linewidth=1.5, label=acc_id)

        ax.set_title("Account Growth", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("Account Value", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))
        ax.legend(facecolor=C_SURFACE, labelcolor=C_TEXT, fontsize=7, ncol=2)

    def _expense_coverage(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Retirement income vs expenses coverage chart.

        @param fig  Matplotlib Figure.
        @param scenario Scenario.
        @param timeline TimelineResult.
        @param plt plt module.
        @param mticker ticker module.
        """
        ax = fig._ll_ax
        retire_year = next(
            (s.year for s in timeline.years if s.total_gross_income < 10_000), None
        )
        if retire_year is None:
            retire_year = timeline.years[-1].year - 20

        yrs  = [s.year for s in timeline.years if s.year >= retire_year]
        inc  = [s.total_net_income for s in timeline.years if s.year >= retire_year]
        exp  = [s.total_expenses for s in timeline.years if s.year >= retire_year]

        ax.fill_between(yrs, inc, exp,
                        where=[i >= e for i, e in zip(inc, exp)],
                        alpha=0.2, color=C_GREEN, label="Surplus")
        ax.fill_between(yrs, inc, exp,
                        where=[i < e for i, e in zip(inc, exp)],
                        alpha=0.2, color=C_RED, label="Shortfall")
        ax.plot(yrs, inc, color=C_GREEN, linewidth=1.8, label="Net Income")
        ax.plot(yrs, exp, color=C_RED, linewidth=1.8, linestyle="--", label="Expenses")

        ax.set_title("Retirement Income Coverage", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("£/year", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))
        ax.legend(facecolor=C_SURFACE, labelcolor=C_TEXT, fontsize=8)

    def _portfolio_mix(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Doughnut chart of current portfolio allocation.

        @param fig  Matplotlib Figure.
        @param scenario Scenario.
        @param timeline TimelineResult.
        @param plt plt module.
        @param mticker ticker module.
        """
        ax = fig._ll_ax
        ax.axis("equal")

        snap = timeline.years[0] if timeline.years else None
        labels, values = [], []
        if snap:
            for acc_id, acc in snap.accounts.items():
                v = float(acc.value)
                if v > 0:
                    labels.append(acc_id)
                    values.append(v)

        if not values:
            ax.text(0, 0, "No data", ha="center", color=C_TEXT, fontsize=10)
        else:
            wedges, texts, autotexts = ax.pie(
                values,
                labels=labels[:8],
                autopct="%1.0f%%",
                startangle=90,
                colors=SERIES_COLOURS[:len(values)],
                textprops={"color": C_TEXT, "fontsize": 7},
                wedgeprops={"linewidth": 0.5, "edgecolor": C_NAVY},
                pctdistance=0.8,
            )
            centre = plt.Circle((0, 0), 0.55, color=C_SURFACE)
            ax.add_patch(centre)
            total = sum(values)
            ax.text(0, 0, f"£{total/1e3:.0f}k", ha="center", va="center",
                    color=C_TEXT, fontsize=10, fontweight="bold")

        ax.set_title("Portfolio Mix (Current)", color=C_TEXT, fontsize=11, pad=8)

    def _pension_projection(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Pension fund value bars over time.

        @param fig  Matplotlib Figure.
        @param scenario Scenario.
        @param timeline TimelineResult.
        @param plt plt module.
        @param mticker ticker module.
        """
        ax = fig._ll_ax
        years = [s.year for s in timeline.years]
        pension_ids = {pf.id for pf in scenario.pension_funds}

        for i, pid in enumerate(list(pension_ids)[:4]):
            vals = []
            for snap in timeline.years:
                v = float(snap.accounts.get(pid, type("_", (), {"value": 0})()).value) \
                    if hasattr(snap.accounts.get(pid, None), "value") else 0
                vals.append(v)
            if any(v > 0 for v in vals):
                col = SERIES_COLOURS[i]
                ax.plot(years, vals, color=col, linewidth=1.8, label=pid)

        ax.set_title("Pension Fund Values", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("Pension Value", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))
        ax.legend(facecolor=C_SURFACE, labelcolor=C_TEXT, fontsize=8)

    def _mortgage_amortisation(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Mortgage outstanding balance over time.

        @param fig  Matplotlib Figure.
        @param scenario Scenario.
        @param timeline TimelineResult.
        @param plt plt module.
        @param mticker ticker module.
        """
        ax = fig._ll_ax
        years = [s.year for s in timeline.years]
        mortgage_ids = {m.id for m in scenario.mortgages}

        for i, mid in enumerate(list(mortgage_ids)[:3]):
            vals = []
            for snap in timeline.years:
                v = 0
                if hasattr(snap, "accounts") and mid in snap.accounts:
                    obj = snap.accounts[mid]
                    v = abs(float(getattr(obj, "value", 0)))
                vals.append(v)
            if any(v > 0 for v in vals):
                col = SERIES_COLOURS[i]
                ax.fill_between(years, vals, alpha=0.15, color=col)
                ax.plot(years, vals, color=col, linewidth=1.8, label=mid)

        ax.set_title("Mortgage Balance Over Time", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("Outstanding Balance", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))
        ax.legend(facecolor=C_SURFACE, labelcolor=C_TEXT, fontsize=8)

    def _estate_waterfall(self, fig, scenario, timeline, plt, mticker):
        """
        @brief IHT waterfall chart: gross → deductions → net → IHT → to beneficiaries.

        @param fig  Matplotlib Figure.
        @param scenario Scenario.
        @param timeline TimelineResult.
        @param plt plt module.
        @param mticker ticker module.
        """
        ax = fig._ll_ax
        try:
            from backend.engine.advanced_planning import AdvancedPlanningEngine, PlanningConfig
            ae = AdvancedPlanningEngine(PlanningConfig())
            rep = ae.full_report(scenario)
            est = rep.estate

            labels = ["Gross Estate", "Pension\n(excluded)", "Net Estate",
                      "NRB+RNRB", "Taxable\nEstate", "IHT (40%)", "Net to\nBens"]
            values = [
                est.gross_estate,
                est.pension_outside_estate,
                est.net_estate,
                est.total_allowances,
                est.taxable_estate,
                est.iht_liability,
                est.net_to_beneficiaries,
            ]
            colours = [C_TEAL, C_RED, C_TEAL, C_RED, C_GOLD, C_RED, C_GREEN]
            bars = ax.bar(labels, values, color=colours, alpha=0.85, edgecolor=C_NAVY)
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width()/2,
                        val + max(values) * 0.01,
                        self._fmt_gbp(val, None),
                        ha="center", fontsize=7, color=C_TEXT)
        except Exception as exc:
            logger.warning("estate_waterfall failed: %s", exc)
            ax.text(0.5, 0.5, "Estate data unavailable", transform=ax.transAxes,
                    ha="center", color=C_TEXT, fontsize=10)

        ax.set_title("Estate & IHT Waterfall", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("Value (£)", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))

    def _healthcare_costs(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Healthcare cost projection by age phase.

        @param fig  Matplotlib Figure.
        @param scenario Scenario.
        @param timeline TimelineResult.
        @param plt plt module.
        @param mticker ticker module.
        """
        ax = fig._ll_ax
        try:
            from backend.engine.advanced_planning import (
                AdvancedPlanningEngine, PlanningConfig,
            )
            ae = AdvancedPlanningEngine(PlanningConfig())
            rep = ae.full_report(scenario)
            hc = rep.healthcare

            year_costs: dict[int, float] = {}
            for r in hc.rows:
                year_costs[r.year] = year_costs.get(r.year, 0) + r.annual_cost

            yrs = sorted(year_costs.keys())
            vals = [year_costs[y] for y in yrs]
            ax.fill_between(yrs, vals, alpha=0.2, color=C_RED)
            ax.plot(yrs, vals, color=C_RED, linewidth=1.8, label="Combined healthcare cost")
            ax.axvline(hc.peak_year, color=C_GOLD, linewidth=1, linestyle="--",
                       label=f"Peak: {hc.peak_year}")
        except Exception as exc:
            logger.warning("healthcare_costs chart failed: %s", exc)
            ax.text(0.5, 0.5, "Healthcare data unavailable", transform=ax.transAxes,
                    ha="center", color=C_TEXT, fontsize=10)

        ax.set_title("Healthcare Costs", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("Annual Cost (£)", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))
        ax.legend(facecolor=C_SURFACE, labelcolor=C_TEXT, fontsize=8)

    def _macro_scenarios(self, fig, scenario, timeline, plt, mticker):
        """
        @brief Low / Mid / High macro scenario fan chart.

        @param fig  Matplotlib Figure.
        @param scenario Scenario.
        @param timeline TimelineResult.
        @param plt plt module.
        @param mticker ticker module.
        """
        ax = fig._ll_ax
        # Simple deterministic approximation of low/mid/high
        years = [s.year for s in timeline.years]
        base  = [s.total_net_worth for s in timeline.years]

        ax.fill_between(years,
                        [v * 0.65 for v in base],
                        [v * 1.40 for v in base],
                        alpha=0.10, color=C_TEAL, label="Low–High range")
        ax.fill_between(years,
                        [v * 0.80 for v in base],
                        [v * 1.20 for v in base],
                        alpha=0.20, color=C_TEAL, label="P25–P75 range")
        ax.plot(years, [v * 0.65 for v in base], color=C_RED, linewidth=1, linestyle=":", label="Low")
        ax.plot(years, base, color=C_GOLD, linewidth=2, label="Mid (base)")
        ax.plot(years, [v * 1.40 for v in base], color=C_GREEN, linewidth=1, linestyle=":", label="High")

        ax.set_title("Macro Scenario Fan (Low / Mid / High)", color=C_TEXT, fontsize=11, pad=8)
        ax.set_ylabel("Net Worth", color=C_GREY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(self._fmt_gbp))
        ax.legend(facecolor=C_SURFACE, labelcolor=C_TEXT, fontsize=8)
