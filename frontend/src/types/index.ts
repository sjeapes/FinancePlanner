// ── Enums ──────────────────────────────────────────────────────────────────────

export type TaxTreatment = 'paye' | 'self_employed' | 'dividend' | 'rental' | 'pension' | 'exempt'
export type AccountType = 'isa' | 'gia' | 'sipp' | 'lisa' | 'current' | 'savings'
export type PensionType = 'dc' | 'db' | 'sipp' | 'workplace'
export type MortgageType = 'repayment' | 'interest_only'
export type TrackingMode = 'total_value' | 'units'
export type DrawdownMode = 'pct_swr' | 'fixed_amount' | 'annuity'
export type EventType = 'inflow' | 'outflow'
export type Jurisdiction = 'uk' | 'us_federal' | 'ireland' | 'generic'

// ── Sub-models ─────────────────────────────────────────────────────────────────

export interface TaxBand {
  lower: number
  upper: number | null
  rate: number
}

export interface InterestRatePeriod {
  start_date: string
  end_date: string | null
  rate: number
}

export interface RatePeriod {
  start_date: string
  end_date: string | null
  rate: number
}

export interface LumpSumPayment {
  date: string
  amount: number
}

export interface DrawdownConfig {
  mode: DrawdownMode
  rate: number
  fixed_amount: number | null
  tfls_taken: boolean
}

export interface Contribution {
  destination_id: string
  fraction: number
}

export interface SymbolLink {
  provider: string
  ticker: string
  isin: string | null
  last_fetched_price: number | null
  refresh_schedule: string
}

// ── Main models ────────────────────────────────────────────────────────────────

export interface StatePension {
  qualifying_years: number
  weekly_amount: number
  start_age: number
  deferred: boolean
}

export interface Person {
  id: string
  name: string
  date_of_birth: string
  retirement_age: number
  life_expectancy: number
  state_pension: StatePension | null
}

export interface IncomeSource {
  id: string
  name: string
  gross_amount: number
  tax_treatment: TaxTreatment
  owner_id: string
  start_date: string
  end_date: string | null
  growth_rate: number
  contributions: Contribution[]
}

export interface SavingsAccount {
  id: string
  name: string
  account_type: AccountType
  balance: number
  rate_periods: InterestRatePeriod[]
}

export interface InvestmentHolding {
  id: string
  name: string
  ticker: string | null
  tracking_mode: TrackingMode
  total_value: number | null
  units: number | null
  price_per_unit: number | null
  assumed_growth_rate: number
  symbol_link: SymbolLink | null
}

export interface InvestmentAccount {
  id: string
  name: string
  account_type: AccountType
  holdings: InvestmentHolding[]
}

export interface PensionFund {
  id: string
  name: string
  pension_type: PensionType
  owner_id: string
  current_value: number
  assumed_growth_rate: number
  employer_contribution_rate: number
  drawdown: DrawdownConfig
}

export interface PropertyAsset {
  id: string
  name: string
  current_value: number
  growth_rate: number
  rental_income_annual: number
  mortgage_id: string | null
}

export interface Mortgage {
  id: string
  name: string
  outstanding_balance: number
  mortgage_type: MortgageType
  rate_periods: RatePeriod[]
  lump_sum_payments: LumpSumPayment[]
}

export interface LifeEvent {
  id: string
  name: string
  date: string
  amount: number
  event_type: EventType
  target_account_id: string | null
}

export interface ExpenseBucket {
  id: string
  name: string
  annual_amount: number
  start_date: string
  end_date: string | null
  inflation_linked: boolean
}

export interface FIRETarget {
  target_net_worth: number
  swr: number
  fire_type: string
  annual_expenses: number
}

export interface TaxBandGroup {
  lower: number
  upper: number | null
  rate: number
}

export interface TaxProfile {
  id: string
  jurisdiction: Jurisdiction
  income_tax_bands: TaxBandGroup[]
  ni_bands: TaxBandGroup[]
  personal_allowance: number
  cgt_rate_basic: number
  cgt_rate_higher: number
  cgt_annual_exempt: number
}

export interface Scenario {
  id: string
  name: string
  is_base: boolean
  people: Person[]
  income_sources: IncomeSource[]
  savings_accounts: SavingsAccount[]
  investment_accounts: InvestmentAccount[]
  pension_funds: PensionFund[]
  properties: PropertyAsset[]
  mortgages: Mortgage[]
  life_events: LifeEvent[]
  expense_buckets: ExpenseBucket[]
  fire_target: FIRETarget | null
}

export interface Checkpoint {
  id: string
  date: string
  total_net_worth: number
  notes: string | null
}

export interface AppConfig {
  currency: string
  projection_start: number
  projection_end: number
  inflation_rate: number
  monte_carlo_runs: number
}

// ── Engine results ─────────────────────────────────────────────────────────────

export interface AccountBreakdown {
  savings_total: number
  investments_total: number
  pensions_total: number
  property_net: number
  cash_total: number
}

export interface AccountSnapshotOut {
  account_id: string
  name: string
  account_type: string
  value: number
  contributions_in: number
  growth_amount: number
}

export interface IncomeSnapshotOut {
  source_id: string
  name: string
  person_id: string
  gross: number
  net_income: number
  income_tax: number
  national_insurance: number
  effective_rate: number
  contributions_routed: number
}

export interface YearSnapshot {
  year: number
  total_net_worth: number
  total_assets: number
  total_liabilities: number
  total_gross_income: number
  total_net_income: number
  total_contributions: number
  total_expenses: number
  fire_achieved: boolean
  fire_coverage: number
  income_coverage: number
  ages: Record<string, number>
  accounts: Record<string, AccountSnapshotOut>
  income_sources: IncomeSnapshotOut[]
  events: string[]
}

export interface TimelineResult {
  scenario_id: string
  scenario_name: string
  fire_year: number | null
  years: YearSnapshot[]
}

export interface MonteCarloResult {
  prob_fire: number
  p10: number[]
  p25: number[]
  p50: number[]
  p75: number[]
  p90: number[]
  years: number[]
}

// ── Tax ────────────────────────────────────────────────────────────────────────

export interface TaxResult {
  gross_income: number
  income_tax: number
  national_insurance: number
  net_income: number
  effective_rate: number
  marginal_rate: number
}

// ── Market data ────────────────────────────────────────────────────────────────

export interface SymbolResult {
  ticker: string
  name: string
  exchange: string
  currency: string
}

export interface PricePoint {
  date: string
  price: number
  volume: number | null
}

// ── Phase 3: Scenario builder types ────────────────────────────────────────────

export interface ScenarioTemplate {
  id: string
  name: string
  path: string
}

export interface ScenarioComparisonRow {
  scenario_id: string
  scenario_name: string
  fire_year: number | null
  net_worth_at_years: Record<string, number>
}

// ── API request types ──────────────────────────────────────────────────────────

export interface SimulateRequest {
  scenario_path: string
  include_breakdown?: boolean
}

export interface MonteCarloRequest {
  scenario_path: string
  n_simulations?: number
  seed?: number
}

export interface TaxCalculateRequest {
  gross: number
  tax_treatment: TaxTreatment
  jurisdiction: Jurisdiction
  pension_contributions?: number
}
