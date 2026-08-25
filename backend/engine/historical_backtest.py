"""
@file historical_backtest.py
@brief Phase 9 historical sequence backtest engine for LifeLedger.

Replays the projection using actual historical equity return sequences to
show how the plan would have fared if retirement started in a crash year.

This demonstrates sequence-of-returns risk in a way Monte Carlo does not:
the returns are drawn from real history rather than random samples.

Sequences
---------
1929  Great Depression: -43% at the trough (1931), multi-year recovery
1966  UK stagflation: 15 years of poor real returns with high inflation
2000  Dot-com bust: three-year drawdown, then GFC hits at end of recovery
2008  GFC: -37% in year 1, rapid V-shaped recovery

After the historical sequence ends, the projection reverts to the scenario's
configured nominal growth rate for the remainder of the projection window.

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("lifeledger.historical_backtest")


# ─────────────────────────────────────────────────────────────────────────────
# Historical return sequences
# ─────────────────────────────────────────────────────────────────────────────
# All values are annual total returns as decimals (e.g. -0.43 = -43%).
# Sources: Robert Shiller data (US S&P 500), Barclays Equity Gilt Study (UK).
# Used for planning illustration only — actual returns will differ by index.

HISTORICAL_SEQUENCES: dict[str, dict] = {

    "1929": {
        "label": "Great Depression (1929)",
        "description": "The worst equity crash in modern history. Starting retirement in 1929 meant "
                       "a -43% drawdown in year 3 and 25 years to recover in real terms.",
        "colour": "#e05252",
        "returns": [  # 1929–1958, annual total returns (decimal)
            -0.084, -0.249, -0.433, -0.082,  0.540, -0.014,  0.480,  0.339,
            -0.350,  0.311, -0.119,  0.199,  0.254,  0.192,  0.360, -0.079,
             0.060,  0.049,  0.182,  0.304,  0.243,  0.181, -0.012,  0.524,
             0.317,  0.071, -0.097,  0.439,  0.117,  0.002,
        ],
    },

    "1966": {
        "label": "Stagflation (1966–1981)",
        "description": "A 15-year period of poor real returns driven by inflation. UK equities "
                       "fell 73% in real terms between 1972–1974.",
        "colour": "#f97316",
        "returns": [  # 1966–1985, approximate UK/global equity returns
            -0.100,  0.240,  0.110, -0.080,  0.040,  0.140,  0.190, -0.170,
            -0.270,  0.370,  0.240,  0.040,  0.010,  0.200,  0.320,  0.180,
             0.050,  0.167,  0.321,  0.185,
        ],
    },

    "2000": {
        "label": "Dot-com bust (2000–2002)",
        "description": "Three consecutive negative years followed by recovery — then the GFC "
                       "hit in year 9. A 10-year period delivering near-zero real returns.",
        "colour": "#d4a843",
        "returns": [  # 2000–2013
            -0.091, -0.119, -0.221,  0.287,  0.109,  0.049,  0.158,  0.055,
            -0.370,  0.265,  0.151,  0.021,  0.160,  0.324,
        ],
    },

    "2008": {
        "label": "Global Financial Crisis (2008)",
        "description": "A sharp -37% drawdown in year 1 followed by a rapid V-shaped recovery. "
                       "Sequence risk is lower here than 1929 or 1966 due to the swift rebound.",
        "colour": "#0e9aad",
        "returns": [  # 2008–2022
            -0.370,  0.265,  0.151,  0.021,  0.160,  0.324,  0.137,  0.014,
             0.120,  0.218, -0.044,  0.314,  0.186,  0.287, -0.181,
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class BacktestYearSnapshot:
    """
    @brief Portfolio value in one year under a historical scenario.

    @param year           Calendar year (offset from retirement start).
    @param age            Primary person's age.
    @param portfolio      Portfolio value at year end.
    @param return_rate    Equity return rate applied this year.
    @param drawdown       Annual drawdown (spending) this year.
    @param fire_sustained True while portfolio > 0.
    """
    year: int
    age: int
    portfolio: float
    return_rate: float
    drawdown: float
    fire_sustained: bool


@dataclass
class BacktestScenarioResult:
    """
    @brief Full trajectory for one historical starting scenario.

    @param scenario_id    Key from HISTORICAL_SEQUENCES.
    @param label          Display label.
    @param description    Plain-English description.
    @param colour         Hex colour for chart rendering.
    @param years          Year-by-year snapshots.
    @param terminal_value Portfolio value at end of projection.
    @param ruin_year      Year portfolio hit zero (None if portfolio survived).
    @param survived       True if portfolio never reached zero.
    @param min_value      Lowest portfolio value reached during projection.
    @param min_value_year Year of lowest portfolio value.
    """
    scenario_id: str
    label: str
    description: str
    colour: str
    years: list[BacktestYearSnapshot]
    terminal_value: float
    ruin_year: Optional[int]
    survived: bool
    min_value: float
    min_value_year: int


@dataclass
class HistoricalBacktestResult:
    """
    @brief Full historical backtest output.

    @param base_label         Label for the base (mean-return) scenario.
    @param base_years         Base scenario year snapshots.
    @param base_terminal      Base scenario terminal portfolio value.
    @param scenarios          One result per historical sequence.
    @param all_survived       True if all historical scenarios survived without ruin.
    @param worst_scenario_id  Scenario ID with the lowest terminal value.
    @param worst_terminal     Lowest terminal value across all scenarios.
    @param warnings           Warning messages.
    """
    base_label: str
    base_years: list[BacktestYearSnapshot]
    base_terminal: float
    scenarios: list[BacktestScenarioResult]
    all_survived: bool
    worst_scenario_id: str
    worst_terminal: float
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────


class HistoricalBacktestEngine:
    """
    @brief Runs the portfolio through historical equity return sequences.

    For each historical sequence, the engine replaces the configured nominal
    growth rate with the actual sequence returns for those years, then
    reverts to the base growth rate for the remainder of the projection.
    """

    def run(
        self,
        starting_portfolio: float,
        annual_drawdown: float,
        retirement_year: int,
        projection_end_year: int,
        birth_year: int,
        base_growth_rate: float = 0.07,
        inflation_rate: float = 0.025,
        equity_fraction: float = 0.80,
    ) -> HistoricalBacktestResult:
        """
        @brief Run the historical backtest against all four sequences.

        @param starting_portfolio  Portfolio value at retirement start (GBP).
        @param annual_drawdown     Annual drawdown in today's money.
        @param retirement_year     Calendar year retirement begins.
        @param projection_end_year Last calendar year to model.
        @param birth_year          Primary person's birth year.
        @param base_growth_rate    Nominal growth rate for non-sequence years.
        @param inflation_rate      CPI for uprating drawdown each year.
        @param equity_fraction     Fraction of portfolio exposed to equity returns.
                                   (1 - equity_fraction) earns base_growth_rate regardless.
        @return                    HistoricalBacktestResult.
        """
        warnings: list[str] = []
        n_years = projection_end_year - retirement_year + 1

        # ── Base scenario (constant mean return) ─────────────────────────────
        base_years = self._project(
            portfolio=starting_portfolio,
            drawdown_base=annual_drawdown,
            n_years=n_years,
            retirement_year=retirement_year,
            birth_year=birth_year,
            return_sequence=[base_growth_rate] * n_years,
            inflation_rate=inflation_rate,
        )
        base_terminal = base_years[-1].portfolio if base_years else 0.0

        # ── Historical scenarios ──────────────────────────────────────────────
        scenario_results: list[BacktestScenarioResult] = []

        for seq_id, seq_data in HISTORICAL_SEQUENCES.items():
            hist_returns = seq_data["returns"]
            # Build the return sequence: history first, then revert to base
            full_sequence: list[float] = []
            for i in range(n_years):
                if i < len(hist_returns):
                    # Blend: equity_fraction at historical rate,
                    # (1-equity_fraction) at base rate
                    hist_r = hist_returns[i]
                    blended = equity_fraction * hist_r + (1 - equity_fraction) * base_growth_rate
                    full_sequence.append(blended)
                else:
                    full_sequence.append(base_growth_rate)

            year_snaps = self._project(
                portfolio=starting_portfolio,
                drawdown_base=annual_drawdown,
                n_years=n_years,
                retirement_year=retirement_year,
                birth_year=birth_year,
                return_sequence=full_sequence,
                inflation_rate=inflation_rate,
            )

            terminal  = year_snaps[-1].portfolio if year_snaps else 0.0
            ruin_year = next((s.year for s in year_snaps if not s.fire_sustained), None)
            survived  = ruin_year is None

            # Minimum portfolio (trough)
            min_val  = min(s.portfolio for s in year_snaps)
            min_yr   = next(s.year for s in year_snaps if s.portfolio == min_val)

            if not survived:
                warnings.append(
                    f"{seq_data['label']}: portfolio exhausted at "
                    f"age {min_yr - birth_year} ({min_yr})."
                )

            scenario_results.append(BacktestScenarioResult(
                scenario_id=seq_id,
                label=seq_data["label"],
                description=seq_data["description"],
                colour=seq_data["colour"],
                years=year_snaps,
                terminal_value=round(terminal, 2),
                ruin_year=ruin_year,
                survived=survived,
                min_value=round(min_val, 2),
                min_value_year=min_yr,
            ))
            logger.info(
                "Backtest %s: terminal=£%.0f survived=%s min=£%.0f at %d",
                seq_id, terminal, survived, min_val, min_yr,
            )

        all_survived   = all(s.survived for s in scenario_results)
        worst          = min(scenario_results, key=lambda s: s.terminal_value, default=None)
        worst_id       = worst.scenario_id if worst else ""
        worst_terminal = worst.terminal_value if worst else 0.0

        return HistoricalBacktestResult(
            base_label="Base projection (mean returns)",
            base_years=base_years,
            base_terminal=round(base_terminal, 2),
            scenarios=scenario_results,
            all_survived=all_survived,
            worst_scenario_id=worst_id,
            worst_terminal=worst_terminal,
            warnings=warnings,
        )

    @staticmethod
    def _project(
        portfolio: float,
        drawdown_base: float,
        n_years: int,
        retirement_year: int,
        birth_year: int,
        return_sequence: list[float],
        inflation_rate: float,
    ) -> list[BacktestYearSnapshot]:
        """
        @brief Run a single portfolio projection with a given return sequence.

        @param portfolio      Starting portfolio value.
        @param drawdown_base  Annual drawdown in today's money.
        @param n_years        Number of years to project.
        @param retirement_year  First calendar year.
        @param birth_year     Primary person's birth year.
        @param return_sequence  Annual return for each year.
        @param inflation_rate  CPI for uprating drawdown.
        @return               List of BacktestYearSnapshot.
        """
        snaps: list[BacktestYearSnapshot] = []
        val = portfolio

        for i in range(n_years):
            yr  = retirement_year + i
            age = yr - birth_year
            r   = return_sequence[i] if i < len(return_sequence) else 0.07

            # Inflation-uprated drawdown
            drawdown = drawdown_base * (1 + inflation_rate) ** i

            # Apply return then subtract drawdown
            val = val * (1 + r) - drawdown
            fire_sustained = val > 0
            if not fire_sustained:
                val = 0.0

            snaps.append(BacktestYearSnapshot(
                year=yr, age=age,
                portfolio=round(val, 2),
                return_rate=round(r, 4),
                drawdown=round(drawdown, 2),
                fire_sustained=fire_sustained,
            ))

            if not fire_sustained:
                # Fill remaining years with zeros
                for j in range(i + 1, n_years):
                    snaps.append(BacktestYearSnapshot(
                        year=retirement_year + j,
                        age=(retirement_year + j) - birth_year,
                        portfolio=0.0,
                        return_rate=return_sequence[j] if j < len(return_sequence) else 0.07,
                        drawdown=drawdown_base * (1 + inflation_rate) ** j,
                        fire_sustained=False,
                    ))
                break

        return snaps
