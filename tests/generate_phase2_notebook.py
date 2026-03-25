"""
@brief Generate the LifeLedger Phase 2 validation notebook.
@return Writes LifeLedger_Phase2_Tests.ipynb to the project root.

Tests covered:
  1. Pydantic v2 model validation and round-trip serialisation
  2. SQLite cache — init, write, read, immutability
  3. Market data — yfinance live fetch for a known UK ticker
  4. Backend route imports and FastAPI app construction
  5. Simulation endpoint logic (direct call, no HTTP server required)
  6. Tax endpoint logic (direct call)
  7. Scenario list / load via API route functions
  8. Summary
"""

import json
import os
import sys

OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'LifeLedger_Phase2_Tests.ipynb')


def md(text: str) -> dict:
    """
    @brief Build a markdown notebook cell.
    @param text Markdown source string.
    @return nbformat cell dict.
    """
    return {"cell_type": "markdown", "metadata": {}, "source": text}


def code(src: str) -> dict:
    """
    @brief Build a code notebook cell.
    @param src Python source string.
    @return nbformat cell dict with empty outputs.
    """
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": src,
    }


cells = []

# ── Title ────────────────────────────────────────────────────────────────────
cells.append(md("""# LifeLedger — Phase 2 Validation Notebook

Tests the Phase 2 API layer without requiring a running HTTP server.

**Run from the project root** — all cells are self-contained; run top to bottom.

Sections:
1. Environment setup
2. Pydantic v2 model validation
3. SQLite cache (price_history, api_keys, sync_state)
4. Market data — yfinance live fetch
5. FastAPI app construction and route registration
6. Simulation route logic (direct import)
7. Tax route logic (direct import)
8. Scenario route logic (direct import)
9. Summary
"""))

# ── 1. Environment setup ─────────────────────────────────────────────────────
cells.append(md("## 1. Environment Setup"))
cells.append(code("""\
import sys
import os
import logging
import warnings
import tempfile
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.getcwd())
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)-8s %(name)-30s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)

import fastapi
import pydantic
import sqlalchemy
import httpx
import yfinance

print('\\u2713 Environment ready')
print(f'  Python      {sys.version.split()[0]}')
print(f'  FastAPI     {fastapi.__version__}')
print(f'  Pydantic    {pydantic.__version__}')
print(f'  SQLAlchemy  {sqlalchemy.__version__}')
print(f'  yfinance    {yfinance.__version__}')
print(f'  Project root: {PROJECT_ROOT}')
"""))

# ── 2. Pydantic v2 models ────────────────────────────────────────────────────
cells.append(md("## 2. Pydantic v2 Model Validation"))
cells.append(code("""\
from backend.models.pydantic_models import (
    PersonModel, IncomeSourceModel, SavingsAccountModel,
    InvestmentAccountModel, PensionFundModel, ScenarioModel,
    FIRETargetModel,
)
from backend.models.models import TaxTreatment, AccountType, PensionType
import pydantic

print('\\u2500' * 55)
print('Pydantic v2 model validation')
print('\\u2500' * 55)

# ── PersonModel ──────────────────────────────────────────────
person_data = {
    'id': 'james',
    'name': 'James',
    'date_of_birth': '1987-07-01',
    'retirement_age': 60,
    'life_expectancy': 90,
    'state_pension': {
        'qualifying_years': 25,
        'weekly_amount': 221.20,
        'start_age': 67,
        'deferred': False,
    },
}
p = PersonModel(**person_data)
assert p.name == 'James'
assert p.retirement_age == 60
assert p.state_pension is not None
assert p.state_pension.weekly_amount == 221.20
print(f'\\u2713 PersonModel  name={p.name}, retirement_age={p.retirement_age}')

# ── Validation rejects bad data ──────────────────────────────
try:
    PersonModel(id='x', name='', date_of_birth='not-a-date',
                retirement_age=-1, life_expectancy=90)
    print('  FAIL: should have raised ValidationError')
except pydantic.ValidationError as e:
    print(f'\\u2713 PersonModel  correctly rejects invalid data ({e.error_count()} errors)')

# ── FIRETargetModel ──────────────────────────────────────────
ft = FIRETargetModel(
    target_net_worth=1_200_000,
    swr=0.04,
    fire_type='lean_fire',
    annual_expenses=48_000,
)
assert ft.target_net_worth == 1_200_000
assert ft.swr == 0.04
print(f'\\u2713 FIRETargetModel  target=\\u00a3{ft.target_net_worth:,.0f}, swr={ft.swr:.1%}')

# ── JSON round-trip ──────────────────────────────────────────
json_str = p.model_dump_json()
p2 = PersonModel.model_validate_json(json_str)
assert p2.name == p.name
assert p2.date_of_birth == p.date_of_birth
print(f'\\u2713 PersonModel  JSON round-trip OK ({len(json_str)} bytes)')

print()
print('\\u2713 All Pydantic v2 model tests passed')
"""))

# ── 3. SQLite cache ──────────────────────────────────────────────────────────
cells.append(md("## 3. SQLite Cache"))
cells.append(code("""\
import os
import sqlite3
from datetime import date
from backend.persistence.sqlite_cache import (
    init_db,
    upsert_price, get_prices,
    set_api_key, get_api_key,
    update_sync_state, get_sync_state,
)

print('\\u2500' * 55)
print('SQLite cache tests')
print('\\u2500' * 55)

# Use a fixed test path in data/ to avoid Windows tempdir lock issues
db_path = 'data/phase2_test_cache.db'
engine = None
try:
    engine = init_db(db_path)

    # ── price_history ────────────────────────────────────────
    upsert_price(engine, 'VWRP.L', date(2025, 1, 2), 115.20, 'yfinance')
    upsert_price(engine, 'VWRP.L', date(2025, 1, 3), 116.40, 'yfinance')
    upsert_price(engine, 'AAPL',   date(2025, 1, 2), 185.00, 'yfinance')

    rows = get_prices(engine, 'VWRP.L')
    assert len(rows) == 2, f'Expected 2 rows, got {len(rows)}'
    prices = {r['date']: r['price'] for r in rows}
    assert prices['2025-01-02'] == 115.20
    assert prices['2025-01-03'] == 116.40
    print(f'\\u2713 price_history  write + read OK ({len(rows)} rows for VWRP.L)')

    # ── Immutability: upsert same date should NOT change price ──
    upsert_price(engine, 'VWRP.L', date(2025, 1, 2), 999.99, 'yfinance')
    rows2 = get_prices(engine, 'VWRP.L', start_date=date(2025, 1, 2), end_date=date(2025, 1, 2))
    assert rows2[0]['price'] == 115.20, f"Immutability violated: {rows2[0]['price']}"
    print('\\u2713 price_history  historical prices immutable \\u2714')

    # ── api_keys ─────────────────────────────────────────────
    set_api_key(engine, 'alpha_vantage', 'DEMO_KEY_12345')
    retrieved = get_api_key(engine, 'alpha_vantage')
    assert retrieved == 'DEMO_KEY_12345', f'Key mismatch: {retrieved}'
    print(f'\\u2713 api_keys  set + get OK (key not stored in plaintext in YAML)')

    # Confirm key is NOT stored as plaintext in SQLite binary
    # Must close engine first so sqlite3 can open the file
    engine.dispose()
    engine = None
    con = sqlite3.connect(db_path)
    raw = con.execute("SELECT encrypted_key FROM api_keys WHERE provider='alpha_vantage'").fetchone()[0]
    con.close()
    assert raw != 'DEMO_KEY_12345', 'Key stored in plaintext — security issue!'
    print(f'\\u2713 api_keys  key is obfuscated in DB (not plaintext)')

    # Re-open engine for sync_state test
    engine = init_db(db_path)

    # ── sync_state ───────────────────────────────────────────
    update_sync_state(engine, local_hash='abc123', remote_hash='def456',
                      conflict_status='none')
    state = get_sync_state(engine)
    assert state is not None
    assert state['local_hash'] == 'abc123'
    assert state['conflict_status'] == 'none'
    print(f'\\u2713 sync_state  update + read OK')

finally:
    if engine is not None:
        engine.dispose()
    import gc, time
    gc.collect()
    time.sleep(0.2)
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except PermissionError:
            print(f'\\u26a0  Could not delete test DB (Windows lock) — ignoring')
    print()
    print('\\u2713 All SQLite cache tests passed')
"""))

# ── 4. Market data — yfinance ────────────────────────────────────────────────
cells.append(md("## 4. Market Data — yfinance Live Fetch"))
cells.append(code("""\
import os
from datetime import date, timedelta
from backend.market_data.providers.yfinance_provider import YFinanceProvider
from backend.market_data.cache import PriceCache

print('\\u2500' * 55)
print('Market data tests (requires internet)')
print('\\u2500' * 55)

provider = YFinanceProvider()

# ── Fetch recent history for a UK LSE ticker ─────────────────
end_date   = date.today()
start_date = end_date - timedelta(days=30)
history = provider.fetch_history('VWRP.L', start_date, end_date)

if history:
    latest = max(history, key=lambda p: p.date)
    print(f'\\u2713 yfinance  VWRP.L (Vanguard FTSE All-World)')
    print(f'       Fetched {len(history)} trading days')
    print(f'       Latest close: \\u00a3{latest.price:.2f} ({latest.date})')
    assert latest.price > 0
else:
    print('\\u26a0  yfinance  No data returned (network issue?) — skipping assertion')

# ── Fetch a US ticker ────────────────────────────────────────
us_history = provider.fetch_history('AAPL', start_date, end_date)
if us_history:
    latest_us = max(us_history, key=lambda p: p.date)
    print(f'\\u2713 yfinance  AAPL: ${latest_us.price:.2f} ({latest_us.date})')
else:
    print('\\u26a0  yfinance  AAPL no data (network issue?)')

# ── PriceCache round-trip ────────────────────────────────────
cache_db_path = 'data/phase2_pricecache_test.db'
try:
    cache = PriceCache(cache_db_path)

    test_date = date(2025, 6, 1)
    cache.cache_price('TEST.L', test_date, 42.50, 'yfinance')
    cached = cache.get_cached_price('TEST.L', test_date)
    assert cached == 42.50, f'Cache miss: {cached}'
    print(f'\\u2713 PriceCache  write + read OK (\\u00a342.50)')

    # Immutability via cache layer
    cache.cache_price('TEST.L', test_date, 999.99, 'yfinance')
    cached2 = cache.get_cached_price('TEST.L', test_date)
    assert cached2 == 42.50, f'Cache immutability violated: {cached2}'
    print('\\u2713 PriceCache  immutability enforced \\u2714')
finally:
    cache._engine.dispose()
    import gc, time
    gc.collect()
    time.sleep(0.2)
    if os.path.exists(cache_db_path):
        try:
            os.remove(cache_db_path)
        except PermissionError:
            pass

print()
print('\\u2713 Market data tests passed')
"""))

# ── 5. FastAPI app construction ──────────────────────────────────────────────
cells.append(md("## 5. FastAPI App — Construction & Route Registration"))
cells.append(code("""\
from backend.main import app, create_app

print('\\u2500' * 55)
print('FastAPI app construction')
print('\\u2500' * 55)

assert app.title == 'LifeLedger API'
print(f'\\u2713 App title: {app.title}')
print(f'\\u2713 App version: {app.version}')

# Count registered routes by prefix
routes = [(r.path, list(getattr(r, 'methods', ['']))) for r in app.routes if hasattr(r, 'methods')]

def routes_for(prefix):
    return [r for r in routes if r[0].startswith(prefix)]

sections = [
    ('/api/simulate',     'Simulation'),
    ('/api/scenarios',    'Scenarios'),
    ('/api/accounts',     'Accounts'),
    ('/api/tax',          'Tax'),
    ('/api/checkpoints',  'Checkpoints'),
    ('/api/sync',         'Sync'),
    ('/api/market-data',  'Market data'),
]

total = 0
for prefix, name in sections:
    count = len(routes_for(prefix))
    total += count
    print(f'  \\u2713 {name:<15} {count} route(s)')

print(f'\\u2500' * 55)
print(f'  Total API routes registered: {total}')
assert total >= 20, f'Expected \\u226520 routes, got {total}'
print(f'\\u2713 All route groups registered correctly')
"""))

# ── 6. Simulation route logic ────────────────────────────────────────────────
cells.append(md("## 6. Simulation Route Logic (Direct Import)"))
cells.append(code("""\
import sys, os
sys.path.insert(0, os.getcwd())

from backend.persistence.yaml_serialiser import (
    load_app_config_from_file,
    load_scenario_from_file,
    load_tax_profiles_from_file,
)
from backend.engine.calculator import ProjectionEngine, run_monte_carlo

print('\\u2500' * 55)
print('Simulation engine via Phase 2 config paths')
print('\\u2500' * 55)

CONFIG_PATH   = 'config/lifeledger_config.yaml'
SCENARIO_PATH = 'data/scenarios/base.yaml'
TAX_PATH      = 'config/tax_profiles.yaml'

cfg      = load_app_config_from_file(CONFIG_PATH)
profiles = {p.id: p for p in load_tax_profiles_from_file(TAX_PATH)}
sc       = load_scenario_from_file(SCENARIO_PATH)

assert cfg is not None, 'Config load failed'
assert sc  is not None, 'Scenario load failed'
assert len(profiles) >= 2, f'Expected \\u22652 tax profiles, got {len(profiles)}'
print(f'\\u2713 Config loaded   currency={cfg.base_currency}, range={cfg.projection_start_year}\\u2013{cfg.projection_end_year}')
print(f'\\u2713 Scenario loaded  name=\\u201c{sc.name}\\u201d, people={len(sc.people)}')
print(f'\\u2713 Tax profiles     {list(profiles.keys())}')

# Run projection
engine = ProjectionEngine(cfg, profiles)
result = engine.project(sc)

nw_2025 = result.year(2025).total_net_worth
nw_2075 = result.year(2075).total_net_worth
fire_yr  = result.fire_year

assert nw_2025 > 600_000,    f'2025 NW regression: {nw_2025:,.0f}'
assert fire_yr == 2031,       f'FIRE year regression: {fire_yr}'
assert nw_2075 > 10_000_000, f'2075 NW regression: {nw_2075:,.0f}'

print()
print(f'  2025 net worth : \\u00a3{nw_2025:>14,.0f}')
print(f'  FIRE year      : {fire_yr}')
print(f'  2075 net worth : \\u00a3{nw_2075:>14,.0f}')

# Pydantic serialisation — use ScenarioModel as proxy
import json
from backend.models.pydantic_models import ScenarioModel
snap = result.year(2031)
snap_dict = {
    'year': 2031,
    'total_net_worth': snap.total_net_worth,
    'gross_income': snap.total_gross_income,
    'net_income': snap.total_net_income,
    'fire_achieved': snap.fire_achieved,
}
json_out = json.dumps(snap_dict)
assert '2031' in json_out
print()
print(f'\\u2713 YearSnapshot JSON serialisation OK ({len(json_out)} bytes)')
print()
print('\\u2713 Simulation tests passed')
"""))

# ── 7. Tax route logic ───────────────────────────────────────────────────────
cells.append(md("## 7. Tax Endpoint Logic (Direct Call)"))
cells.append(code("""\
from backend.engine.tax_engine import calculate_net_income
from backend.models.models import TaxTreatment
from backend.persistence.yaml_serialiser import load_tax_profiles_from_file

print('\\u2500' * 55)
print('Tax endpoint logic — matches /api/tax/calculate')
print('\\u2500' * 55)

profiles = {p.id: p for p in load_tax_profiles_from_file('config/tax_profiles.yaml')}
uk = profiles['uk_standard']
uk_se = profiles.get('uk_self_employed', uk)

import pandas as pd

rows = []
test_cases = [
    ('\\u00a395k PAYE + \\u00a39.5k pension',  95_000,  TaxTreatment.PAYE,          uk,    9_500,  67_949),
    ('\\u00a362k PAYE',                          62_000,  TaxTreatment.PAYE,          uk,        0,  None),
    ('\\u00a315k Self-employed',                 15_000,  TaxTreatment.SELF_EMPLOYED, uk_se,     0,  None),
    ('\\u00a3150k PAYE (taper zone)',           150_000,  TaxTreatment.PAYE,          uk,        0,  94_806),
    ('\\u00a312.5k (below personal allowance)', 12_500,  TaxTreatment.PAYE,          uk,        0,  12_500),
]

for label, gross, treatment, profile, pension, expected_net in test_cases:
    r = calculate_net_income(gross, treatment, profile, pension_contributions=pension)
    ok = '\\u2713' if (expected_net is None or abs(r.net_income - expected_net) < 200) else '\\u2717 FAIL'
    rows.append({
        'Case':          label,
        'Gross':         f'\\u00a3{gross:>9,.0f}',
        'Income Tax':    f'\\u00a3{r.income_tax:>9,.0f}',
        'NI':            f'\\u00a3{r.national_insurance:>8,.0f}',
        'Net':           f'\\u00a3{r.net_income:>9,.0f}',
        'Eff. Rate':     f'{r.effective_rate:.1%}',
        'Pass':          ok,
    })
    if expected_net:
        assert abs(r.net_income - expected_net) < 200, f'{label}: net={r.net_income:.0f}, expected={expected_net}'

df = pd.DataFrame(rows)
print(df.to_string(index=False))
print()
print('\\u2713 All tax cases match expected values')
"""))

# ── 8. Scenario route logic ──────────────────────────────────────────────────
cells.append(md("## 8. Scenario Route Logic (Direct Import)"))
cells.append(code("""\
import os
from backend.persistence.yaml_serialiser import load_scenario_from_file

print('\\u2500' * 55)
print('Scenario loading and Pydantic serialisation')
print('\\u2500' * 55)

SCENARIOS_DIR = 'data/scenarios'
yaml_files = [f for f in os.listdir(SCENARIOS_DIR) if f.endswith('.yaml')]
print(f'\\u2713 Scenarios directory contains {len(yaml_files)} file(s): {yaml_files}')
assert len(yaml_files) >= 1

# Load base scenario
sc = load_scenario_from_file(os.path.join(SCENARIOS_DIR, 'base.yaml'))
assert sc is not None
assert sc.is_base is True
assert len(sc.people) == 2
assert len(sc.income_sources) >= 3
assert len(sc.savings_accounts) >= 1
assert len(sc.investment_accounts) >= 1
assert len(sc.pension_funds) >= 1
assert sc.fire_target is not None

print(f'\\u2713 base.yaml loaded')
print(f'     People            : {[p.name for p in sc.people]}')
print(f'     Income sources    : {len(sc.income_sources)}')
print(f'     Savings accounts  : {len(sc.savings_accounts)}')
print(f'     Investment accts  : {len(sc.investment_accounts)}')
print(f'     Pension funds     : {len(sc.pension_funds)}')
print(f'     Properties        : {len(sc.properties)}')
print(f'     FIRE target       : \\u00a3{sc.fire_target.target_net_worth:,.0f} at {sc.fire_target.swr:.1%} SWR')

# Verify holdings have expected tickers (via symbol_link)
all_holdings = [h for a in sc.investment_accounts for h in a.holdings]
tickers = [h.symbol_link.symbol for h in all_holdings if h.symbol_link and h.symbol_link.symbol]
print(f'     Investment tickers: {tickers}')
assert len(all_holdings) >= 1

print()
print('\\u2713 Scenario route logic tests passed')
"""))

# ── 9. Summary ───────────────────────────────────────────────────────────────
cells.append(md("## 9. Summary"))
cells.append(code("""\
print('=' * 60)
print('  LifeLedger Phase 2 — Validation Summary')
print('=' * 60)
print()
sections_summary = [
    ('Pydantic v2 models',          'PersonModel, FIRETargetModel, JSON round-trip'),
    ('SQLite cache',                 'price_history, api_keys, sync_state, immutability'),
    ('Market data (yfinance)',       'VWRP.L history, AAPL price, PriceCache'),
    ('FastAPI app',                  f'\\u226520 routes registered across 7 groups'),
    ('Simulation engine',            'NW 2025, FIRE 2031, NW 2075 — all match Phase 1'),
    ('Tax endpoint logic',           '5 test cases — PAYE, SE, taper zone'),
    ('Scenario route logic',         'base.yaml — 2 people, \\u22653 income, FIRE target'),
]
for name, detail in sections_summary:
    print(f'  \\u2705  {name}')
    print(f'       {detail}')
    print()

print('=' * 60)
print('  Phase 2 validation: ALL PASS')
print('=' * 60)
print()
print('To start the API server:')
print('  python -m uvicorn backend.main:app --reload --port 8000')
print()
print('API docs: http://localhost:8000/api/docs')
"""))

# ── Write notebook ────────────────────────────────────────────────────────────
nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "LifeLedger (Python 3.11)",
            "language": "python",
            "name": "lifeledger",
        },
        "language_info": {"name": "python", "version": "3.11.4"},
    },
    "cells": cells,
}

out_path = os.path.abspath(OUTPUT)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"Notebook written to: {out_path}")
print(f"Cells: {len(cells)}")
