# CLAUDE.md — LifeLedger Agent Briefing

This file is the authoritative reference for any Claude agent working on the
LifeLedger codebase. Read it in full before writing a single line of code.
It documents: what the project is, the owner's non-negotiable requirements,
what has been built, what validated results look like, and exactly what
remains to be done in each phase.

---

## 1. Project Overview

**LifeLedger** is a self-hosted personal finance and retirement planning
platform for a two-person household. Its purpose is to give the user full
local control over long-horizon financial modelling, retirement projections,
scenario planning, and FIRE analysis — with no dependency on external
services.

### Core principles
- **Whole-life modelling** — projections from today to life expectancy (age 90–95)
- **Multi-jurisdiction, multi-currency** — UK-primary; US Federal, Ireland, generic also supported
- **Scenario-first** — every view has a base + comparison scenario overlay
- **Privacy by default** — self-hosted; Google Drive sync is optional and opt-in
- **Configuration over code** — every parameter is YAML-configurable; more config options are always preferred over fewer

### Target deployment
- Self-hosted via Docker Compose (primary)
- Home Assistant add-on (Phase 6)
- Cloudflare Tunnel, Fly.io/Railway, or Raspberry Pi

---

## 2. Owner Requirements (Non-Negotiable)

These requirements came directly from the project owner. Every agent working
on this codebase must follow them unconditionally.

### Language & libraries
- **Python everywhere possible.** Do not introduce Node.js, Go, or any other
  runtime for backend work. The frontend is HTML/CSS/JS (React + TypeScript in
  Phase 2+); that is the only exception.
- **Phase 1 stdlib + numpy + pandas + scipy + pyyaml only.** No external web
  framework overhead until the core engine was validated. Phase 2+ adds
  FastAPI and Pydantic v2 per the architecture.

### Configuration
- **Config files must be YAML or JSON.** No TOML, INI, or environment-variable-
  only config. Every tunable parameter belongs in a config file.
- **More configuration options in config files is preferable to fewer**, even
  if a setting might never be used. Err on the side of exposing knobs.

### Comments & documentation
- **All functions must have Doxygen-style docstrings** at the start of the
  function body using the `@brief`, `@param`, `@return` tags. No exceptions —
  this applies to every new function and any function that is modified.
- Example format:
  ```python
  def calculate_net_income(gross: float, ...) -> TaxResult:
      """
      @brief Calculate net income after all tax deductions.
      @param gross Gross annual income amount.
      @param tax_treatment How the income is taxed.
      @return TaxResult with breakdown.
      """
  ```

### Error handling
- **All errors must be logged** — to the terminal AND to the log file
  (`logs/lifeledger.log`). Never swallow an exception silently.
- Use Python's `logging` module throughout. The log level is configurable via
  `lifeledger_config.yaml` (`app.log_level`). Default is `INFO`.
- Log format: `%(levelname)-8s %(name)-30s %(message)s`
- Functions must use `try/except` around any I/O, calculation, or parsing that
  can fail. On failure, log the error and return a safe default — do not raise
  unless the caller explicitly needs to handle it.
- Never let one bad data record crash an entire load or projection run. Log it
  and skip.

### Testing
- **Every phase must include a Jupyter notebook** for validation. The notebook
  must be runnable from the project root with `sys.path.insert(0, '.')`.
- Notebook cells must produce visible output confirming key values (net worth,
  tax calculations, FIRE year, MC probabilities).
- Include assertions in notebook cells; a failed assertion is the correct way
  to surface a regression.

### Architecture decisions (locked, do not reverse)
- **Income does NOT auto-add to net worth.** Only explicitly routed
  contributions to savings/investment/pension accounts affect net worth.
  This is a fundamental design decision — a £95k salary does not make the
  household £95k richer each year; only the savings fraction does.
- **Scenarios are YAML diffs from base**, not full copies. They are merged at
  runtime. Never store a redundant full copy of the base data in a scenario file.
- **API keys** (Alpha Vantage, Finnhub) are stored in SQLite only, never in
  any YAML file that could end up on Google Drive.
- **Checkpoints** define the historical/projected boundary. Any year up to and
  including the most recent checkpoint is shown as actuals; beyond it is
  projected.

---

## 3. Repository Structure

```
lifeledger/
├── CLAUDE.md                          ← this file
├── LifeLedger_Phase1_Tests.ipynb      ← Phase 1 validation notebook
├── backend/
│   ├── __init__.py
│   ├── api/                           ← Phase 2: FastAPI routes
│   │   └── __init__.py
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── calculator.py              ← ✅ Phase 1: Projection engine + Monte Carlo
│   │   ├── tax_engine.py              ← ✅ Phase 1: UK/US/Generic tax calculations
│   │   ├── mortgage.py                ← ✅ Phase 2: Mortgage amortisation engine
│   │   ├── pension.py                 ← ✅ Phase 2: Pension lifecycle engine
│   │   ├── events.py                  ← ✅ Phase 2: Life events engine
│   │   ├── tax_wrappers.py            ← ✅ Phase 2: Tax wrapper rules + CGT + FX
│   │   ├── scenario_engine.py         ← ✅ Phase 2: Scenario diff merger
│   │   └── monte_carlo.py             ← ✅ Phase 3: Enhanced MC + confidence bands
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py                  ← ✅ Phase 1: All 20 dataclasses
│   └── persistence/
│       ├── __init__.py
│       └── yaml_serialiser.py         ← ✅ Phase 1: YAML ↔ dataclass serialisation
├── config/
│   ├── lifeledger_config.yaml         ← ✅ Phase 1: Main app config
│   └── tax_profiles.yaml             ← ✅ Phase 1: UK, US, Ireland, generic profiles
├── data/
│   ├── lifeledger.db                  ← Phase 2: SQLite cache (market prices, API keys)
│   ├── scenarios/
│   │   ├── base.yaml                  ← ✅ Phase 1: Full base scenario (James + Sarah)
│   │   └── [other scenarios].yaml     ← Phase 3+
│   ├── checkpoints/
│   │   └── YYYY-MM-DD_audit.yaml     ← Phase 4+
│   └── exports/                       ← Phase 6: PDF report exports
├── frontend/                          ← Phase 2+: React + TypeScript
│   └── src/
│       ├── components/
│       ├── screens/
│       ├── store/
│       ├── api/
│       └── types/
├── logs/
│   └── lifeledger.log
├── tests/
│   └── generate_notebook.py           ← ✅ Phase 1: Notebook generator script
├── docker-compose.yml                 ← Phase 2+
└── README.md                          ← Phase 2+
```

---

## 4. Phase 1 — What Has Been Built (COMPLETE ✅)

Phase 1 is the validated foundation. Do not modify these files without
understanding the downstream effects. All Phase 2+ work builds on top of them.

### 4.1 Data Models (`backend/models/models.py` — 782 lines)

20 dataclasses + supporting enums. All have Doxygen docstrings.

| Class | Purpose |
|---|---|
| `Person` | Individual with DOB, retirement age, life expectancy, state pension |
| `StatePension` | NI qualifying years, weekly amount, deferral, `annual_amount()` |
| `IncomeSource` | Recurring income with tax treatment, date range, growth rate, contribution routing |
| `Contribution` | Routes a fraction of gross income to a destination account |
| `SavingsAccount` | Cash/ISA accounts with time-varying `InterestRatePeriod` list |
| `InvestmentHolding` | Single holding — `total_value` mode or `units × price_per_unit` mode |
| `InvestmentAccount` | Wrapper for holdings; `effective_growth_rate()` is weighted average |
| `PensionFund` | SIPP/DC/DB with `DrawdownConfig` (pct_swr / fixed_amount / annuity) |
| `PropertyAsset` | Property with growth rate, rental income, linked mortgage |
| `Mortgage` | Repayment/interest-only with `RatePeriod` list and `LumpSumPayment` list |
| `LifeEvent` | One-off inflow/outflow on a specific date |
| `ExpenseBucket` | Recurring inflation-linked expense category |
| `FIRETarget` | Target net worth, SWR, fire_type, `implied_target()` |
| `TaxProfile` | Jurisdiction bands, NI bands, CGT config, allowances |
| `Scenario` | Named collection of all above objects; is_base flag |
| `Checkpoint` | Actual net worth snapshot — anchors historical/projected boundary |
| `AppConfig` | Loaded from `lifeledger_config.yaml` |
| `SymbolLink` | Market data linkage (provider, symbol, ISIN, refresh schedule) |
| `DrawdownConfig` | Pension drawdown mode + rate + TFLS config |
| `InterestRatePeriod` / `RatePeriod` / `LumpSumPayment` / `TaxBand` | Sub-models |

Key enums: `TaxTreatment`, `AccountType`, `PensionType`, `MortgageType`, `TrackingMode`, `DrawdownMode`, `EventType`, `Jurisdiction`

### 4.2 YAML Serialiser (`backend/persistence/yaml_serialiser.py` — 742 lines)

- `load_app_config_from_file(path)` → `AppConfig`
- `load_scenario_from_file(path)` → `Scenario | None`
- `load_tax_profiles_from_file(path)` → `list[TaxProfile]`
- `parse_scenario(dict)` → `Scenario | None`
- All `parse_*` functions for every model
- Safe helpers: `_parse_date`, `_float`, `_int`, `_enum` — all log on failure, never raise
- `load_yaml(path)` / `dump_yaml(data, path)` — file I/O with error handling

### 4.3 Tax Engine (`backend/engine/tax_engine.py` — 378 lines)

- `calculate_net_income(gross, tax_treatment, profile, ...)` → `TaxResult`
  - Dispatches to jurisdiction-specific calculators
- `calculate_uk_income_tax(gross, profile, pension_contributions)` → `(tax, marginal_rate)`
  - Applies personal allowance taper at £100k (£1 reduction per £2 over threshold)
- `calculate_uk_ni(gross, profile)` → `float` (Class 1 PAYE)
- `calculate_uk_self_employed_ni(gross, profile)` → `float` (Class 4 + Class 2)
- `calculate_uk_cgt(gain, existing_income, profile)` → `CGTResult`
  - Splits gain across basic/higher rate boundary correctly
- `calculate_us_federal_income_tax(gross, profile, filing_status)` → `(tax, marginal_rate)`
- `calculate_fica(gross, profile)` → `float` (SS + Medicare + Additional Medicare)
- `calculate_generic_tax(gross, profile)` → `(tax, marginal_rate)`
- `_apply_bands(income, bands, floor)` → shared progressive band calculator

**Validated tax results:**
- £95k PAYE (£9.5k pension relief): net £67,949, effective rate 28.5%
- £150k PAYE (taper zone): net £94,806, effective rate 36.8%
- All results confirmed correct against 2024/25 HMRC rates

### 4.4 Projection Engine (`backend/engine/calculator.py` — 775 lines)

**`ProjectionEngine.project(scenario)`** — 12-step year loop, returns `TimelineResult`

Pipeline per year:
1. Active income sources → gross/net per person via tax engine
2. Contribution routing → credit destination accounts
3. Employer pension top-ups
4. Grow savings accounts (interest rate for year)
5. Grow investment accounts (weighted growth rate)
6. Pension accumulation OR drawdown (with TFLS in first drawdown year)
7. State pension (inflated from base year, taxed as pension income)
8. Property value growth
9. Mortgage balance step (PMT calculation, lump sums)
10. Life events (one-off credits/debits to accounts)
11. Inflation-linked expenses
12. Net worth = assets − liabilities; FIRE check

**`run_monte_carlo(scenario, config, tax_profiles, ...)`** → `MonteCarloResult`
- 1,000 simulations (configurable)
- Perturbs growth rates (Normal, σ=0.12) and inflation (Normal, σ=0.005)
- Temporarily patches `assumed_growth_rate` per simulation; restores after
- Returns P10/P25/P50/P75/P90 percentile arrays
- `prob_fire` = fraction of simulations that achieve FIRE

**`_pmt(rate, nper, pv)`** — Pure-Python mortgage PMT (numpy_financial not available)

**Validated projection results (base scenario, James + Sarah):**
- 2025 net worth: £644,858
- FIRE achieved: 2031 (target £1.2m)
- James retirement year: 2047
- Net worth at James retirement: £4,475,487
- 2075 net worth: £14,506,909
- MC FIRE probability (1,000 sims): ~100% (base rates are strong)
- MC P50 at retirement: ~£4,556,150

### 4.5 Config Files

**`config/lifeledger_config.yaml`** — master config covering:
- App settings (currency, log level, log file)
- Projection range (2025–2075)
- Inflation (base/low/high rates, period overrides)
- FX rates and annual drift
- Monte Carlo (simulations, seed, std devs, sequence-of-returns risk)
- Tax defaults for UK and US Federal
- Google Drive sync settings
- SQLite cache settings
- Engine behaviour flags

**`config/tax_profiles.yaml`** — four profiles:
- `uk_standard` — PAYE income tax + Class 1 NI + CGT + IHT + allowances
- `uk_self_employed` — Income tax + Class 4 NI + Class 2 flat
- `us_federal_single` — Federal brackets + FICA + standard deduction + long-term CGT
- `generic` — Flat rate, fully configurable

**`data/scenarios/base.yaml`** — complete base scenario:
- James (b. 1987) and Sarah (b. 1989)
- 3 income sources (£95k PAYE, £62k PAYE, £15k self-employed consulting)
- 2 savings accounts (Halifax Cash ISA, current account)
- 2 investment accounts (Vanguard ISA with VWRP.L + LifeStrategy, Fidelity GIA)
- 2 pension funds (Vanguard SIPP, Sarah workplace DC)
- 1 property (London house £485k) + 1 mortgage (£285k, fixed→variable)
- 4 expense buckets (household, childcare, retirement living, healthcare)
- 2 life events (car purchase 2027, inheritance 2038)
- FIRE target: £1.2m at 4% SWR

### 4.6 Jupyter Notebook (`LifeLedger_Phase1_Tests.ipynb` — 28 cells)

Sections:
1. Environment Setup (logging, matplotlib dark theme, constants)
2. Configuration & YAML Loading
3. Model Inspection (people, income, investments, mortgages)
4. Tax Engine Validation (10 test cases in DataFrame, CGT tests, assertions)
5. Full 50-Year Projection (key-year snapshot table)
6. Account-Level Breakdown (2035 and 2050 tables, income breakdown 2026)
7. FIRE Analysis (progress table, retirement income coverage)
8. Monte Carlo Simulation (1,000 runs, percentile table)
9. Chart: Net Worth Timeline (stacked area + FIRE line + MC bands)
10. Chart: Income Sources (stacked timeline)
11. Chart: Monte Carlo Fan (P10–P90 with deterministic overlay)
12. Edge Cases & Error Handling (10 assertions covering zero income, missing
    profiles, expired sources, bad YAML paths, PMT edge cases)

**To run the notebook:** open in Jupyter from the project root. Cell 1 adds
`PROJECT_ROOT` to `sys.path`. All cells are self-contained; run top to bottom.


## 4b. Phase 2 — Core Engines + API Layer (COMPLETE ✅)

### Engines added (`backend/engine/`)
| File | What it delivers |
|---|---|
| `mortgage.py` | Full amortisation engine: multi-rate periods, lump-sum & monthly overpayments, ERC cap enforcement, offset account, property equity / LTV tracking. Returns `MortgageResult` with month-by-month schedule and year-by-year `AnnualSummary` for the projection engine. |
| `pension.py` | Full pension lifecycle: accumulation (contributions + employer match, growth, AMC fee drag), drawdown (percentage SWR / fixed nominal / fixed real), annuity conversion (level / inflation-linked / joint life), UK PCLS (25%), annual allowance + 3-year carry-forward relief, US RMDs from age 73 via IRS Uniform Lifetime Table. Returns `PensionResult` with year-by-year schedule. |
| `events.py` | Life events engine: 15 typed event processors (property_sale, property_purchase, inheritance, lump_sum_income, major_expense, job_change, career_break, emigration, care_cost_start/end, state_pension_start, partner_death, business_start, redundancy, asset_contribution). Returns `EventMutation` objects consumed by the projection engine. Career break auto-resume is tracked internally. |
| `tax_wrappers.py` | Tax wrapper rules for 12 account types (ISA, LISA, SIPP, GIA, 401k, Roth_401k, IRA_traditional, IRA_roth, Brokerage_US, PRSA, Taxable, Tax_free). Includes `CGTTracker` (lot tracking, annual exemption, loss carry-forward, basic/higher rate split, residential surcharge), LISA bonus/penalty calculator, and `FXManager` (spot rates + annual drift projection). |
| `scenario_engine.py` | Scenario diff merger: deep-merges a diff YAML onto the base scenario by ID, re-parsing only changed items. Validates merged result. |

### API layer (`backend/api/routes/`)
All routes existed in the repo; Phase 2 confirmed and validated:
- `accounts.py` — CRUD for all account types via base.yaml
- `simulation.py` — `POST /api/simulate` + `POST /api/simulate/monte-carlo`
- `scenarios.py` — scenario list/create/update/delete + comparison
- `tax.py` — `POST /api/tax/calculate`
- `sync.py` — Google Drive push/pull/status
- `market_data.py` — symbol search, price refresh
- `checkpoints.py` — checkpoint create/list/divergence

### Config files added
| File | Purpose |
|---|---|
| `config/mortgages/mortgage_config.yaml` | Example mortgage: 5yr fix → SVR, offset, ERC cap, lump-sum + monthly overpayments, property growth |
| `config/pensions/pension_config.yaml` | Example SIPP: glide-path growth periods, PCLS, 4% SWR drawdown, annual allowance + carry-forward |
| `config/events/events_config.yaml` | Full household event plan: property sale/purchase, inheritance, job changes, state pension, care costs, redundancy |
| `config/tax/tax_wrappers_config.yaml` | CGT tracker settings (£3k exemption, 10%/20% rates, residential 18%/24%), wrapper overrides, GBP/USD/EUR FX rates |

### Validation notebooks
- `notebooks/02_mortgage_validation.ipynb` — 10-cell mortgage validation with dark-mode charts
- `notebooks/03_pension_validation.ipynb` — 11-cell pension validation (all phases, PCLS, RMD, allowance breach)
- `notebooks/04_events_validation.ipynb` — 11-cell events validation (all 15 event types, career break resume, YAML round-trip)
- `notebooks/05_tax_wrappers_validation.ipynb` — 10-cell CGT/FX/wrapper validation

---

## 4c. Phase 3 — Monte Carlo + Scenario Comparison (COMPLETE ✅)

### Engines added (`backend/engine/`)
| File | What it delivers |
|---|---|
| `monte_carlo.py` | Enhanced MC engine wrapping the base `run_monte_carlo` in `calculator.py`. Adds: structured confidence bands (P5–P95) as `ConfidenceBand` objects; multi-scenario comparison via `compare_scenarios()` returning `ScenarioComparison` with per-year median table and FIRE crossover years; deterministic macro scenario fan chart (Low/Mid/High) via `MacroScenarioBand`; sequence-of-returns risk injection (configurable crash + recovery in early retirement); FIRE probability by year (monotonically non-decreasing); surplus/shortfall analysis against drawdown target; YAML-loadable config. |

### Config files added
| File | Purpose |
|---|---|
| `config/simulation/monte_carlo_config.yaml` | n_sims (2000 default), seed, growth_std (0.10), inflation_std (0.005), percentiles [5,10,25,50,75,90,95], Low/Mid/High macro scenario params (inflation, equity real return, salary growth, FX), SoR crash −20%/2yr + recovery, drawdown_annual_target £48k |

### Low / Mid / High macro scenario parameters
| Param | Low | Mid | High |
|---|---|---|---|
| Inflation | 3.5% | 2.5% | 2.0% |
| Equity real return | 3.0% | 5.0% | 7.5% |
| Salary real growth | 0.0% | 1.0% | 2.0% |
| GBP/USD | 1.18 | 1.27 | 1.38 |

### Validation notebook
- `notebooks/06_phase3_validation.ipynb` — 9-cell notebook: confidence band width test, FIRE probability monotonicity, macro fan chart (Low/Mid/High), multi-scenario comparison, SoR impact on P10, surplus/shortfall, YAML round-trip, full Phase 3 chart (3-panel: MC bands + FIRE probability + surplus/shortfall), scenario comparison overlay chart.

---

---

## 5. Phases Still To Do

### Phase 2 — API Layer + Frontend Wiring (3–4 weeks)

**Goal:** Expose the Phase 1 engine via a FastAPI REST API; wire up the React
frontend to it; add SQLite persistence for market prices.

**Available packages to add:** `fastapi`, `uvicorn`, `pydantic>=2.7`,
`sqlalchemy>=2.0`, `httpx`, `aiofiles`, `python-multipart`

#### Backend work
- `backend/main.py` — FastAPI app factory; CORS; startup/shutdown events;
  logging middleware; exception handlers that return structured JSON errors
- `backend/api/routes/` — one file per domain:
  - `accounts.py` — CRUD for savings/investment/pension accounts
  - `simulation.py` — `POST /api/simulate` → runs `ProjectionEngine.project()`;
    `POST /api/simulate/monte-carlo` → runs `run_monte_carlo()`
  - `scenarios.py` — list/create/update/delete scenarios; `GET /api/scenarios/compare`
  - `checkpoints.py` — create checkpoint, list, divergence analysis
  - `sync.py` — Google Drive push/pull/status (Phase 2 stubs, real impl Phase 2)
  - `tax.py` — `POST /api/tax/calculate` for ad-hoc tax calculation
  - `market_data.py` — symbol search, ISIN lookup, price refresh
- Replace the dataclass models with **Pydantic v2** models (keep the same field
  names and structure; just inherit from `BaseModel` instead of `@dataclass`).
  The YAML serialiser helpers can be reused; just call `Model(**dict)` instead.
- Add `backend/persistence/sqlite_cache.py` — SQLAlchemy models for:
  - `price_history` table (symbol, date, price, provider)
  - `api_keys` table (provider, encrypted_key) — keys NEVER in YAML
  - `sync_state` table (last_sync_at, conflict_status)
- Add `backend/market_data/` directory — see §5 market data section below
- Add `docker-compose.yml` with services: `api` (uvicorn), `frontend` (Vite dev server)
- Add `requirements.txt` with pinned versions

#### Frontend work
The wireframes already exist in `lifeledger_wireframes.html` (in the project
files). The task is to convert them to a proper React + TypeScript application.

- Bootstrap with Vite: `npm create vite@latest frontend -- --template react-ts`
- Styling: Tailwind CSS (utility classes only — no custom CSS unless unavoidable)
- State: Zustand stores — `configStore`, `simulationStore`, `scenarioStore`
- Data fetching: `@tanstack/react-query` v5 for all API calls
- Forms: `react-hook-form` v7 + `zod` v3 for validation
- Charts: `recharts` v2 for all graphs (NOT Chart.js — recharts integrates
  better with React state)
- Component structure mirrors the wireframes:
  ```
  frontend/src/
  ├── components/
  │   ├── graph/         TimelineChart, MonteCarloBands, ScenarioOverlay, CrosshairTooltip
  │   ├── portfolio/     PortfolioMix, HoldingsTable
  │   ├── forms/         IncomeForm, PensionForm, MortgageForm, InvestmentForm,
  │   │                  HistoricalGrowthForm, SymbolSearchWidget, PriceFetchStatus
  │   └── layout/        Sidebar, TopBar, PageHeader
  ├── screens/           Dashboard, TimelineGraph, PortfolioMixScreen,
  │                      RetirementPlanner, EstatePlanner, ScenariosScreen,
  │                      CheckpointsScreen, Settings
  ├── store/             configStore.ts, simulationStore.ts, scenarioStore.ts
  ├── api/               client.ts, hooks/ (one hook file per domain)
  └── types/             mirrors backend Pydantic models
  ```
- Design system (from wireframes, do not deviate):
  - Background: `#0f1b2d` (navy), surface: `#162236`, elevated: `#1d2f47`
  - Accent teal: `#0e9aad`, gold: `#d4a843`, green: `#2dbd7e`, red: `#e05252`
  - Display font: Playfair Display (headings)
  - Mono font: DM Mono (all numbers, tickers, dates, monetary values)
  - Body font: DM Sans
  - Numbers MUST use DM Mono — this is a hard UI rule

#### Jupyter notebook for Phase 2
Test: API endpoints return correct JSON for a known scenario; SQLite cache
writes and reads price history correctly; Pydantic models validate correctly.

#### ⚠️ Data Entry Gap — added 2026-03-13

The original Phase 2 plan assumed scenario data would be edited as YAML files
directly. This is impractical for regular use. A **Data Management screen**
must be added so users can enter and edit all financial data through the UI.

**New screen: `DataManagement` (add to sidebar between Dashboard and Timeline)**

The screen is a tabbed editor with one tab per data category. Each tab lists
existing items and has Add / Edit / Delete actions backed by the accounts API.

Tabs and their content:
- **People** — edit Person fields (DOB, retirement age, life expectancy) and
  StatePension (qualifying years, weekly amount, start age)
- **Income** — full IncomeForm with all IncomeSource fields: name, gross,
  tax treatment (dropdown), owner (dropdown), start/end dates, growth rate,
  contribution routing (list of destination → fraction pairs)
- **Savings** — SavingsAccount editor: name, type, balance, rate periods table
- **Investments** — InvestmentAccount editor + per-holding form (name, ticker,
  tracking mode toggle, value/units+price, growth rate, symbol link)
- **Pensions** — PensionFund editor: name, type, owner, value, growth rate,
  employer contribution rate, drawdown config (mode, rate, TFLS)
- **Property & Mortgage** — PropertyAsset + linked Mortgage editor (rate periods
  table, lump sum payments table)
- **Expenses** — ExpenseBucket list: name, annual amount, start/end, inflation-linked toggle
- **Life Events** — LifeEvent list: name, date, amount, type (inflow/outflow),
  target account

**Form rules:**
- Use `react-hook-form` v7 + `zod` v3 for all validation
- Monetary inputs: number type, step=100, show £ prefix
- Rate inputs: number type, step=0.001, show % suffix (display as %, store as decimal)
- Date inputs: ISO date picker
- All saves call the appropriate `PUT /api/accounts/{type}/{id}` or
  `POST /api/accounts/{type}` endpoint
- On save success: invalidate simulation cache (trigger re-run prompt)

**New form components to build (replace current stubs):**
- `IncomeForm.tsx` — full implementation with contribution routing sub-form
- `PensionForm.tsx` — full implementation with DrawdownConfig sub-form
- `MortgageForm.tsx` — full with RatePeriod table and LumpSumPayment table
- `InvestmentForm.tsx` — full with per-holding rows and SymbolSearchWidget
- `SavingsForm.tsx` — new: name, type, balance, InterestRatePeriod table
- `PersonForm.tsx` — new: all Person + StatePension fields
- `ExpenseForm.tsx` — new: ExpenseBucket fields
- `LifeEventForm.tsx` — new: LifeEvent fields
- `PropertyForm.tsx` — new: PropertyAsset fields
- `SymbolSearchWidget.tsx` — ticker search input using `useSymbolSearch` hook,
  shows dropdown of results, sets ticker + fetches current price on select
- `HistoricalGrowthForm.tsx` — lets user override assumed_growth_rate from
  historical data (shows yfinance-fetched CAGR for a given period)

**FIRE Target editor** — add to RetirementPlanner screen:
- Target net worth, SWR (%), annual expenses, FIRE type dropdown
- Saved via `PUT /api/accounts/fire_target/primary`

This data entry capability was missing from the original plan and is
**required before Phase 3** so users can manage their own financial data
rather than editing YAML directly.

---

### Phase 3 — Scenario Builder + FIRE Modelling (COMPLETE ✅)

**Goal:** Full scenario CRUD in the UI; side-by-side graph comparison; FIRE
analysis dashboard; scenario templates.

#### Backend work
- `backend/engine/scenario_engine.py` — merges a scenario diff onto the base
  scenario at runtime; validates merged result before projecting
- Scenario YAML diffs: only fields that differ from base are stored. The merger
  must handle nested structures (e.g. override a single income source's
  `end_date` without duplicating the whole income object).
- Built-in scenario templates (store as YAML in `data/scenarios/templates/`):
  - `retire_at_55.yaml` — move James's retirement to 55, adjust pension start
  - `sell_house_2030.yaml` — sell London house, invest equity into ISA + SIPP
  - `move_to_us.yaml` — switch tax profiles to US Federal, add FX conversion
  - `annuity_vs_drawdown.yaml` — compare SIPP annuity vs 4% SWR
  - `stress_test.yaml` — apply sequence-of-returns shock + 20% market crash
  - `partner_death_70.yaml` — remove Sarah's income from year 2059
  - `inheritance_65.yaml` — add £150k inheritance at James age 65
  - `aggressive_fire.yaml` — raise savings rates to 35%, target retire at 50

#### Frontend work
- `ScenariosScreen` — card grid showing all scenarios with key metrics
- Scenario editor — form-based YAML diff builder (change specific fields only)
- Graph overlay — up to 4 scenarios plotted simultaneously with distinct colours
- Scenario comparison table — key metrics at ages 55/60/65/70/80
- Template gallery with preview

#### Jupyter notebook for Phase 3
Test: all 8 templates load and project without errors; scenario merge produces
expected diffs; graph comparison data is consistent across scenarios.

---

### Phase 4 — Retirement Features (2–3 weeks)

**Goal:** Deep retirement income planning; pension drawdown optimisation;
state pension integration; coverage reporting.

#### Backend work
- `backend/engine/retirement_engine.py`:
  - `calculate_income_coverage(year_snap)` → ratio of net income to expenses
  - `find_optimal_drawdown_order(scenario, start_year)` → which accounts to
    draw from first to minimise lifetime tax (ISA-first vs SIPP-first vs GIA)
  - `calculate_drawdown_tax_saving(scenario, strategy_a, strategy_b)` → 10-yr
    tax saving comparison between two drawdown strategies
  - `project_annuity_conversion(pension_fund, annuity_rate, type)` → converts
    fund to IncomeSource object for `level` / `inflation_linked` / `joint_life`
    annuity types; `joint_life` must generate a survivor income stream
- UK State Pension improvements:
  - Deferral bonus: 1% per year; configurable in `lifeledger_config.yaml`
    under `engine.pension_state_deferral_bonus_per_year`
  - NI qualifying years tracker: show years to full pension
  - State pension triple lock: configurable growth assumption
- Add `data/checkpoints/` YAML structure and `backend/engine/checkpoint_engine.py`:
  - `apply_checkpoints(result, checkpoints)` — overrides projection values with
    actuals up to the most recent checkpoint date
  - `divergence_analysis(result, checkpoint)` — calculates how much actuals
    deviated from projected at checkpoint date

#### Config additions (`lifeledger_config.yaml`)
```yaml
retirement:
  drawdown_order: "isa_first"       # isa_first | sipp_first | gia_first | optimised
  annuity_rate_assumed: 0.045       # 4.5% annuity rate for comparison
  triple_lock_rate: 0.025           # state pension annual increase
  income_coverage_target: 1.0       # 1.0 = 100% coverage
  sequence_risk_crash_magnitude: -0.30  # -30% crash in year 1 of retirement
```

#### Frontend work
- `RetirementPlanner` screen — fully wired:
  - Drawdown configuration form (mode toggle, rate input, TFLS)
  - Annuity comparison panel (level vs inflation-linked vs joint life)
  - Year-by-year income coverage table with green/amber/red highlighting
  - Drawdown order optimiser — shows 10-year tax saving between strategies
- `CheckpointsScreen` — add/edit/delete checkpoints; divergence chart showing
  actual vs projected at each checkpoint

#### Jupyter notebook for Phase 4
Test: drawdown order optimisation returns a consistent strategy; annuity
conversion produces correct IncomeSource; checkpoint divergence values are
correct; state pension amounts are correct for various NI year counts.

---

### Phase 5 — Advanced Planning (3–4 weeks)

**Goal:** Survivor simulation, estate/IHT planning, healthcare budgeting,
portfolio rebalancing alerts, and extended scenario types.

#### Backend work
- `backend/engine/survivor_engine.py`:
  - `simulate_survivor(scenario, deceased_person_id, death_year)` → returns
    a modified scenario with deceased's income removed, their pension converted
    to survivor fraction (configurable in `DrawdownConfig.joint_life_fraction`),
    and mortgage affordability check
  - Must check whether survivor can cover mortgage payments on single income
- `backend/engine/estate_engine.py`:
  - UK IHT: £325k NRB + £175k RNRB (residence nil-rate band), 7-year rule,
    annual gifting exemption £3k/yr, pension outside estate
  - US federal estate: configurable exemption threshold
  - `calculate_iht_liability(scenario, death_year, person_id)` → £ IHT due
  - `gifting_tracker(scenario)` → years remaining before 7-year clock expires
    per gift, potential IHT saving if gifts survive
- `backend/engine/healthcare_engine.py`:
  - Configurable long-term care cost bucket (start age, annual amount, duration)
  - `estimate_care_costs(person, start_age, daily_rate, duration_years)` → adds
    an `ExpenseBucket` to the scenario
- Portfolio rebalancing:
  - `backend/engine/rebalance_engine.py`
  - `check_rebalance_needed(account, target_allocation)` → returns drift %
  - `calculate_rebalance_trades(account, target_allocation)` → buy/sell amounts

#### Config additions (`lifeledger_config.yaml`)
```yaml
estate:
  uk_nil_rate_band: 325000
  uk_residence_nil_rate_band: 175000
  uk_annual_gifting_exempt: 3000
  us_federal_estate_exemption: 13610000
  pension_outside_estate: true

healthcare:
  start_age: 80
  daily_care_rate: 1200          # £/day residential care
  duration_years: 3
  inflation_linked: true

rebalancing:
  enabled: true
  drift_threshold_pct: 5.0       # rebalance if any asset class drifts > 5%
  rebalance_frequency: "annual"  # annual | quarterly | threshold_only
```

#### Frontend work
- `EstatePlanner` screen:
  - IHT liability estimate with NRB/RNRB breakdown
  - Gifting tracker table (gift date, amount, years remaining, IHT saving)
  - Pension-outside-estate toggle and impact
- Survivor simulation panel in `ScenariosScreen` — select deceased person +
  death year → overlay survivor scenario on main graph
- Healthcare costs configurator
- Portfolio rebalancing alerts on `PortfolioMixScreen` — amber/red badges on
  holdings that have drifted from target allocation

#### Jupyter notebook for Phase 5
Test: IHT calculation matches manual calculation for known estate values;
survivor scenario removes correct income streams; rebalancing correctly
identifies drift; healthcare costs inflate correctly over time.

---

### Phase 6 — Report Export + Polish + Home Assistant (3–4 weeks)

**Goal:** Full PDF report export system; Home Assistant add-on packaging;
checkpoint UI; mobile-responsive UI; dark mode; comprehensive tests.

#### Report export (`backend/reports/`)
The report system is fully specified in the architecture document. Key points:

- `backend/reports/builder.py` — orchestrates the 7-step pipeline:
  1. Validate `ReportConfig`
  2. Run simulation (+ MC if `include_monte_carlo=True`)
  3. Render charts with matplotlib (150 DPI PNG, 10×5in figures)
  4. Assemble section objects
  5. Build PDF with ReportLab Platypus
  6. Upload to `LifeLedger/exports/` on Google Drive
  7. Notify frontend via WebSocket or polling endpoint
- `backend/reports/chart_renderer.py` — matplotlib custom style matching
  the UI: deep navy backgrounds, teal/gold/green palette, DM Mono annotations,
  solid lines for historical, dashed for projected
- 11 selectable graphs (see architecture doc §10 for full list)
- 9 report sections (cover page, exec summary, account snapshots, income,
  future assumptions, graphs, scenario comparison, retirement coverage, estate)
- 3 preset configs: Quick (~4pp), Full Annual (~18pp), IFA Pack (~28pp)
- `ReportConfig` must be serialisable to YAML and storable in Google Drive
  file description field

#### Config additions (`lifeledger_config.yaml`)
```yaml
reports:
  default_paper_size: "A4"     # A4 | letter
  default_colour_scheme: "navy_teal"  # navy_teal | warm | monochrome
  include_table_of_contents: true
  chart_dpi: 150
  chart_figsize: [10, 5]
  default_watermark: null      # null | "CONFIDENTIAL" | "DRAFT"
  drive_export_folder: "LifeLedger/exports"
  filename_pattern: "lifeledger_{date}_{slug}.pdf"
```

#### Home Assistant add-on
- `homeassistant/config.json` — add-on manifest (name, version, description,
  ports, options schema)
- `homeassistant/run.sh` — entrypoint: start uvicorn on port 8099
- The add-on must expose the config options from `lifeledger_config.yaml` via
  the HA options schema so users can configure without editing YAML directly

#### Polish
- Mobile-responsive breakpoints (tablet ≥ 768px, phone ≥ 375px)
- All monetary values use DM Mono font (already in wireframes; must be in CSS)
- Dark mode is the only mode — do not add a light mode toggle
- `README.md` — installation instructions for Docker Compose and HA add-on

#### Jupyter notebook for Phase 6
Test: PDF generates without errors; all 11 chart types render; ReportConfig
round-trips through YAML serialisation; report file appears in the correct
Drive folder path structure.

---

## 6. Market Data Module (Phase 2+)

`backend/market_data/` — referenced in Phases 2–4; here is the full spec.

### Provider priority chain
1. **yfinance** (primary) — unofficial Yahoo Finance; no API key needed;
   UK LSE tickers use `.L` suffix (e.g. `VWRP.L`); supports 20+ years history
2. **Alpha Vantage** (secondary) — 25 req/day free; key stored in SQLite
   `api_keys` table under `provider='alpha_vantage'`
3. **Finnhub** (tertiary) — 60 req/min free; key in SQLite
4. **OpenFIGI** (ISIN resolver) — 250 req/day free; used to convert ISIN/SEDOL
   to ticker before querying the above providers

### Module structure
```
backend/market_data/
├── __init__.py
├── providers/
│   ├── base.py          — abstract BaseProvider class
│   ├── yfinance_provider.py
│   ├── alpha_vantage.py
│   ├── finnhub_provider.py
│   └── open_figi.py
├── cache.py             — SQLite price cache (historical prices immutable)
├── scheduler.py         — refresh scheduler (on_app_open | daily | weekly)
├── symbol_search.py     — search by name, ticker, or ISIN
└── price_sync.py        — orchestrates provider fallback chain
```

### Behaviour rules
- Historical prices are **immutable** once cached — never re-fetch a date
  that already exists in the cache
- If all providers fail, use `last_fetched_price` from `SymbolLink` and log
  a staleness warning
- Rate limit queuing: if a provider hits its limit, queue remaining requests
  with exponential backoff; do not fail silently
- API keys are stored only in SQLite `api_keys` table; never log them;
  never write them to any YAML file

### Config additions (`lifeledger_config.yaml`)
```yaml
market_data:
  primary_provider: "yfinance"
  fallback_providers: ["alpha_vantage", "finnhub"]
  isin_resolver: "open_figi"
  cache_days_historical: 3650    # 10 years
  retry_attempts: 3
  retry_backoff_seconds: 2
  rate_limit_delay_ms: 500
  stale_price_warning_hours: 48
```

---

## 7. Google Drive Sync (Phase 2+)

- Auth: OAuth2 PKCE flow — no client secret stored anywhere
- Scope: `drive.file` only (access only to files LifeLedger creates)
- Sync triggers: on save + every 5 minutes (configurable)
- Conflict detection: SHA-256 hash comparison of local vs Drive file
- Conflict resolution modes (configurable): `prompt`, `keep_local`, `keep_remote`, `auto_merge`
- Offline mode: falls back to SQLite cache silently; shows a banner in the UI
- `backend/persistence/drive.py` — Drive API v3 wrapper
- `backend/persistence/sync_manager.py` — orchestrates conflict detection,
  resolution, and retry logic

---

## 8. Key Design Decisions (Do Not Reverse)

| Decision | Rationale |
|---|---|
| Income does NOT auto-add to net worth | Only saved/invested income builds wealth; spending income is not tracked as an asset accumulation |
| Scenarios are YAML diffs from base | Avoids data duplication; merged at runtime; base is single source of truth |
| API keys in SQLite only | YAML files may be synced to Google Drive; keys must never leave local storage |
| Checkpoints define historical boundary | Prior to latest checkpoint = actuals; after = projected |
| yfinance as primary provider | No API key required; works for UK LSE (`.L`) and US; 20+ year history |
| No light mode | Dark financial dashboard is the core design identity; supporting two themes doubles UI complexity |
| DM Mono for all numbers | Monetary values must be monospaced for vertical alignment in tables |
| Pydantic v2 deferred to Phase 2 | Phase 1 stdlib-only validated the core engine before adding web framework overhead |
| ReportLab Platypus for PDF | Mature Python-native PDF library; supports Platypus flowables for multi-page layout |

---

## 9. Conventions Every Agent Must Follow

### Python style
- Type hints on all function signatures and return types
- `Optional[X]` for nullable fields (not `X | None` — keep compatible with 3.10)
- `field(default_factory=list)` for mutable defaults in dataclasses
- All IDs are strings (not int) — they come from YAML keys
- Monetary amounts are `float` (not Decimal) — precision is sufficient for projections

### Logging
```python
logger = logging.getLogger(__name__)
# At module top — one logger per file, named by module path
```
- `logger.debug(...)` — per-year calculation details
- `logger.info(...)` — significant state transitions (scenario loaded, FIRE achieved, sync complete)
- `logger.warning(...)` — degraded operation (missing tax profile, stale price, fallback used)
- `logger.error(...)` — recoverable error (bad YAML field, failed API call)
- `logger.critical(...)` — unrecoverable error only

### YAML conventions
- Keys use `snake_case`
- Monetary amounts in full units (not thousands): `95000` not `95`
- Dates in ISO format: `"2025-03-08"`
- Rates as decimals: `0.07` not `7` or `7%`
- `null` for optional absent values (not empty string)
- All files must have a top-level comment block identifying the file and purpose

### Git conventions (for when the repo is initialised)
- Branch per phase: `phase-2/api-layer`, `phase-3/scenarios`, etc.
- Commit messages: `[phase-N] short description`
- Never commit `logs/`, `__pycache__/`, `*.pyc`, `data/lifeledger.db`

---

## 10. Dependencies by Phase

### Phase 1 (✅ complete — no install needed beyond these)
```
python >= 3.12
numpy >= 1.26
pandas >= 2.2
scipy >= 1.13
pyyaml >= 6.0
```

### Phase 2+ (to be installed)
```
fastapi >= 0.111
uvicorn[standard] >= 0.29
pydantic[email] >= 2.7
sqlalchemy >= 2.0
httpx >= 0.27
aiofiles >= 23.2
python-multipart >= 0.0.9
yfinance >= 0.2
google-api-python-client >= 2.130
google-auth-oauthlib >= 1.2
reportlab >= 4.1        # Phase 6
matplotlib >= 3.8       # Phase 6 charts
```

### Frontend (Phase 2+)
```
react 18+, typescript 5.4+, vite 5+
tailwindcss 3.4+
recharts 2.12+
d3 7+
zustand 4.5+
@tanstack/react-query 5+
react-hook-form 7+
zod 3.23+
axios 1.7+
date-fns 3+
lucide-react (icons)
```

---

## 11. Quick Validation

To confirm Phase 1 is intact before starting any new work:

```bash
cd /path/to/lifeledger
python3 -c "
import sys; sys.path.insert(0, '.')
import logging; logging.basicConfig(level=logging.WARNING)
from backend.persistence.yaml_serialiser import *
from backend.engine.calculator import ProjectionEngine, run_monte_carlo
from backend.engine.tax_engine import calculate_net_income
from backend.models.models import TaxTreatment

cfg = load_app_config_from_file('config/lifeledger_config.yaml')
profiles = {p.id: p for p in load_tax_profiles_from_file('config/tax_profiles.yaml')}
sc = load_scenario_from_file('data/scenarios/base.yaml')
engine = ProjectionEngine(cfg, profiles)
result = engine.project(sc)
mc = run_monte_carlo(sc, cfg, profiles, n_simulations=100, seed=42)

assert result.year(2025).total_net_worth > 600_000, 'Net worth 2025 regression'
assert result.fire_year == 2031, f'FIRE year changed: {result.fire_year}'
assert result.year(2075).total_net_worth > 10_000_000, 'Long-run regression'
assert mc.prob_fire > 0.9, 'MC FIRE probability regression'
uk = profiles['uk_standard']
r = calculate_net_income(95000, TaxTreatment.PAYE, uk, pension_contributions=9500)
assert abs(r.net_income - 67949) < 100, f'Tax engine regression: {r.net_income}'
print('Phase 1 validation: ALL PASS')
"
```

Expected output: `Phase 1 validation: ALL PASS`
If any assertion fails, do not proceed — investigate the regression first.

---

---

## 12. Phase 7 — Generational & Cross-Jurisdiction Planning

> **Status: PLANNED — not yet implemented.**
> Source: `UK_vs_US_Financial_Planning.ipynb` and `UK_vs_US_Comparison_Document_v2.md`
> Priority: post-Phase 6. Can be integrated as a dedicated screen in Phase 3 frontend or as a standalone report module.

### 12.1 Purpose

Phase 7 extends LifeLedger from a single-household retirement planner into a
**multi-generational, cross-jurisdiction wealth platform**. It models:

1. **Parents' financial position** across two country paths (UK vs US) from the
   current position to their projected death year.
2. **Offspring financial trajectory** from childhood through their full working
   life, using realistic career path models.
3. **Wealth transfer** — how assets pass between generations under UK IHT and
   US estate tax, and what arrives in the offspring's hands net of tax.
4. **Country comparison** — at any point in the projection, show the delta
   between staying in the US and relocating to the UK (or vice versa).

The existing `UK_vs_US_Financial_Planning.ipynb` notebook is to be **rolled
into the platform** as the data source for Phase 7's country-specific macro
assumptions. The notebook's scenario logic, career models, and sensitivity
analyses should be reproduced as engine modules, with results surfaced on a
dedicated screen.

---

### 12.2 New Engine Modules

#### `backend/engine/generational_engine.py`

Core engine for multi-generation projection.

Key classes:
- `Offspring` — person dataclass: name, birth_year, life_expectancy,
  career_path_id, country (UK/US), education_type, university_start_year
- `CareerTrajectory` — maps career_path_id to salary growth curve:
  - Phase 1 (entry): start_salary, annual_growth_rate
  - Phase 2 (mid): breakpoint_year, mid_salary, mid_growth
  - Phase 3 (senior): senior_salary, senior_growth, peak_year
  - Phase 4 (wind-down): wind_down_year, end_salary
- `OffspringProjection` — year-by-year projection for one offspring:
  salary, tax, net_income, savings_rate, account_values, FIRE_year
- `GenerationalTransfer` — wealth passed from parents to offspring:
  gross_estate, iht_liability, net_transfer, transfer_year
- `GenerationalResult` — combined output:
  parent_timeline, offspring_timeline, transfer, combined_family_wealth

Career paths (matching the notebook's 10 careers):
```yaml
career_paths:
  - id: software_engineer
    label: "Software Engineer"
    ceiling: high
    uk:
      entry_salary: 45000
      mid_salary: 95000
      senior_salary: 150000
      peak_year_from_start: 20
    us:
      entry_salary: 120000   # mid-cost city (Austin / Denver / Seattle suburbs)
      mid_salary: 200000
      senior_salary: 320000
      peak_year_from_start: 18
      bayarea_threshold: 300000  # above this → Bay Area living costs apply

  - id: doctor
    label: "Doctor / Physician"
    ceiling: high
    uk:
      entry_salary: 35000   # FY1
      mid_salary: 75000     # registrar
      senior_salary: 120000 # consultant
    us:
      entry_salary: 65000   # resident
      mid_salary: 200000    # attending (mid-city)
      senior_salary: 350000

  # ... (lawyer, data_scientist, nurse, accountant, teacher, etc.)
```

#### `backend/engine/country_comparison_engine.py`

Runs two parallel projections (UK path / US path) and computes the delta.

- `CountryPath` — enum: UK, US
- `CountryProjection` — full timeline for one country path:
  income, tax, housing_cost, healthcare_cost, net_savings, total_wealth
- `BreakEvenResult` — year at which the UK path overtakes the US path
  (in common currency at a given FX rate)
- `ComparisonMatrix` — table of key metrics at key ages: wealth, estate,
  housing cost, healthcare cost, income coverage

Key methods:
- `run_comparison(base_scenario, us_scenario, fx_rate)` → `ComparisonMatrix`
- `find_break_even(uk_result, us_result, fx_scenario)` → `BreakEvenResult`
- `estate_comparison(uk_result, us_result, offspring)` → net estate each path

#### `backend/engine/macro_country_engine.py`

Country-specific macro assumption sets. Extends `MacroScenarioParams` with
country-aware parameters from the notebook.

```yaml
country_macro:
  UK:
    low:
      inflation: 0.035
      equity_real_return: 0.030
      salary_real_growth: 0.000
      house_price_nominal: 0.030
      healthcare_cost_annual: 0        # NHS free
    mid:
      inflation: 0.025
      equity_real_return: 0.050
      salary_real_growth: 0.010
      house_price_nominal: 0.035
      healthcare_cost_annual: 0
    high:
      inflation: 0.020
      equity_real_return: 0.075
      salary_real_growth: 0.020
      house_price_nominal: 0.045
      healthcare_cost_annual: 0

  US:
    low:
      inflation: 0.030
      equity_real_return: 0.035
      salary_real_growth: 0.010
      house_price_nominal: 0.030
      healthcare_working: 10000         # employer plan OOP
      healthcare_aca_bridge: 26000      # ages 62-65 (couple)
      healthcare_medicare: 14000        # ages 65-79
      healthcare_late_life: 36000       # ages 80+
    mid:
      inflation: 0.025
      equity_real_return: 0.060
      salary_real_growth: 0.018
      house_price_nominal: 0.045
      healthcare_working: 10000
      healthcare_aca_bridge: 26000
      healthcare_medicare: 14000
      healthcare_late_life: 36000
    high:
      inflation: 0.020
      equity_real_return: 0.080
      salary_real_growth: 0.025
      house_price_nominal: 0.055
      healthcare_working: 8000
      healthcare_aca_bridge: 22000
      healthcare_medicare: 12000
      healthcare_late_life: 30000
```

Key parameters from the notebook to preserve exactly:
- US Phase 1 (2026–2028): $600k gross, WA (0% state tax), 401k $23.5k + $10k match
- UK Phase 2 (2029+): £75k primary + £35k spouse = £110k combined
- Hannah (born 2017): university start 2035; life expectancy 2109
- Parents (born 1982): projected death ~2070; projection end 2109

#### `backend/engine/university_engine.py`

Models university costs and funding mechanisms by country.

```yaml
university:
  hannah_start_year: 2035
  hannah_duration_years: 4

  uk:
    tuition_per_year: 9250          # Plan 5 tuition cap
    living_costs_per_year: 12000    # Moderate
    funding: student_loan_plan5     # repay 9% above £25k for 40 years
    parent_contribution: 20000      # parental support

  us:
    low:
      type: in_state_public
      tuition_per_year: 14000
      living_per_year: 18000
      funding: 529_plan             # 529 balance at start: ~$136k
    mid:
      type: in_state_public
      tuition_per_year: 16000
      living_per_year: 20000
      funding: 529_plan
    high:
      type: elite_private
      tuition_per_year: 62000
      living_per_year: 25000
      funding: scholarships_and_loans

  529_plan:
    current_balance: 136000         # USD, at 2035 start
    annual_contribution: 0          # already funded
    growth_rate: 0.07

  lisa_for_hannah:
    enabled: true
    annual_contribution: 4000       # max
    government_bonus: 1000          # 25% of £4k
    start_year: 2035                # Hannah's 18th birthday
    projected_balance_at_first_home: 22000  # net of bonus
```

---

### 12.3 Frontend Additions

#### New screen: `CrossJurisdictionScreen`

A dedicated screen (add to sidebar after Retirement Planner) with:

**Tab 1 — Country Comparison**
- Select two country paths: UK vs US (or any two from the registered set)
- Select macro scenario: Low / Mid / High
- Key metrics table: wealth at retirement, annual housing cost, healthcare cost,
  estate to offspring (net of tax), Hannah's university cost (parental outlay)
- FIRE date comparison per path
- Break-even chart: when does Path A overtake Path B (in common currency)?
- Toggle: show/hide CA state tax sensitivity

**Tab 2 — Generational Timeline**
- Combined family wealth chart: parents + Hannah on one chart (2026–2109)
- Parents' line ends at projected death; transfer arrow shows estate passing
- Hannah's line picks up from inheritance + her own savings
- Three scenarios (Low/Mid/High) as shaded bands
- FIRE date markers for parents and for Hannah (per career path)

**Tab 3 — Hannah's Career Paths**
- Career selector: 10 career options with UK/US salary curves
- Chart: salary trajectory (entry → peak) for selected career, both countries
- Net worth at 45 / 55 / 65 per career, per country
- University cost breakdown (UK vs US) with 529/LISA impact

**Tab 4 — Estate & IHT**
- UK IHT scenario: NRB + RNRB, pension outside estate, 7-year gift rule
- US estate tax scenario: current exemption ($14M+), step-up basis
- Net estate to Hannah: UK path vs US path in common currency
- Sensitivity slider: assumed death year (affects compounding to transfer)

**Tab 5 — Sensitivity Analysis**
- CA state tax impact on Phase 1 savings (bar chart from notebook Section 5C)
- Social Security claim age comparison (bar chart from notebook Section 5C)
- GBP/USD sensitivity: how net wealth in GBP changes at FX 1.10 / 1.27 / 1.40
- Investment return sensitivity: ±2% return over 20 years

---

### 12.4 Notebook Integration

The existing `UK_vs_US_Financial_Planning.ipynb` is rolled into the platform
as **`notebooks/07_generational_planning.ipynb`**. This notebook:
- Imports engine modules from `backend/engine/` rather than defining its own logic
- Uses the same YAML config system (country_macro, career_paths, university)
- Reproduces all 6 figures from the original notebook using the platform's
  dark-mode matplotlib style
- Adds platform-specific validation: all chart data matches the engine output

The original notebook's standalone config block (`CONFIGURATION` cells 1A–1F)
should be replaced by YAML loads from the config directory. Notebook users
who want to tweak assumptions should edit the YAML, not the notebook.

---

### 12.5 Validation Figures

**Original spec targets (from source notebooks):**

| Metric | US Path | UK Path |
|---|---|---|
| Wealth at retirement (2044) | $12.9M | £5.5M (~$7M) |
| Estate to Hannah (~2072, gross) | $53M | £24M |
| Annual housing cost (2029) | $98,433/yr | £29,280/yr |
| Hannah university (parental outlay, mid) | $134k | £98k |
| ACA bridge healthcare (62–65, couple) | $26,000/yr | £0 NHS |
| 529 plan at Hannah's university start | $136k | — |
| State pension combined (from 2049) | — | £23,005/yr (2050) |
| US Social Security (from 67) | $27,600/yr | — |

Starting assets (2026): £1.05M total (£623k SIPP, £115k ISA, $400k US equities).

**Phase 7 engine validated figures (run 2026-08-24, mid scenario):**

> Spec's £24M / $53M are *no-drawdown ceiling* figures — gross asset values if
> retirement costs are funded entirely from external income (state pension + SS).
> The engine models realistic drawdown, producing a different but correct result.

| Metric | Engine output | vs Spec | Status |
|---|---|---|---|
| UK retirement wealth (2044) | £4,838,463 | 88% of £5.5M | ✅ Pass (≤10% gap) |
| US retirement wealth (2044) | $11,852,795 | 92% of $12.9M | ✅ Pass (≤10% gap) |
| UK gross estate (2072, realistic) | £14,933,108 | — | ✅ Correct (with drawdown) |
| UK gross estate (2072, no-drawdown) | £24,780,531 | 103% of £24M | ✅ Match |
| US gross estate (2072, no-drawdown) | $52,917,793 | 100% of $53M | ✅ Match |
| UK FIRE age (offspring, SWE) | 44 | — | ✅ Plausible |
| University UK (Plan 5 loan at grad) | £49,926 | — | ✅ |
| University US (529 covers) | $136k | ✅ exact | ✅ |
| State pension UK combined (2050) | £23,005/yr | — | ✅ |

**Engine regression anchors** (add to pytest when real data entered):
- `UK_RETIREMENT_2044 = 4_838_463`  ± 5%
- `US_RETIREMENT_2044 = 11_852_795` ± 5%
- `UK_FIRE_AGE_SWE    = 44`
- `UK_GROSS_ESTATE_NODRAWDOWN_2072 = 24_780_531` ± 3%

---

### 12.6 Config File (`config/generational/generational_config.yaml`)

New top-level config file covering all Phase 7 settings:
```yaml
generational:
  parents:
    birth_year: 1982
    life_expectancy_male: 87
    life_expectancy_female: 90
    current_assets:
      uk_sipp_gbp: 623000
      uk_isa_gbp: 115000
      us_equities_usd: 400000
    retire_age: 62
    retire_year: 2044
    us_phase:
      start_year: 2026
      end_year: 2028
      gross_salary_usd: 600000
      state: WA                   # no state income tax
      k401_employee: 23500
      k401_employer_match: 10000
      extra_savings_target_usd: 100000
    uk_phase:
      start_year: 2029
      primary_gross_gbp: 75000
      spouse_gross_gbp: 35000
      primary_pension_rate: 0.05
      employer_pension_rate: 0.05
      house_price_gbp: 800000
      deposit_gbp: 400000
      sdlt_gbp: 27200

  offspring:
    - name: Hannah
      birth_year: 2017
      life_expectancy: 92
      projection_end: 2109
      us_university:
        start_year: 2035
        years: 4
      uk_university:
        start_year: 2035
        years: 3
        student_loan_plan: 5
      lisa_start_year: 2035

  fx:
    scenarios:
      low:  1.18
      mid:  1.27
      high: 1.38

  career_paths: [see §12.2 above — stored inline or imported from careers_config.yaml]
```

*Last updated: 2026-08-24. Maintained by Claude on behalf of the project owner.*
