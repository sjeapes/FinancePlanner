"""
@file report_engine.py
@brief PDF report export engine for LifeLedger Phase 6.

Implements a 7-step pipeline to produce professional financial planning
PDF reports from a ``Scenario`` and ``TimelineResult``:

  1. Validate ``ReportConfig`` — check sections, presets, output path.
  2. Run projection — call ``ProjectionEngine`` if no ``TimelineResult``
     is supplied.
  3. Render charts — call ``ChartRenderer`` to produce matplotlib PNGs for
     each requested chart type.
  4. Assemble section flowables — convert each section into ReportLab
     Platypus flowables (``Paragraph``, ``Table``, ``Image``, etc.).
  5. Build PDF — write to the configured output path with headers/footers.
  6. Upload to Google Drive — optional, controlled by config.
  7. Return the output file path for the API response.

Three presets:
  quick       — 4 pages: cover + summary + account table + 2 charts
  full_annual — ~18 pages: all 9 sections + up to 8 charts
  ifa_pack    — ~28 pages: all sections + all 11 charts + detailed tables

Requires ``reportlab>=4.1`` and ``matplotlib>=3.8``.  If ReportLab is not
installed the engine logs a clear error and raises ``ImportError`` with
installation instructions.

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import yaml

logger = logging.getLogger("lifeledger.reports")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Section identifiers
SEC_COVER          = "cover_page"
SEC_EXEC_SUMMARY   = "executive_summary"
SEC_ACCOUNTS       = "account_snapshots"
SEC_INCOME         = "income_breakdown"
SEC_ASSUMPTIONS    = "future_assumptions"
SEC_GRAPHS         = "projection_graphs"
SEC_SCENARIOS      = "scenario_comparison"
SEC_RETIREMENT     = "retirement_coverage"
SEC_ESTATE         = "estate_summary"

ALL_SECTIONS = [
    SEC_COVER, SEC_EXEC_SUMMARY, SEC_ACCOUNTS, SEC_INCOME,
    SEC_ASSUMPTIONS, SEC_GRAPHS, SEC_SCENARIOS, SEC_RETIREMENT, SEC_ESTATE,
]

# Chart identifiers
CHART_NET_WORTH    = "net_worth_timeline"
CHART_INCOME       = "income_sources"
CHART_MC_FAN       = "monte_carlo_fan"
CHART_ACCOUNTS     = "account_growth"
CHART_COVERAGE     = "expense_coverage"
CHART_PORTFOLIO    = "portfolio_mix"
CHART_PENSION      = "pension_projection"
CHART_MORTGAGE     = "mortgage_amortisation"
CHART_ESTATE       = "estate_waterfall"
CHART_HEALTHCARE   = "healthcare_costs"
CHART_MACRO        = "macro_scenarios"

ALL_CHARTS = [
    CHART_NET_WORTH, CHART_INCOME, CHART_MC_FAN, CHART_ACCOUNTS,
    CHART_COVERAGE, CHART_PORTFOLIO, CHART_PENSION, CHART_MORTGAGE,
    CHART_ESTATE, CHART_HEALTHCARE, CHART_MACRO,
]

# Preset definitions
PRESETS: dict[str, dict] = {
    "quick": {
        "sections": [SEC_COVER, SEC_EXEC_SUMMARY, SEC_ACCOUNTS, SEC_GRAPHS],
        "charts":   [CHART_NET_WORTH, CHART_INCOME],
        "include_monte_carlo": False,
    },
    "full_annual": {
        "sections": ALL_SECTIONS,
        "charts":   [CHART_NET_WORTH, CHART_INCOME, CHART_MC_FAN, CHART_ACCOUNTS,
                     CHART_COVERAGE, CHART_PORTFOLIO, CHART_PENSION, CHART_ESTATE],
        "include_monte_carlo": True,
    },
    "ifa_pack": {
        "sections": ALL_SECTIONS,
        "charts":   ALL_CHARTS,
        "include_monte_carlo": True,
    },
}

# Brand colours (used in PDF headings, table headers, etc.)
COLOUR_NAVY  = "#0f1b2d"
COLOUR_TEAL  = "#0e9aad"
COLOUR_GOLD  = "#d4a843"
COLOUR_GREEN = "#2dbd7e"
COLOUR_TEXT  = "#1a1a2e"
COLOUR_LIGHT = "#f4f6f8"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ReportConfig:
    """
    @brief Configuration for one PDF report build.

    @param title              Report title, shown on cover page.
    @param subtitle           Subtitle (e.g. 'Annual Review 2025').
    @param prepared_for       Client name shown on cover page.
    @param prepared_by        Adviser/firm name shown on cover page.
    @param scenario_path      Path to the scenario YAML, relative to project root.
    @param preset             'quick' | 'full_annual' | 'ifa_pack'.
                              If set, overrides sections and charts with preset defaults.
    @param sections           Explicit list of section identifiers to include.
    @param charts             Explicit list of chart identifiers to include.
    @param include_monte_carlo  True to run MC simulation and include fan chart.
    @param mc_simulations     Number of MC simulations (if include_monte_carlo=True).
    @param paper_size         'A4' | 'letter'.
    @param colour_scheme      'navy_teal' | 'warm' | 'monochrome'.
    @param watermark          None | 'CONFIDENTIAL' | 'DRAFT'.
    @param output_path        Absolute output file path for the generated PDF.
    @param output_filename    Filename template (used if output_path not set).
    @param chart_dpi          Resolution of embedded charts in DPI.
    @param chart_width_inches  Width of embedded chart figures.
    @param chart_height_inches Height of embedded chart figures.
    @param include_toc        True to include a Table of Contents page.
    @param upload_to_drive    True to upload to Google Drive after generation.
    @param drive_folder       Google Drive folder path.
    @param date_range_start   First year to show on timeline charts.
    @param date_range_end     Last year to show on timeline charts.
    @param enabled            False to skip generation entirely.
    @param notes              Free-text notes.
    """

    title: str = "LifeLedger Financial Plan"
    subtitle: str = ""
    prepared_for: str = ""
    prepared_by: str = "LifeLedger"
    scenario_path: str = "data/scenarios/base.yaml"
    preset: str = "full_annual"
    sections: list[str] = field(default_factory=list)
    charts: list[str] = field(default_factory=list)
    include_monte_carlo: bool = True
    mc_simulations: int = 500
    paper_size: str = "A4"
    colour_scheme: str = "navy_teal"
    watermark: Optional[str] = None
    output_path: Optional[str] = None
    output_filename: str = "lifeledger_{date}_{name}.pdf"
    chart_dpi: int = 150
    chart_width_inches: float = 10.0
    chart_height_inches: float = 5.0
    include_toc: bool = True
    upload_to_drive: bool = False
    drive_folder: str = "LifeLedger/exports"
    date_range_start: int = 2025
    date_range_end: int = 2075
    enabled: bool = True
    notes: str = ""

    def resolve_sections_and_charts(self) -> None:
        """
        @brief Apply preset defaults to sections and charts if not explicitly set.

        If self.preset is set and self.sections / self.charts are empty, fills
        them from PRESETS.  Also syncs include_monte_carlo from the preset.
        """
        if self.preset in PRESETS and not self.sections:
            p = PRESETS[self.preset]
            self.sections = list(p["sections"])
            self.charts = list(p["charts"])
            self.include_monte_carlo = bool(p.get("include_monte_carlo", False))
            logger.debug(
                "ReportConfig.resolve: applied preset '%s' → %d sections, %d charts",
                self.preset, len(self.sections), len(self.charts),
            )

    def effective_output_path(self, project_root: str) -> str:
        """
        @brief Resolve the absolute output file path.

        Uses self.output_path if set, otherwise constructs from project_root
        and the output_filename template.

        @param project_root  Project root directory.
        @return              Absolute path to write the PDF.
        """
        if self.output_path:
            return self.output_path
        date_str = date.today().isoformat()
        name_slug = (
            (self.prepared_for or "report").lower()
            .replace(" ", "_").replace("/", "_")[:20]
        )
        filename = (
            self.output_filename
            .replace("{date}", date_str)
            .replace("{name}", name_slug)
        )
        return os.path.join(project_root, "data", "exports", filename)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class ReportResult:
    """
    @brief Result of a successful report build.

    @param output_path    Absolute path to the generated PDF.
    @param file_size_kb   File size in kilobytes.
    @param page_count     Number of pages in the PDF.
    @param sections_built List of section identifiers that were included.
    @param charts_built   List of chart identifiers that were rendered.
    @param drive_url      Google Drive URL if uploaded (None otherwise).
    @param build_seconds  Wall-clock time to generate the report.
    @param warnings       Non-fatal warning strings.
    """

    output_path: str
    file_size_kb: float
    page_count: int
    sections_built: list[str]
    charts_built: list[str]
    drive_url: Optional[str]
    build_seconds: float
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ReportEngine:
    """
    @brief PDF report export engine.

    Implements the 7-step pipeline to produce a PDF from a scenario.

    Usage::

        engine = ReportEngine(project_root='.')
        config = ReportConfig(preset='full_annual', prepared_for='Stephen')
        result = engine.build(config, scenario, timeline)
    """

    def __init__(self, project_root: str = ".") -> None:
        """
        @brief Initialise the report engine.

        @param project_root  Absolute path to the project root directory.
        @raises ImportError  If reportlab is not installed.
        """
        self._root = project_root
        self._check_dependencies()
        logger.info("ReportEngine initialised (root=%s)", project_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        config: ReportConfig,
        scenario=None,
        timeline=None,
        tax_profiles: Optional[dict] = None,
    ) -> ReportResult:
        """
        @brief Execute the 7-step report pipeline.

        @param config        ReportConfig controlling the output.
        @param scenario      Pre-loaded Scenario (loaded from config.scenario_path if None).
        @param timeline      Pre-computed TimelineResult (re-run if None).
        @param tax_profiles  Tax profile dict (loaded from config if None).
        @return              ReportResult with path and metadata.
        @raises ValueError   If config validation fails.
        @raises ImportError  If reportlab is not installed.
        """
        import time
        t0 = time.time()
        warnings: list[str] = []

        if not config.enabled:
            raise ValueError("ReportConfig.enabled is False — generation skipped.")

        # ── Step 1: Validate ─────────────────────────────────────────────────
        config.resolve_sections_and_charts()
        self._validate_config(config)
        logger.info(
            "ReportEngine.build: preset=%s sections=%d charts=%d",
            config.preset, len(config.sections), len(config.charts),
        )

        # ── Step 2: Load scenario + run projection ───────────────────────────
        scenario, timeline, tax_profiles = self._ensure_projection(
            config, scenario, timeline, tax_profiles
        )

        # ── Step 3: Render charts ────────────────────────────────────────────
        chart_paths = self._render_charts(config, scenario, timeline)
        charts_built = list(chart_paths.keys())

        # ── Step 4: Assemble flowables ────────────────────────────────────────
        flowables = self._assemble_sections(
            config, scenario, timeline, chart_paths
        )

        # ── Step 5: Build PDF ────────────────────────────────────────────────
        output_path = config.effective_output_path(self._root)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        page_count = self._build_pdf(config, flowables, output_path)
        file_size_kb = round(os.path.getsize(output_path) / 1024, 1)

        # ── Step 6: Upload to Drive ──────────────────────────────────────────
        drive_url: Optional[str] = None
        if config.upload_to_drive:
            drive_url = self._upload_to_drive(config, output_path)

        # ── Step 7: Return result ────────────────────────────────────────────
        build_secs = round(time.time() - t0, 1)
        logger.info(
            "ReportEngine.build complete: %s (%.0fkB, %d pages, %.1fs)",
            output_path, file_size_kb, page_count, build_secs,
        )

        return ReportResult(
            output_path=output_path,
            file_size_kb=file_size_kb,
            page_count=page_count,
            sections_built=list(config.sections),
            charts_built=charts_built,
            drive_url=drive_url,
            build_seconds=build_secs,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Step 1: Validate
    # ------------------------------------------------------------------

    def _validate_config(self, config: ReportConfig) -> None:
        """
        @brief Validate ReportConfig fields before running.

        @param config  ReportConfig to validate.
        @raises ValueError  On fatal configuration error.
        """
        errors: list[str] = []
        if not config.sections:
            errors.append("No sections configured. Set preset or explicit sections list.")
        invalid_sections = [s for s in config.sections if s not in ALL_SECTIONS]
        if invalid_sections:
            errors.append(f"Unknown sections: {invalid_sections}")
        invalid_charts = [c for c in config.charts if c not in ALL_CHARTS]
        if invalid_charts:
            errors.append(f"Unknown charts: {invalid_charts}")
        if config.paper_size not in ("A4", "letter"):
            errors.append(f"paper_size must be 'A4' or 'letter', got '{config.paper_size}'")
        if config.chart_dpi < 72 or config.chart_dpi > 600:
            errors.append(f"chart_dpi {config.chart_dpi} is outside [72, 600]")
        if errors:
            msg = "ReportConfig validation failed: " + "; ".join(errors)
            logger.error(msg)
            raise ValueError(msg)

    # ------------------------------------------------------------------
    # Step 2: Projection
    # ------------------------------------------------------------------

    def _ensure_projection(self, config, scenario, timeline, tax_profiles):
        """
        @brief Load scenario and run projection if not already provided.

        @param config       ReportConfig.
        @param scenario     Pre-loaded Scenario or None.
        @param timeline     Pre-computed TimelineResult or None.
        @param tax_profiles Dict of TaxProfile or None.
        @return             Tuple (scenario, timeline, tax_profiles).
        """
        from backend.persistence.yaml_serialiser import (
            load_scenario_from_file, load_app_config_from_file,
            load_tax_profiles_from_file,
        )

        if scenario is None:
            abs_path = os.path.join(self._root, config.scenario_path)
            scenario = load_scenario_from_file(abs_path)
            if scenario is None:
                raise ValueError(f"Failed to load scenario from '{config.scenario_path}'")
            logger.info("Loaded scenario: %s", getattr(scenario, "name", "unknown"))

        if tax_profiles is None:
            tp_path = os.path.join(self._root, "config", "tax_profiles.yaml")
            try:
                profiles = load_tax_profiles_from_file(tp_path)
                tax_profiles = {p.id: p for p in profiles}
            except Exception as exc:
                logger.warning("Could not load tax profiles: %s — using empty dict", exc)
                tax_profiles = {}

        if timeline is None:
            from backend.engine.calculator import ProjectionEngine
            from backend.models.models import AppConfig
            cfg_path = os.path.join(self._root, "config", "lifeledger_config.yaml")
            try:
                app_cfg = load_app_config_from_file(cfg_path)
            except Exception:
                app_cfg = AppConfig()
            proj = ProjectionEngine(scenario, app_cfg, tax_profiles)
            timeline = proj.run()
            logger.info("Projection complete: FIRE year=%s", timeline.fire_year)

        return scenario, timeline, tax_profiles

    # ------------------------------------------------------------------
    # Step 3: Chart rendering
    # ------------------------------------------------------------------

    def _render_charts(
        self, config: ReportConfig, scenario, timeline
    ) -> dict[str, str]:
        """
        @brief Render all requested chart types to temporary PNG files.

        @param config    ReportConfig.
        @param scenario  Loaded Scenario.
        @param timeline  Computed TimelineResult.
        @return          Dict mapping chart_id -> absolute PNG file path.
        """
        from backend.reports.chart_renderer import ChartRenderer

        renderer = ChartRenderer(
            dpi=config.chart_dpi,
            width_inches=config.chart_width_inches,
            height_inches=config.chart_height_inches,
        )

        chart_paths: dict[str, str] = {}
        for chart_id in config.charts:
            try:
                path = renderer.render(chart_id, scenario, timeline)
                if path:
                    chart_paths[chart_id] = path
                    logger.debug("Chart rendered: %s → %s", chart_id, path)
            except Exception as exc:
                logger.warning("Chart '%s' failed: %s — skipping", chart_id, exc)

        return chart_paths

    # ------------------------------------------------------------------
    # Step 4: Assemble flowables
    # ------------------------------------------------------------------

    def _assemble_sections(
        self,
        config: ReportConfig,
        scenario,
        timeline,
        chart_paths: dict[str, str],
    ) -> list:
        """
        @brief Convert each section into a list of ReportLab Platypus flowables.

        @param config       ReportConfig.
        @param scenario     Loaded Scenario.
        @param timeline     Computed TimelineResult.
        @param chart_paths  Dict of chart_id -> PNG path.
        @return             Flat list of ReportLab flowables.
        """
        from reportlab.platypus import (
            HRFlowable, Image, KeepTogether, PageBreak,
            Paragraph, Spacer, Table, TableStyle,
        )
        from reportlab.lib import colors
        from reportlab.lib.units import inch, cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

        styles = getSampleStyleSheet()
        navy   = colors.HexColor(COLOUR_NAVY)
        teal   = colors.HexColor(COLOUR_TEAL)
        gold   = colors.HexColor(COLOUR_GOLD)
        light  = colors.HexColor(COLOUR_LIGHT)

        # Custom paragraph styles
        h1 = ParagraphStyle(
            "LL_H1", parent=styles["Heading1"],
            fontSize=20, textColor=navy, spaceAfter=8,
        )
        h2 = ParagraphStyle(
            "LL_H2", parent=styles["Heading2"],
            fontSize=13, textColor=teal, spaceAfter=6,
        )
        h3 = ParagraphStyle(
            "LL_H3", parent=styles["Heading3"],
            fontSize=11, textColor=navy, spaceAfter=4,
        )
        body = ParagraphStyle(
            "LL_Body", parent=styles["Normal"],
            fontSize=9, leading=13, textColor=colors.HexColor(COLOUR_TEXT),
        )
        small = ParagraphStyle(
            "LL_Small", parent=body, fontSize=8, textColor=colors.grey,
        )
        cover_title = ParagraphStyle(
            "LL_CoverTitle", parent=styles["Title"],
            fontSize=32, textColor=navy, spaceAfter=12, alignment=TA_CENTER,
        )
        cover_sub = ParagraphStyle(
            "LL_CoverSub", parent=styles["Normal"],
            fontSize=14, textColor=teal, alignment=TA_CENTER, spaceAfter=6,
        )
        cover_meta = ParagraphStyle(
            "LL_CoverMeta", parent=styles["Normal"],
            fontSize=10, textColor=colors.grey, alignment=TA_CENTER,
        )

        def hr():
            return HRFlowable(width="100%", thickness=1, color=teal, spaceAfter=6)

        def section_header(text: str):
            return KeepTogether([
                Spacer(1, 0.2 * inch),
                Paragraph(text, h2),
                hr(),
            ])

        def table_style_default():
            return TableStyle([
                ("BACKGROUND",  (0, 0), (-1, 0),  navy),
                ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
                ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
                ("FONTSIZE",    (0, 0), (-1, 0),  9),
                ("FONTSIZE",    (0, 1), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light]),
                ("GRID",        (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
                ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING",(0, 0), (-1, -1), 6),
                ("TOPPADDING",  (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0),(-1, -1), 4),
            ])

        flowables = []

        for section_id in config.sections:
            if section_id == SEC_COVER:
                flowables.extend(self._section_cover(
                    config, Paragraph, Spacer, PageBreak,
                    cover_title, cover_sub, cover_meta, hr, navy, teal, gold,
                ))

            elif section_id == SEC_EXEC_SUMMARY:
                flowables.append(section_header("Executive Summary"))
                flowables.extend(self._section_exec_summary(
                    scenario, timeline, Paragraph, Spacer, Table,
                    table_style_default, body, h3, small, teal,
                ))
                flowables.append(PageBreak())

            elif section_id == SEC_ACCOUNTS:
                flowables.append(section_header("Account Snapshots"))
                flowables.extend(self._section_accounts(
                    scenario, timeline, Paragraph, Spacer, Table,
                    table_style_default, body, small,
                ))
                flowables.append(PageBreak())

            elif section_id == SEC_INCOME:
                flowables.append(section_header("Income Breakdown"))
                flowables.extend(self._section_income(
                    scenario, timeline, Paragraph, Spacer, Table,
                    table_style_default, body, small,
                ))
                flowables.append(PageBreak())

            elif section_id == SEC_ASSUMPTIONS:
                flowables.append(section_header("Future Assumptions"))
                flowables.extend(self._section_assumptions(
                    scenario, Paragraph, Spacer, Table,
                    table_style_default, body, small,
                ))
                flowables.append(PageBreak())

            elif section_id == SEC_GRAPHS:
                flowables.append(section_header("Projection Charts"))
                for chart_id in config.charts:
                    if chart_id in chart_paths:
                        flowables.extend(self._embed_chart(
                            chart_id, chart_paths[chart_id],
                            config, Image, Paragraph, Spacer, h3,
                        ))

                flowables.append(PageBreak())

            elif section_id == SEC_SCENARIOS:
                flowables.append(section_header("Scenario Comparison"))
                flowables.extend(self._section_scenarios(
                    scenario, timeline, Paragraph, Spacer, Table,
                    table_style_default, body, small,
                ))
                flowables.append(PageBreak())

            elif section_id == SEC_RETIREMENT:
                flowables.append(section_header("Retirement Income Coverage"))
                flowables.extend(self._section_retirement(
                    scenario, timeline, Paragraph, Spacer, Table,
                    table_style_default, body, small, colors, navy, gold,
                ))
                flowables.append(PageBreak())

            elif section_id == SEC_ESTATE:
                flowables.append(section_header("Estate & IHT Summary"))
                flowables.extend(self._section_estate(
                    scenario, Paragraph, Spacer, Table,
                    table_style_default, body, small,
                ))

        return flowables

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _section_cover(self, config, Para, Spc, PBrk,
                       cover_title, cover_sub, cover_meta, hr,
                       navy, teal, gold):
        """@brief Build the cover-page flowables."""
        from reportlab.lib.units import inch
        flows = []
        flows.append(Spc(1, 2.0 * inch))
        flows.append(Para(config.title, cover_title))
        if config.subtitle:
            flows.append(Para(config.subtitle, cover_sub))
        flows.append(Spc(1, 0.4 * inch))
        flows.append(hr())
        flows.append(Spc(1, 0.3 * inch))
        if config.prepared_for:
            flows.append(Para(f"Prepared for: <b>{config.prepared_for}</b>", cover_meta))
        flows.append(Para(f"Prepared by: {config.prepared_by}", cover_meta))
        flows.append(Para(f"Date: {date.today().strftime('%d %B %Y')}", cover_meta))
        flows.append(Spc(1, 0.2 * inch))
        if config.watermark:
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib import colors
            wm_style = ParagraphStyle(
                "WM", fontSize=10, textColor=colors.red,
                alignment=1,
            )
            flows.append(Para(f"⚠ {config.watermark} ⚠", wm_style))
        flows.append(PBrk())
        return flows

    def _section_exec_summary(self, scenario, timeline, Para, Spc, Tbl,
                               ts_fn, body, h3, small, teal):
        """@brief Build executive summary flowables."""
        from reportlab.lib.units import inch
        flows = []
        fire_yr = getattr(timeline, "fire_year", None)
        latest = timeline.years[-1] if timeline.years else None
        first  = timeline.years[0] if timeline.years else None

        nw_now  = round(float(getattr(first,  "total_net_worth", 0)), 0) if first else 0
        nw_end  = round(float(getattr(latest, "total_net_worth", 0)), 0) if latest else 0

        data = [
            ["Metric", "Value"],
            ["Current Net Worth",   f"£{nw_now:,.0f}"],
            ["FIRE Achieved",       str(fire_yr) if fire_yr else "Not in projection"],
            ["Terminal Net Worth",  f"£{nw_end:,.0f} ({getattr(latest,'year','?')})"],
            ["Scenario",            getattr(scenario, "name", "Base")],
            ["Projection Range",    f"{getattr(first,'year','?')} → {getattr(latest,'year','?')}"],
            ["People",              ", ".join(getattr(p, "name", "") for p in scenario.people)],
        ]
        tbl = Tbl(data, colWidths=["45%", "55%"])
        tbl.setStyle(ts_fn())
        flows.append(tbl)
        flows.append(Spc(1, 0.15 * inch))

        if fire_yr:
            flows.append(Para(
                f"🎯 FIRE milestone projected in <b>{fire_yr}</b>. "
                f"The portfolio is on track to reach the target net worth.",
                body,
            ))
        else:
            flows.append(Para(
                "FIRE target is not achieved within the projection range. "
                "Consider increasing contribution rates or adjusting the target.",
                body,
            ))
        return flows

    def _section_accounts(self, scenario, timeline, Para, Spc, Tbl,
                           ts_fn, body, small):
        """@brief Build account snapshots table."""
        from reportlab.lib.units import inch
        snap = timeline.years[0] if timeline.years else None
        flows = []
        data = [["Account", "Type", "Current Value", "YTD Growth"]]
        for acc in (list(getattr(scenario, "investment_accounts", []))
                    + list(getattr(scenario, "savings_accounts", []))
                    + list(getattr(scenario, "pension_funds", []))):
            acc_id  = getattr(acc, "id", "")
            name    = getattr(acc, "name", acc_id)
            atype   = str(getattr(acc, "account_type", getattr(acc, "pension_type", "?")))
            if hasattr(atype, "value"):
                atype = atype.value
            val  = getattr(acc, "current_value", 0)
            growth = "—"
            if snap and acc_id in snap.accounts:
                growth_amt = getattr(snap.accounts[acc_id], "growth_amount", 0)
                growth = f"£{growth_amt:,.0f}"
            data.append([name, atype, f"£{float(val):,.0f}", growth])

        if len(data) == 1:
            flows.append(Para("No account data available.", small))
        else:
            tbl = Tbl(data, colWidths=["35%", "15%", "25%", "25%"])
            tbl.setStyle(ts_fn())
            flows.append(tbl)
        return flows

    def _section_income(self, scenario, timeline, Para, Spc, Tbl,
                         ts_fn, body, small):
        """@brief Build income breakdown table."""
        flows = []
        data = [["Income Source", "Person", "Gross/yr", "Tax Treatment", "Active Until"]]
        for isrc in scenario.income_sources:
            name = getattr(isrc, "name", "")
            pid  = getattr(isrc, "person_id", "")
            gross = getattr(isrc, "gross_annual", 0)
            tx = getattr(isrc, "tax_treatment", "")
            if hasattr(tx, "value"):
                tx = tx.value
            end  = getattr(isrc, "end_date", None)
            end_str = end.isoformat() if end else "Ongoing"
            data.append([name, pid, f"£{float(gross):,.0f}", str(tx), end_str])

        if len(data) == 1:
            flows.append(Para("No income source data.", small))
        else:
            tbl = Tbl(data, colWidths=["28%", "12%", "18%", "18%", "24%"])
            tbl.setStyle(ts_fn())
            flows.append(tbl)
        return flows

    def _section_assumptions(self, scenario, Para, Spc, Tbl, ts_fn, body, small):
        """@brief Build future assumptions table."""
        flows = []
        data = [["Parameter", "Value"]]
        # Pull from scenario/config where available
        growth_rates = set(
            f"{float(getattr(a, 'assumed_growth_rate', 0)):.1%}"
            for a in getattr(scenario, "investment_accounts", [])
        )
        data.extend([
            ["Base Inflation", "2.5% (configurable)"],
            ["Equity Growth Rates", " / ".join(growth_rates) or "Varies by account"],
            ["UK State Pension Growth", "2.5% (triple lock floor)"],
            ["Projection End", "2075"],
            ["Tax Regime", "UK 2024/25 rates (updated via tax_profiles.yaml)"],
            ["SIPP Annual Allowance", "£60,000 (2024/25)"],
            ["ISA Annual Allowance", "£20,000 per person (2024/25)"],
            ["CGT Annual Exemption", "£3,000 (2024/25)"],
        ])
        tbl = Tbl(data, colWidths=["45%", "55%"])
        tbl.setStyle(ts_fn())
        flows.append(tbl)
        flows.append(Para(
            "Rates are updated via config/tax_profiles.yaml and "
            "config/lifeledger_config.yaml. No financial advice is implied. "
            "Past performance is not a guide to future returns.",
            small,
        ))
        return flows

    def _embed_chart(self, chart_id, path, config, ImgCls, Para, Spc, h3):
        """@brief Embed one chart PNG as an Image flowable."""
        from reportlab.lib.units import inch
        labels = {
            CHART_NET_WORTH:  "Net Worth Timeline",
            CHART_INCOME:     "Income Sources",
            CHART_MC_FAN:     "Monte Carlo Confidence Bands",
            CHART_ACCOUNTS:   "Account Growth",
            CHART_COVERAGE:   "Retirement Income Coverage",
            CHART_PORTFOLIO:  "Portfolio Mix",
            CHART_PENSION:    "Pension Projection",
            CHART_MORTGAGE:   "Mortgage Amortisation",
            CHART_ESTATE:     "Estate Waterfall",
            CHART_HEALTHCARE: "Healthcare Costs",
            CHART_MACRO:      "Macro Scenarios (Low / Mid / High)",
        }
        flows = [Para(labels.get(chart_id, chart_id), h3)]
        try:
            img_width  = config.chart_width_inches * inch
            img_height = config.chart_height_inches * inch
            img = ImgCls(path, width=img_width, height=img_height)
            flows.append(img)
        except Exception as exc:
            logger.warning("Could not embed chart '%s': %s", chart_id, exc)
        flows.append(Spc(1, 0.15 * inch))
        return flows

    def _section_scenarios(self, scenario, timeline, Para, Spc, Tbl,
                            ts_fn, body, small):
        """@brief Build scenario comparison table at key ages."""
        flows = []
        key_years = [2030, 2035, 2040, 2045, 2050, 2060, 2070]
        data = [["Year", "Net Worth", "Assets", "Liabilities", "FIRE?"]]
        for yr in key_years:
            snap = timeline.year(yr)
            if snap:
                data.append([
                    str(yr),
                    f"£{float(snap.total_net_worth):,.0f}",
                    f"£{float(snap.total_assets):,.0f}",
                    f"£{float(snap.total_liabilities):,.0f}",
                    "✓" if snap.fire_achieved else "—",
                ])
        if len(data) > 1:
            tbl = Tbl(data, colWidths=["15%", "25%", "25%", "20%", "15%"])
            tbl.setStyle(ts_fn())
            flows.append(tbl)
        else:
            flows.append(Para("Projection data not available for key years.", small))
        return flows

    def _section_retirement(self, scenario, timeline, Para, Spc, Tbl,
                             ts_fn, body, small, colors, navy, gold):
        """@brief Build retirement income coverage table."""
        flows = []
        from backend.engine.retirement_engine import RetirementConfig, RetirementEngine
        try:
            re = RetirementEngine(RetirementConfig())
            report = re.analyse(scenario, timeline)
            cov = report.income_coverage
            if cov.years:
                data = [["Year", "Income", "Expenses", "Coverage", "Status"]]
                for row in cov.years[:20]:
                    data.append([
                        str(row.year),
                        f"£{row.total_income:,.0f}",
                        f"£{row.total_expenses:,.0f}",
                        f"{row.coverage_ratio:.0%}",
                        row.status.upper(),
                    ])
                tbl = Tbl(data, colWidths=["15%", "22%", "22%", "18%", "23%"])
                tbl.setStyle(ts_fn())
                flows.append(tbl)
                if cov.first_shortfall_year:
                    flows.append(Para(
                        f"⚠ First income shortfall: {cov.first_shortfall_year}. "
                        f"Average coverage: {cov.avg_coverage_ratio:.0%}.",
                        small,
                    ))
        except Exception as exc:
            logger.warning("Retirement section failed: %s", exc)
            flows.append(Para("Retirement analysis unavailable.", small))
        return flows

    def _section_estate(self, scenario, Para, Spc, Tbl, ts_fn, body, small):
        """@brief Build estate / IHT summary flowables."""
        flows = []
        from backend.engine.advanced_planning import AdvancedPlanningEngine, PlanningConfig
        try:
            ae = AdvancedPlanningEngine(PlanningConfig())
            rep = ae.full_report(scenario)
            est = rep.estate
            data = [
                ["Item", "Value"],
                ["Gross Estate",          f"£{est.gross_estate:,.0f}"],
                ["Pension (outside estate)", f"-£{est.pension_outside_estate:,.0f}"],
                ["Net Estate",            f"£{est.net_estate:,.0f}"],
                ["NRB + RNRB Available",  f"£{est.total_allowances:,.0f}"],
                ["Taxable Estate",        f"£{est.taxable_estate:,.0f}"],
                ["IHT Liability (40%)",   f"£{est.iht_liability:,.0f}"],
                ["Net to Beneficiaries",  f"£{est.net_to_beneficiaries:,.0f}"],
            ]
            tbl = Tbl(data, colWidths=["55%", "45%"])
            tbl.setStyle(ts_fn())
            flows.append(tbl)
            if est.iht_reduction_opportunities:
                flows.append(Spc(1, 0.1 * 72))
                flows.append(Para("<b>IHT reduction opportunities:</b>", body))
                for op in est.iht_reduction_opportunities[:3]:
                    flows.append(Para(
                        f"• {op['strategy']} → estimated saving £{op['estimated_saving']:,.0f}",
                        small,
                    ))
        except Exception as exc:
            logger.warning("Estate section failed: %s", exc)
            flows.append(Para("Estate analysis unavailable.", small))
        return flows

    # ------------------------------------------------------------------
    # Step 5: Build PDF
    # ------------------------------------------------------------------

    def _build_pdf(self, config: ReportConfig, flowables: list, output_path: str) -> int:
        """
        @brief Write all flowables to a PDF file using ReportLab Platypus.

        Adds page headers (title, logo placeholder) and footers (page number,
        date, confidentiality notice).

        @param config       ReportConfig.
        @param flowables    List of ReportLab flowable objects.
        @param output_path  Absolute output file path.
        @return             Number of pages in the generated PDF.
        """
        from reportlab.platypus import SimpleDocTemplate
        from reportlab.lib.pagesizes import A4, letter
        from reportlab.lib.units import inch, cm
        from reportlab.lib import colors

        page_size = A4 if config.paper_size == "A4" else letter
        margin = 1.8 * cm

        page_count = [0]

        navy = colors.HexColor(COLOUR_NAVY)
        teal = colors.HexColor(COLOUR_TEAL)

        def header_footer(canvas, doc):
            """@brief Draw header and footer on each page."""
            canvas.saveState()
            page_num = doc.page
            page_count[0] = page_num

            # Header bar
            canvas.setFillColor(navy)
            canvas.rect(margin, page_size[1] - margin - 0.5 * cm,
                        page_size[0] - 2 * margin, 0.4 * cm, fill=True, stroke=False)
            canvas.setFillColor(colors.white)
            canvas.setFont("Helvetica-Bold", 7)
            canvas.drawString(margin + 0.1 * cm,
                              page_size[1] - margin - 0.32 * cm, config.title)
            canvas.drawRightString(page_size[0] - margin - 0.1 * cm,
                                   page_size[1] - margin - 0.32 * cm,
                                   f"LifeLedger · {date.today().strftime('%B %Y')}")

            # Footer
            canvas.setFillColor(colors.HexColor("#888888"))
            canvas.setFont("Helvetica", 7)
            canvas.drawString(margin,
                              margin * 0.6,
                              "This report is for planning purposes only. "
                              "Not financial advice.")
            canvas.drawRightString(page_size[0] - margin,
                                   margin * 0.6,
                                   f"Page {page_num}")

            # Watermark
            if config.watermark:
                canvas.saveState()
                canvas.setFont("Helvetica-Bold", 60)
                canvas.setFillColor(colors.Color(0.8, 0, 0, alpha=0.07))
                canvas.translate(page_size[0] / 2, page_size[1] / 2)
                canvas.rotate(45)
                canvas.drawCentredString(0, 0, config.watermark)
                canvas.restoreState()

            canvas.restoreState()

        doc = SimpleDocTemplate(
            output_path,
            pagesize=page_size,
            leftMargin=margin, rightMargin=margin,
            topMargin=margin + 0.7 * cm, bottomMargin=margin + 0.3 * cm,
            title=config.title,
            author=config.prepared_by,
            subject="LifeLedger Financial Plan",
        )
        doc.build(flowables, onFirstPage=header_footer, onLaterPages=header_footer)
        return page_count[0]

    # ------------------------------------------------------------------
    # Step 6: Drive upload
    # ------------------------------------------------------------------

    def _upload_to_drive(self, config: ReportConfig, output_path: str) -> Optional[str]:
        """
        @brief Upload the generated PDF to Google Drive.

        @param config       ReportConfig with drive_folder setting.
        @param output_path  Path to the PDF file.
        @return             Google Drive share URL or None on failure.
        """
        try:
            from backend.persistence.drive import DriveClient
            client = DriveClient(project_root=self._root)
            url = client.upload_file(
                local_path=output_path,
                drive_folder=config.drive_folder,
            )
            logger.info("Uploaded report to Drive: %s", url)
            return url
        except Exception as exc:
            logger.error("Drive upload failed: %s — proceeding without upload", exc)
            return None

    # ------------------------------------------------------------------
    # Dependency check
    # ------------------------------------------------------------------

    @staticmethod
    def _check_dependencies() -> None:
        """
        @brief Check that ReportLab is installed.

        @raises ImportError  If reportlab is not available.
        """
        try:
            import reportlab  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "ReportLab is required for PDF report generation. "
                "Install it with: pip install reportlab>=4.1\n"
                "Then restart the LifeLedger API."
            ) from exc


# ---------------------------------------------------------------------------
# YAML config loader
# ---------------------------------------------------------------------------


def load_report_config(path: str) -> ReportConfig:
    """
    @brief Load a ReportConfig from a YAML file.

    Expected top-level key: ``report``.

    @param path  Filesystem path to the YAML config file.
    @return      Populated ReportConfig.
    @raises FileNotFoundError  If the file does not exist.
    @raises yaml.YAMLError     If the file is not valid YAML.
    """
    logger.info("Loading report config from: %s", path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Report config not found: %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise

    if not isinstance(raw, dict) or "report" not in raw:
        raise ValueError(f"YAML '{path}' must have a top-level 'report' key.")

    r = raw["report"]
    return ReportConfig(
        title=str(r.get("title", "LifeLedger Financial Plan")),
        subtitle=str(r.get("subtitle", "")),
        prepared_for=str(r.get("prepared_for", "")),
        prepared_by=str(r.get("prepared_by", "LifeLedger")),
        scenario_path=str(r.get("scenario_path", "data/scenarios/base.yaml")),
        preset=str(r.get("preset", "full_annual")),
        sections=list(r.get("sections", [])),
        charts=list(r.get("charts", [])),
        include_monte_carlo=bool(r.get("include_monte_carlo", True)),
        mc_simulations=int(r.get("mc_simulations", 500)),
        paper_size=str(r.get("paper_size", "A4")),
        colour_scheme=str(r.get("colour_scheme", "navy_teal")),
        watermark=r.get("watermark"),
        output_path=r.get("output_path"),
        output_filename=str(r.get("output_filename", "lifeledger_{date}_{name}.pdf")),
        chart_dpi=int(r.get("chart_dpi", 150)),
        chart_width_inches=float(r.get("chart_width_inches", 10.0)),
        chart_height_inches=float(r.get("chart_height_inches", 5.0)),
        include_toc=bool(r.get("include_toc", True)),
        upload_to_drive=bool(r.get("upload_to_drive", False)),
        drive_folder=str(r.get("drive_folder", "LifeLedger/exports")),
        date_range_start=int(r.get("date_range_start", 2025)),
        date_range_end=int(r.get("date_range_end", 2075)),
        enabled=bool(r.get("enabled", True)),
        notes=str(r.get("notes", "")),
    )
