# LifeLedger — Feature Roadmap

Phases 1–6 are complete. This document groups remaining work into logical phases with effort estimates. Phases are independent — any can be tackled in any order.

---

## Phase 7 · Generational & Cross-Jurisdiction Planning
*The biggest differentiator — no consumer tool does this.*

| Deliverable | Notes |
|---|---|
| `backend/engine/generational_engine.py` | Offspring trajectory (childhood → retirement → death), 10 career path models, wealth transfer from parents |
| `backend/engine/jurisdiction_engine.py` | UK vs US parallel projection: income tax, pension systems, healthcare phases, CGT vs step-up basis, FX drift |
| `config/generational/generational_config.yaml` | Offspring DOBs, career models, university cost assumptions, country macro params |
| `backend/api/routes/generational.py` | API routes for generational report |
| `frontend/src/screens/GenerationalPlanning.tsx` | New screen: timeline showing two country paths, wealth handoff waterfall, offspring career selector |
| `notebooks/09_phase7_validation.ipynb` | Validation: UK retirement £5.5M vs US $12.9M; estate to offspring £24M vs $53M |

**Key calculations:**
- UK Plan 5 student loan vs US 529 plan: net cost of university per route
- IHT (NRB + RNRB, 7yr gifts) vs US estate tax (stepped-up basis)
- FX drift model: GBP/USD random walk with mean reversion
- Break-even age for UK vs US emigration decision
- Offspring FIRE date under each inheritance scenario

---

## Phase 8 · Tax Optimisation Engine
*Addresses the biggest gap vs ProjectionLab and Boldin.*

| Deliverable | Notes |
|---|---|
| Auto band-filler | Each year, compute optimal £ to draw from SIPP to fill personal allowance + basic rate band, then top up from ISA. Returns year-by-year draw schedule. |
| UFPLS support | Uncrystallised Funds Pension Lump Sum: 25% tax-free on each withdrawal instead of all at retirement start. Model both strategies and show lifetime tax delta. Most-requested ProjectionLab UK feature. |
| Lifetime allowance tracker | Track cumulative tax-free cash taken; flag when approaching the £268,275 ceiling. |
| CGT harvesting scheduler | Each tax year, identify GIA gains below the £3k exemption and recommend realising them to reset cost basis. |
| Dividend allowance optimiser | Flag when dividend income exceeds £500 allowance; recommend ISA or pension routing. |
| Rental income tax treatment | Correctly add rental income to salary before income tax banding; model mortgage interest relief. |
| Scottish rate support | Separate tax bands for Scottish-resident taxpayers (5 bands vs 3). |
| `config/tax/optimiser_config.yaml` | Knobs for each strategy: enable/disable, target band, safety buffer |
| `frontend/src/screens/TaxOptimiser.tsx` | New screen: year-by-year recommended actions, lifetime tax saved, before/after chart |

---

## Phase 9 · Visualisation & UX Enhancement
*Closes the gap with ProjectionLab's best-in-class charts.*

| Deliverable | Notes |
|---|---|
| Sankey / cash flow diagram | D3 or recharts Sankey: income → tax → accounts → expenses. Most-praised ProjectionLab feature. Shows the "money flow" gestalt in a single view. |
| Historical sequence backtest | Run the projection against actual historical return sequences: 1929, 1966, 2000, 2008. Shows how robust the plan is to real historical crashes — more persuasive than MC for many users. |
| Milestone / goal system | Structured goal cards (FIRE date, house purchase, university fund, mortgage free) with progress bars on the dashboard. Each milestone links to the projection year where it's achieved. |
| Interactive scenario sliders | Real-time sliders on the timeline chart: drag retirement age, savings rate, or property growth and see the FIRE date update instantly without re-running the full projection. |
| Portfolio heatmap | Account × year grid showing value. Colour intensity = growth. Lets users spot which accounts are working hardest. |
| Mortgage comparison wizard | Side-by-side table: current rate vs remortgage scenario. Shows break-even on arrangement fees and total interest saving. |

---

## Phase 10 · Data Import & Record Ingest
*Reduces manual-entry friction without requiring third-party API connections.*

| Deliverable | Notes |
|---|---|
| Bank statement ingest (CSV/OFX) | Upload a bank or credit card statement export and have LifeLedger parse it into the emergency fund / current account balance. Supports the standard OFX/QFX format (exported by most UK banks) and generic CSV with column mapping. No API, no credentials — just a file the user downloads from their own bank portal. |
| Broker CSV import | Import holdings from broker statement CSVs: Vanguard, Hargreaves Lansdown, AJ Bell, Interactive Brokers, Freetrade. Map broker column names to LifeLedger account types and auto-populate units, price, and total value. |
| Pension statement PDF parser | Extract current pot value and employer/employee contribution rates from PDF pension statements (ReportLab + pdfplumber). Handles the standard layouts from Nest, People's Pension, Standard Life, Aviva. |
| Spending category import | Upload a Monzo, Starling, or YNAB CSV export; map spending categories to LifeLedger expense buckets; update annual spend assumptions from actuals. |
| ISIN resolver | Resolve any ISIN to a yfinance ticker symbol using the OpenFIGI API. Removes the need to manually find ticker symbols for holdings. |
| Price staleness alerts | Dashboard banner when any holding price is >24h stale with one-click refresh. |
| Import history log | Audit trail of every file ingested: filename, date, accounts affected, values changed. Lets the user undo an import if the file was wrong. |
| Google Drive auto-backup | Scheduled upload of `data/scenarios/` to Drive (already partially configured in `lifeledger_config.yaml`; needs the OAuth flow wired to the Settings screen). |

---

## Phase 11 · Collaborative & Shared Planning
*Addresses the couples use case and IFA sharing.*

| Deliverable | Notes |
|---|---|
| Read-only share link | Generate a time-limited URL that shows a read-only dashboard view. For sharing with an IFA or a partner who doesn't need edit access. |
| Multi-user scenario comments | Add comments to any scenario explaining assumptions. Useful when both partners contribute to the plan. |
| IFA export pack | PDF report preset formatted for sharing with an Independent Financial Adviser: assumptions page, source data table, regulatory disclaimer. Extends the Phase 6 `ifa_pack` preset. |
| Checkpoint notifications | HA automation trigger when net worth diverges from projection by >5%. Sends an alert to prompt a manual checkpoint review. |

---

## Phase 12 · Intelligence & Automation
*AI-assisted planning, the long-term differentiator.*

| Deliverable | Notes |
|---|---|
| Planning coach | Rule-based alert system surfacing actionable insights: "You have £8k of basic-rate band unfilled — consider a £8k SIPP withdrawal this year", "Your ISA allowance expires in 47 days — you have £12k unused", "NI gap for 2019/20 closes for top-up in April 2026". |
| Natural language scenario builder | Type "What if I retire at 55 and sell the house in 2035?" → engine parses intent, creates a scenario YAML diff, runs the projection, and shows the delta vs base. |
| Annual review automation | On 1 April each year, generate a Full Annual PDF report automatically, upload to Drive, and send an HA notification. |
| Monte Carlo insight surfacing | After MC run, automatically identify: the year where P10 diverges from P50 (sequence-of-returns risk window), the contribution change that shifts FIRE by 1 year, the scenarios where the portfolio is exhausted before age 90. |
| Spending pattern analysis | If Open Banking is connected: compare actual monthly spend to expense bucket assumptions. Flag where actuals consistently exceed the plan. |

---

## Platform / Infrastructure (ongoing)

| Item | Notes |
|---|---|
| PWA manifest + service worker | Make the web app installable on iOS/Android home screen with offline caching of the last projection result. |
| HA Ingress path fix verification | Confirm `base: './'` and `getApiBase()` work correctly end-to-end when accessed via Ingress (see Phase 6 fix). |
| CLAUDE.md refresh | Update the agent briefing document after each phase completes. |
| Regression test expansion | Add tests for Phase 7 generational figures. Add golden-file tests for PDF report output (compare page count, section count). |
| Dependency updates | Pin all npm and pip deps to exact versions; add `dependabot.yml` for automated PRs. |

---

## Priority recommendation

For the most impact with the least new engine work:

1. **Phase 8 (Tax Optimiser)** — The band-filler and UFPLS support alone address the most common real-world planning question ("how do I draw down tax-efficiently?") and directly beat ProjectionLab's biggest UK gap.
2. **Phase 9 (Sankey + Milestone system)** — Primarily frontend; dramatically improves daily usability and makes the tool feel complete rather than analytical.
3. **Phase 7 (Generational)** — The biggest differentiation play; no consumer tool does this. High effort, high reward.
4. **Phase 10 (Open Banking)** — Removes the main friction point for ongoing use.
