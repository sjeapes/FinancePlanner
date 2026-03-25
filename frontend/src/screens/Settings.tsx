import { useState } from 'react'
import { PageHeader } from '../components/layout/PageHeader'
import { useConfigStore } from '../store/configStore'
import { useCalculateTax } from '../api/hooks/useTax'
import type { TaxResult, Jurisdiction, TaxTreatment } from '../types'

export function Settings() {
  const { currency, projectionStart, projectionEnd, inflationRate, setConfig } = useConfigStore()
  const calcTax = useCalculateTax()

  // API key state
  const [avKey, setAvKey] = useState('')
  const [fhKey, setFhKey] = useState('')

  // Tax calculator state
  const [taxGross, setTaxGross] = useState('95000')
  const [taxResult, setTaxResult] = useState<TaxResult | null>(null)

  async function handleTaxCalc() {
    const result = await calcTax.mutateAsync({
      gross: parseFloat(taxGross) || 0,
      tax_treatment: 'paye' as TaxTreatment,
      jurisdiction: 'uk' as Jurisdiction,
    })
    setTaxResult(result)
  }

  return (
    <div>
      <PageHeader title="Settings" subtitle="Application configuration" />

      <div className="grid grid-cols-2 gap-4">
        {/* Config values */}
        <div
          className="rounded-xl p-5"
          style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <div
            className="text-xs font-semibold uppercase tracking-wide mb-4"
            style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
          >
            Projection Settings
          </div>
          <div className="space-y-4">
            {/* Currency */}
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: '#8fa3b8' }}>
                Currency
              </label>
              <select
                value={currency}
                onChange={(e) => setConfig({ currency: e.target.value })}
                className="w-full px-3 py-2 rounded text-sm font-mono"
                style={{
                  background: '#1d2f47',
                  border: '1px solid #243859',
                  color: '#e8edf2',
                  outline: 'none',
                }}
              >
                <option value="GBP">GBP (£)</option>
                <option value="USD">USD ($)</option>
                <option value="EUR">EUR (€)</option>
              </select>
            </div>

            {/* Projection range */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: '#8fa3b8' }}>
                  Start Year
                </label>
                <input
                  type="number"
                  value={projectionStart}
                  onChange={(e) => setConfig({ projectionStart: parseInt(e.target.value) || 2025 })}
                  className="w-full px-3 py-2 rounded text-sm font-mono"
                  style={{ background: '#1d2f47', border: '1px solid #243859', color: '#e8edf2', outline: 'none' }}
                />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: '#8fa3b8' }}>
                  End Year
                </label>
                <input
                  type="number"
                  value={projectionEnd}
                  onChange={(e) => setConfig({ projectionEnd: parseInt(e.target.value) || 2075 })}
                  className="w-full px-3 py-2 rounded text-sm font-mono"
                  style={{ background: '#1d2f47', border: '1px solid #243859', color: '#e8edf2', outline: 'none' }}
                />
              </div>
            </div>

            {/* Inflation */}
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: '#8fa3b8' }}>
                Inflation Rate
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  step="0.001"
                  value={inflationRate}
                  onChange={(e) => setConfig({ inflationRate: parseFloat(e.target.value) || 0.025 })}
                  className="flex-1 px-3 py-2 rounded text-sm font-mono"
                  style={{ background: '#1d2f47', border: '1px solid #243859', color: '#e8edf2', outline: 'none' }}
                />
                <span className="font-mono text-sm" style={{ color: '#8fa3b8' }}>
                  = {(inflationRate * 100).toFixed(1)}%
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* API Keys */}
        <div
          className="rounded-xl p-5"
          style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <div
            className="text-xs font-semibold uppercase tracking-wide mb-4"
            style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
          >
            Market Data API Keys
          </div>
          <p className="text-xs mb-4" style={{ color: '#8fa3b8', lineHeight: 1.5 }}>
            Keys are stored in local SQLite only — never in YAML files or synced to Google Drive.
          </p>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: '#8fa3b8' }}>
                Alpha Vantage
              </label>
              <div className="flex gap-2">
                <input
                  type="password"
                  placeholder="Enter API key…"
                  value={avKey}
                  onChange={(e) => setAvKey(e.target.value)}
                  className="flex-1 px-3 py-2 rounded text-sm font-mono"
                  style={{ background: '#1d2f47', border: '1px solid #243859', color: '#e8edf2', outline: 'none' }}
                />
                <button
                  onClick={() => {
                    if (avKey) console.log('Save AV key — Phase 2 API endpoint')
                  }}
                  className="px-3 py-2 rounded text-xs font-medium transition-all duration-150 cursor-pointer"
                  style={{
                    background: avKey ? '#0e9aad' : 'rgba(255,255,255,0.04)',
                    border: '1px solid transparent',
                    color: avKey ? '#fff' : '#8fa3b8',
                  }}
                >
                  Save
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: '#8fa3b8' }}>
                Finnhub
              </label>
              <div className="flex gap-2">
                <input
                  type="password"
                  placeholder="Enter API key…"
                  value={fhKey}
                  onChange={(e) => setFhKey(e.target.value)}
                  className="flex-1 px-3 py-2 rounded text-sm font-mono"
                  style={{ background: '#1d2f47', border: '1px solid #243859', color: '#e8edf2', outline: 'none' }}
                />
                <button
                  onClick={() => {
                    if (fhKey) console.log('Save Finnhub key — Phase 2 API endpoint')
                  }}
                  className="px-3 py-2 rounded text-xs font-medium transition-all duration-150 cursor-pointer"
                  style={{
                    background: fhKey ? '#0e9aad' : 'rgba(255,255,255,0.04)',
                    border: '1px solid transparent',
                    color: fhKey ? '#fff' : '#8fa3b8',
                  }}
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Live Tax Calculator Widget */}
      <div
        className="rounded-xl p-5 mt-4"
        style={{ background: '#162236', border: '1px solid rgba(255,255,255,0.07)' }}
      >
        <div
          className="text-xs font-semibold uppercase tracking-wide mb-4"
          style={{ color: '#8fa3b8', letterSpacing: '0.8px' }}
        >
          Live Tax Calculator
        </div>
        <div className="flex items-end gap-3">
          <div className="flex-1 max-w-xs">
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#8fa3b8' }}>
              Gross Income (£)
            </label>
            <input
              type="number"
              value={taxGross}
              onChange={(e) => setTaxGross(e.target.value)}
              className="w-full px-3 py-2 rounded text-sm font-mono"
              style={{ background: '#1d2f47', border: '1px solid #243859', color: '#e8edf2', outline: 'none' }}
            />
          </div>
          <button
            onClick={() => { void handleTaxCalc() }}
            disabled={calcTax.isPending}
            className="px-4 py-2 rounded text-xs font-semibold transition-all duration-150 cursor-pointer disabled:opacity-60"
            style={{ background: '#0e9aad', border: 'none', color: '#fff' }}
          >
            {calcTax.isPending ? 'Calculating…' : 'Calculate'}
          </button>
        </div>

        {taxResult && (
          <div className="mt-4 grid grid-cols-3 gap-3">
            {[
              { label: 'Net Income',     value: `£${taxResult.net_income.toLocaleString()}`,          color: '#2dbd7e' },
              { label: 'Income Tax',     value: `£${taxResult.income_tax.toLocaleString()}`,           color: '#e05252' },
              { label: 'NI',             value: `£${taxResult.national_insurance.toLocaleString()}`,   color: '#e05252' },
              { label: 'Effective Rate', value: `${(taxResult.effective_rate * 100).toFixed(1)}%`,     color: '#8fa3b8' },
              { label: 'Marginal Rate',  value: `${(taxResult.marginal_rate * 100).toFixed(0)}%`,      color: '#8fa3b8' },
            ].map(({ label, value, color }) => (
              <div
                key={label}
                className="rounded-lg px-3 py-2.5"
                style={{ background: '#1d2f47', border: '1px solid #243859' }}
              >
                <div className="text-xs mb-1" style={{ color: '#8fa3b8' }}>
                  {label}
                </div>
                <div className="font-mono text-sm font-medium" style={{ color }}>
                  {value}
                </div>
              </div>
            ))}
          </div>
        )}

        {calcTax.isError && (
          <p className="mt-3 text-xs" style={{ color: '#e05252' }}>
            Tax calculation failed — ensure the API is running.
          </p>
        )}
      </div>
    </div>
  )
}
