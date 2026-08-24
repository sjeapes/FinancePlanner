# LifeLedger

**Self-hosted personal finance and retirement planning platform.**

Long-horizon financial modelling, Monte Carlo retirement simulation, FIRE analysis, estate planning, and PDF report export — all running locally, with no subscription and no data leaving your machine.

> Dark mode · UK & US tax regimes · Multi-scenario · Home Assistant add-on

---

## What LifeLedger Does

| Capability | Detail |
|---|---|
| **Net worth projection** | Year-by-year timeline from today to age 90–95, stacked by account type |
| **FIRE analysis** | Automatic FIRE date detection, Safe Withdrawal Rate, income coverage in retirement |
| **Monte Carlo** | 1,000–10,000 simulations with P10/P25/P50/P75/P90 confidence bands and sequence-of-returns risk |
| **Scenario comparison** | Up to 4 scenarios overlaid on one graph — retire at 55, sell the house, move to US, etc. |
| **Pension modelling** | Accumulation → drawdown → annuity, PCLS, UK annual allowance + carry-forward, US RMDs |
| **Mortgage engine** | Full amortisation, multi-rate periods, lump-sum overpayments, offset account, equity / LTV tracking |
| **Life events** | Property sales, inheritances, career changes, care costs, emigration — 15 typed event processors |
| **Tax wrappers** | ISA, LISA, SIPP, GIA, 401(k), Roth IRA — correct tax treatment at contribution, growth, and withdrawal |
| **Drawdown optimisation** | ISA-first vs SIPP-first vs GIA-first — shows the lifetime tax saving between strategies |
| **Estate / IHT** | UK IHT with NRB + RNRB, 7-year gift tracker, reduction strategies; US federal estate tax |
| **Survivor planning** | Model death of either partner, income impact, mortgage affordability, life cover recommendation |
| **Healthcare costs** | UK (NHS + private top-up) or US (employer plan → ACA bridge → Medicare → late life) by age phase |
| **Portfolio rebalancing** | Drift alerts, glide-path equity reduction, buy/sell trade amounts |
| **PDF reports** | Quick / Full Annual / IFA Pack presets, 9 sections, 11 chart types, watermark, Google Drive upload |
| **Home Assistant add-on** | Net worth, FIRE date, and pension values as HA sensors on your dashboard |

---

## Screens

| Screen | What you see |
|---|---|
| **Dashboard** | Net worth today, FIRE progress bar, income vs expenses, active scenario count |
| **Timeline Graph** | Interactive stacked-area chart, crosshair tooltip, MC bands, FIRE line, scenario overlay |
| **Portfolio Mix** | Doughnut chart — liquid assets by class + total net worth breakdown |
| **Income Manager** | Income sources timeline, tax breakdown, contribution routing |
| **Accounts** | All savings, ISA, GIA, SIPP accounts with live market prices for holdings |
| **Property & Mortgages** | Property value tracking, amortisation schedule, overpayment planner |
| **Life Events** | Planned events on a calendar view with probability weighting |
| **Scenarios** | Create, edit, compare — scenario card grid with at-a-glance metrics |
| **Tax Planner** | Tax profile editor, drawdown order comparison, CGT tracker |
| **Retirement Planner** | Income coverage table, annuity vs drawdown comparison, state pension tracker |
| **Estate Planner** | IHT waterfall, gift tracker with 7-year countdown, survivor simulation |
| **Checkpoints** | Audit log — enter actual values, see real vs projected divergence |
| **Settings** | Google Drive sync, base currency, MC settings, report export |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, NumPy, SciPy |
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS 4, Recharts, Zustand, React Query |
| Data | YAML (scenarios, config) · SQLite (market prices, API keys) · Google Drive (sync) |
| Reports | ReportLab Platypus (PDF) · Matplotlib (charts) |
| Market data | yfinance (primary) · Alpha Vantage · Finnhub · OpenFIGI (ISIN resolver) |
| Deployment | Docker Compose · Home Assistant add-on · Cloudflare Tunnel · Raspberry Pi |

---

## Quick Setup — Desktop

### Option 1: Docker Compose *(recommended)*

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS / Linux)

```bash
# Clone the repo
git clone https://github.com/sjeapes/FinancePlanner.git
cd FinancePlanner

# Build and start (first run takes ~2 min to download images)
docker compose up --build

# Open in browser
# Frontend:  http://localhost:5173
# API docs:  http://localhost:8000/api/docs
```

Stop with `Ctrl+C`, restart with `docker compose up`.

Your data (scenarios, checkpoints, exports) is stored in `./data/` on your machine — Docker does not retain any state internally.

---

### Option 2: Manual Setup *(for development / editing code)*

**Prerequisites:** Python 3.12+ · Node.js 22+

**Step 1 — Clone and install Python dependencies**

```bash
git clone https://github.com/sjeapes/FinancePlanner.git
cd FinancePlanner

# Create a virtual environment (recommended)
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Step 2 — Install frontend dependencies**

```bash
cd frontend
npm install
cd ..
```

**Step 3 — Start the backend**

```bash
# From the project root, with .venv active:
python -m uvicorn backend.main:app --reload --port 8000
```

The backend is now running at `http://localhost:8000`.  
API docs (OpenAPI): `http://localhost:8000/api/docs`

> **Windows shortcut:** double-click `run-backend.bat`

**Step 4 — Start the frontend** *(in a second terminal)*

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173` in your browser.

> **Windows shortcut:** double-click `run-frontend.bat`

---

### Option 3: Raspberry Pi / Always-On Server

```bash
# Clone on the Pi
git clone https://github.com/sjeapes/FinancePlanner.git
cd FinancePlanner

# Install Docker if not already present
curl -sSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# Run in the background
docker compose up --build -d

# Tail logs
docker compose logs -f
```

Access from any device on your network at `http://<pi-ip>:5173`.

**Optional — Cloudflare Tunnel for remote access:**

```bash
# Install cloudflared on the Pi, then:
cloudflared tunnel --url http://localhost:5173
```

---

## Quick Setup — Home Assistant

LifeLedger ships as a self-hosted HA add-on. It runs as a service inside Home Assistant OS and exposes the full web UI via HA Ingress.

### Step 1 — Add the repository

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Click the ⋮ menu (top right) → **Repositories**
3. Add: `https://github.com/sjeapes/FinancePlanner`
4. Click **Add**, then close

The **LifeLedger** add-on will appear in the store. Click **Install**.

> **Manual install (alternative):** copy the `homeassistant/` folder to `/addon_configs/lifeledger/` on your HA host, then reload the add-on store.

### Step 2 — Configure options

In the add-on **Configuration** tab, adjust to your preferences:

```yaml
log_level: INFO            # DEBUG | INFO | WARNING | ERROR
base_currency: GBP         # GBP | USD | EUR
projection_start_year: 2025
projection_end_year: 2075
inflation_base_rate: 0.025
monte_carlo_simulations: 1000
monte_carlo_seed: 42
drive_sync_enabled: false
drive_sync_interval_minutes: 5
```

Click **Save**, then **Start**.

### Step 3 — Access the UI

- Via HA sidebar: click the **LifeLedger** panel (added automatically)
- Direct URL: `http://<ha-ip>:8000`

### Step 4 — Add to your HA dashboard *(optional)*

LifeLedger exposes its data through the FastAPI at port 8000. You can create HA template sensors to display key figures:

```yaml
# configuration.yaml
template:
  - sensor:
      - name: "Net Worth Today"
        unit_of_measurement: "£"
        icon: mdi:chart-line
        state: >
          {{ state_attr('sensor.lifeledger', 'net_worth_current') | default(0) | round(0) }}

      - name: "FIRE Year"
        icon: mdi:fire
        state: >
          {{ state_attr('sensor.lifeledger', 'fire_year') | default('Unknown') }}

      - name: "Years to FIRE"
        unit_of_measurement: "years"
        icon: mdi:calendar-clock
        state: >
          {{ (state_attr('sensor.lifeledger', 'fire_year') | int - now().year) | default(0) }}
```

---

## First-Time Configuration

### Your financial data

Scenarios are stored as YAML files in `data/scenarios/`. The quickest way to get started:

1. Open the **Data Management** screen in the UI
2. Add your people (name, date of birth, retirement age)
3. Add income sources, accounts, pensions, property, and mortgages
4. All data saves to `data/scenarios/base.yaml`

Alternatively, edit `data/scenarios/base.yaml` directly — it is a plain YAML file with full inline comments.

### Market data API keys *(optional)*

Live market prices for your holdings are fetched via yfinance (no key required). For higher rate limits, add keys via **Settings → Market Data**:

| Provider | What it adds | Free tier |
|---|---|---|
| yfinance | UK + US prices, 20yr history | No key needed |
| Alpha Vantage | Higher rate limit | 25 req/day |
| Finnhub | Real-time US prices | 60 req/min |
| OpenFIGI | ISIN → ticker resolution | 250 req/day |

Keys are stored in the local SQLite database (`data/lifeledger.db`) — they never appear in any YAML file.

### Google Drive sync *(optional)*

1. Go to **Settings → Google Drive**
2. Click **Connect** — a browser window opens for OAuth2 authorisation
3. LifeLedger gets `drive.file` scope only (access only to files it creates)
4. Scenarios and config sync to a `LifeLedger/` folder in your Drive

---

## Generating a PDF Report

```
POST http://localhost:8000/api/reports/generate
Content-Type: application/json

{
  "preset": "full_annual",
  "prepared_for": "Stephen",
  "scenario_path": "data/scenarios/base.yaml"
}
```

Or via the **Settings → Export Report** screen. Three presets:

| Preset | Pages | Charts | Use case |
|---|---|---|---|
| `quick` | ~4 | 2 | Quick snapshot for personal review |
| `full_annual` | ~18 | 8 | Annual financial review |
| `ifa_pack` | ~28 | 11 | Share with an IFA or financial adviser |

Reports are saved to `data/exports/`. If Google Drive sync is enabled, they upload automatically.

---

## Running the Test Suite

```bash
# Activate .venv first, then:
pytest tests/test_engines.py -v
```

40+ tests covering all engines: tax, projection, mortgage, pension, events, tax wrappers, retirement planning, estate/IHT, portfolio rebalancing, and YAML round-trips.

For a quick smoke test of Phase 1 core figures:

```bash
python -c "
import sys; sys.path.insert(0, '.')
from backend.persistence.yaml_serialiser import *
from backend.engine.calculator import ProjectionEngine, run_monte_carlo
cfg = load_app_config_from_file('config/lifeledger_config.yaml')
profiles = {p.id: p for p in load_tax_profiles_from_file('config/tax_profiles.yaml')}
sc = load_scenario_from_file('data/scenarios/base.yaml')
result = ProjectionEngine(sc, cfg, profiles).run()
assert result.year(2025).total_net_worth > 600_000
assert result.fire_year == 2031
print('✅ Phase 1 validation: PASS')
"
```

---

## Project Structure

```
FinancePlanner/
├── backend/
│   ├── api/routes/          # FastAPI route handlers
│   │   ├── accounts.py      # Account CRUD
│   │   ├── simulation.py    # Projection + Monte Carlo
│   │   ├── scenarios.py     # Scenario management
│   │   ├── retirement.py    # Phase 4: retirement planning
│   │   ├── planning.py      # Phase 5: estate, survivor, rebalancing
│   │   └── reports.py       # Phase 6: PDF export
│   ├── engine/
│   │   ├── calculator.py    # Core 12-step projection engine
│   │   ├── tax_engine.py    # UK / US / Generic tax calculations
│   │   ├── mortgage.py      # Mortgage amortisation
│   │   ├── pension.py       # Pension lifecycle
│   │   ├── events.py        # Life events processor
│   │   ├── tax_wrappers.py  # ISA / SIPP / GIA / 401k wrapper rules + CGT
│   │   ├── monte_carlo.py   # Confidence bands + scenario comparison
│   │   ├── retirement_engine.py  # Income coverage, drawdown order, annuity
│   │   ├── advanced_planning.py  # Survivor, estate, healthcare, rebalancing
│   │   └── scenario_engine.py    # Scenario diff merger
│   ├── models/              # Pydantic + dataclass models
│   ├── persistence/         # YAML serialiser, SQLite cache, Google Drive
│   ├── market_data/         # Price providers (yfinance, Alpha Vantage, Finnhub)
│   ├── reports/             # PDF engine + chart renderer
│   └── main.py              # FastAPI app factory
├── frontend/src/
│   ├── screens/             # Dashboard, Timeline, Accounts, Retirement, Estate…
│   ├── components/          # Graph, Portfolio, Forms, Layout
│   ├── store/               # Zustand state (config, simulation, scenarios)
│   └── api/hooks/           # React Query hooks per domain
├── config/
│   ├── lifeledger_config.yaml
│   ├── tax_profiles.yaml
│   ├── retirement/retirement_config.yaml
│   ├── planning/planning_config.yaml
│   ├── simulation/monte_carlo_config.yaml
│   └── reports/report_config.yaml
├── data/
│   ├── scenarios/base.yaml           # Your financial data
│   ├── scenarios/templates/          # 8 built-in scenario templates
│   ├── checkpoints/                  # Actual net worth audit logs
│   └── exports/                      # Generated PDF reports
├── homeassistant/
│   ├── config.json          # HA add-on manifest
│   └── run.sh               # HA add-on entrypoint
├── notebooks/               # Jupyter validation notebooks (phases 2–6)
├── tests/
│   └── test_engines.py      # pytest suite — 40+ tests
├── docker-compose.yml
├── Dockerfile.api
├── Dockerfile.frontend
└── requirements.txt
```

---

## Built-In Scenario Templates

Eight scenario templates are included in `data/scenarios/templates/`. Load any of them via the Scenarios screen or the API:

| Template | What it models |
|---|---|
| `retire_at_55.yaml` | Move retirement forward; check FIRE gap and pension accessibility |
| `sell_house_2030.yaml` | Sell primary residence, invest equity into ISA + SIPP |
| `move_to_us.yaml` | Switch to US Federal tax; add USD accounts; model FX impact |
| `annuity_vs_drawdown.yaml` | Compare pension annuity income to 4% SWR drawdown |
| `stress_test.yaml` | −30% market crash in year 1 of retirement + high inflation |
| `partner_death_70.yaml` | Remove partner income from 2059; mortgage affordability check |
| `inheritance_65.yaml` | £150k inheritance at age 65; IHT and investment routing |
| `aggressive_fire.yaml` | 35% savings rate, target retire at 50 |

---

## Configuration Reference

All tunable parameters live in YAML files. Key files:

| File | Controls |
|---|---|
| `config/lifeledger_config.yaml` | Base currency, projection range, inflation, FX rates, MC settings, Drive sync |
| `config/tax_profiles.yaml` | UK / US / Ireland tax bands, NI rates, CGT allowances, ISA/SIPP limits |
| `config/retirement/retirement_config.yaml` | Annuity rates, drawdown SWR, NI Class 3 cost, triple-lock rate, emergency fund target |
| `config/planning/planning_config.yaml` | IHT bands, care home costs, rebalancing targets, glide path |
| `config/simulation/monte_carlo_config.yaml` | n_simulations, Low/Mid/High macro scenarios, sequence-of-returns crash |
| `config/reports/report_config.yaml` | Report preset, chart DPI, watermark, Drive folder |
| `data/scenarios/base.yaml` | Your people, income, accounts, pensions, property, mortgages, expenses, life events |

> **More config is always better than less.** Every parameter that might ever need adjusting is exposed in YAML — not hardcoded.

---

## Core Design Rules

These are non-negotiable in the codebase — do not change them:

1. **Income does not auto-add to net worth.** Only explicitly routed contributions to savings/investment/pension accounts build the portfolio. Spending income is not wealth.
2. **Scenarios are YAML diffs.** Each scenario stores only the fields that differ from `base.yaml`, merged at runtime. The base file is always the single source of truth.
3. **API keys in SQLite only.** Keys for yfinance, Alpha Vantage, Finnhub, and OpenFIGI are never written to any YAML file, which could be synced to Drive.
4. **Dark mode only.** No light mode toggle — one consistent design identity.
5. **DM Mono for all numbers.** Every monetary value, ticker, and date in the UI uses the DM Mono monospace font for vertical alignment.

---

## Acknowledgements

Built with FastAPI, React, ReportLab, Recharts, NumPy, yfinance, and a lot of YAML.  
Designed for self-hosted, privacy-first personal finance planning.

---

*LifeLedger is a personal planning tool, not financial advice. Always consult a qualified IFA before making major financial decisions.*
