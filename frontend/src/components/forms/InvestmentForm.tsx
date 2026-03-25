/**
 * InvestmentForm.tsx
 * Full form for an InvestmentAccount including per-holding rows.
 */

import type { CSSProperties } from 'react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

interface FormValues {
  id: string
  name: string
  account_type: string
  current_value: number
  currency: string
  owner_id: string
  assumed_growth_rate: number
}

interface HoldingRow {
  id: string
  name: string
  tracking_mode: 'total_value' | 'units'
  total_value: string
  units: string
  price_per_unit: string
  assumed_growth_rate: string
  symbol: string
}

interface Props {
  account?: any
  people: any[]
  onSave: (data: any) => void
  onCancel: () => void
}

const inputStyle: CSSProperties = {
  background: '#0f1b2d',
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 6,
  color: '#e8edf2',
  padding: '6px 10px',
  fontSize: 13,
  width: '100%',
  boxSizing: 'border-box',
}

const labelStyle: CSSProperties = {
  display: 'block',
  fontSize: 11,
  color: '#8fa3b8',
  marginBottom: 4,
  fontWeight: 500,
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
}

const fieldStyle: CSSProperties = { marginBottom: 14 }
const errorStyle: CSSProperties = { color: '#e05252', fontSize: 11, marginTop: 3 }

const sectionHeadStyle: CSSProperties = {
  color: '#8fa3b8',
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.8px',
  marginBottom: 12,
  marginTop: 4,
  borderBottom: '1px solid rgba(255,255,255,0.07)',
  paddingBottom: 6,
}

function emptyHolding(): HoldingRow {
  return { id: '', name: '', tracking_mode: 'total_value', total_value: '', units: '', price_per_unit: '', assumed_growth_rate: '', symbol: '' }
}

function holdingFromRaw(h: any): HoldingRow {
  return {
    id: h.id ?? '',
    name: h.name ?? '',
    tracking_mode: h.tracking_mode === 'units' ? 'units' : 'total_value',
    total_value: h.total_value !== undefined ? String(h.total_value) : '',
    units: h.units !== undefined ? String(h.units) : '',
    price_per_unit: h.price_per_unit !== undefined ? String(h.price_per_unit) : '',
    assumed_growth_rate: h.assumed_growth_rate !== undefined ? String(parseFloat((h.assumed_growth_rate * 100).toPrecision(6))) : '',
    symbol: h.symbol_link?.symbol ?? '',
  }
}

export function InvestmentForm({ account, people, onSave, onCancel }: Props) {
  const isEditing = !!account

  const [holdings, setHoldings] = useState<HoldingRow[]>(
    account?.holdings?.length > 0 ? account.holdings.map(holdingFromRaw) : []
  )

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      id: account?.id ?? '',
      name: account?.name ?? '',
      account_type: account?.account_type ?? 'ISA',
      current_value: account?.current_value ?? 0,
      currency: account?.currency ?? 'GBP',
      owner_id: account?.owner_id ?? '',
      assumed_growth_rate:
        account?.assumed_growth_rate !== undefined
          ? parseFloat((account.assumed_growth_rate * 100).toPrecision(6))
          : 7,
    },
  })

  function addHolding() {
    setHoldings((prev) => [...prev, emptyHolding()])
  }

  function removeHolding(idx: number) {
    setHoldings((prev) => prev.filter((_, i) => i !== idx))
  }

  function updateHolding(idx: number, field: keyof HoldingRow, value: string) {
    setHoldings((prev) => prev.map((h, i) => (i === idx ? { ...h, [field]: value } : h)))
  }

  function toggleMode(idx: number) {
    setHoldings((prev) =>
      prev.map((h, i) =>
        i === idx
          ? { ...h, tracking_mode: h.tracking_mode === 'total_value' ? 'units' : 'total_value' }
          : h
      )
    )
  }

  function onSubmit(values: FormValues) {
    const parsedHoldings = holdings
      .filter((h) => h.name.trim() !== '')
      .map((h) => {
        const holding: any = {
          id: h.id,
          name: h.name,
          tracking_mode: h.tracking_mode,
          assumed_growth_rate: parseFloat(h.assumed_growth_rate) / 100 || 0,
        }
        if (h.tracking_mode === 'total_value') {
          holding.total_value = parseFloat(h.total_value) || 0
        } else {
          holding.units = parseFloat(h.units) || 0
          holding.price_per_unit = parseFloat(h.price_per_unit) || 0
        }
        if (h.symbol) {
          holding.symbol_link = { symbol: h.symbol, provider: 'yfinance', auto_refresh: true, refresh_schedule: 'daily' }
        }
        return holding
      })

    const payload: any = {
      ...account,
      id: values.id,
      name: values.name,
      account_type: values.account_type,
      current_value: Number(values.current_value),
      currency: values.currency,
      owner_id: values.owner_id,
      assumed_growth_rate: Number(values.assumed_growth_rate) / 100,
      holdings: parsedHoldings,
    }
    onSave(payload)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ padding: '16px 0' }}>
      <div style={sectionHeadStyle}>Investment Account</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={fieldStyle}>
          <label style={labelStyle}>ID</label>
          <input
            {...register('id', { required: 'ID is required' })}
            style={{ ...inputStyle, opacity: isEditing ? 0.6 : 1 }}
            readOnly={isEditing}
          />
          {errors.id && <div style={errorStyle}>{errors.id.message}</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Name</label>
          <input {...register('name', { required: 'Name is required' })} style={inputStyle} />
          {errors.name && <div style={errorStyle}>{errors.name.message}</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Account Type</label>
          <select {...register('account_type', { required: true })} style={inputStyle}>
            <option value="ISA">ISA</option>
            <option value="GIA">GIA</option>
            <option value="LISA">LISA</option>
          </select>
          {errors.account_type && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Current Value</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={100}
              {...register('current_value', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.current_value && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Currency</label>
          <input {...register('currency', { required: true })} style={inputStyle} />
          {errors.currency && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Owner</label>
          <select {...register('owner_id', { required: 'Owner is required' })} style={inputStyle}>
            <option value="">— Select person —</option>
            {people.map((p: any) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          {errors.owner_id && <div style={errorStyle}>{errors.owner_id.message}</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Assumed Growth Rate</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="number"
              step={0.001}
              {...register('assumed_growth_rate', { required: true })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>%</span>
          </div>
          {errors.assumed_growth_rate && <div style={errorStyle}>Required</div>}
        </div>
      </div>

      <div style={{ ...sectionHeadStyle, marginTop: 20 }}>Holdings</div>
      {holdings.map((h, idx) => (
        <div
          key={idx}
          style={{
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 8,
            padding: '12px',
            marginBottom: 12,
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
            <div>
              <label style={labelStyle}>Holding ID</label>
              <input
                value={h.id}
                onChange={(e) => updateHolding(idx, 'id', e.target.value)}
                style={inputStyle}
                placeholder="e.g. vwrp_isa"
              />
            </div>
            <div>
              <label style={labelStyle}>Name</label>
              <input
                value={h.name}
                onChange={(e) => updateHolding(idx, 'name', e.target.value)}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Symbol (Ticker)</label>
              <input
                value={h.symbol}
                onChange={(e) => updateHolding(idx, 'symbol', e.target.value)}
                style={inputStyle}
                placeholder="e.g. VWRP.L"
              />
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 10, alignItems: 'end' }}>
            <div>
              <label style={labelStyle}>Tracking Mode</label>
              <button
                type="button"
                onClick={() => toggleMode(idx)}
                style={{
                  background: h.tracking_mode === 'total_value' ? 'rgba(14,154,173,0.2)' : 'rgba(212,168,67,0.2)',
                  border: `1px solid ${h.tracking_mode === 'total_value' ? '#0e9aad' : '#d4a843'}`,
                  color: h.tracking_mode === 'total_value' ? '#0e9aad' : '#d4a843',
                  borderRadius: 6,
                  padding: '6px 12px',
                  cursor: 'pointer',
                  fontSize: 12,
                  width: '100%',
                }}
              >
                {h.tracking_mode === 'total_value' ? 'Total Value' : 'Units × Price'}
              </button>
            </div>
            {h.tracking_mode === 'total_value' ? (
              <div>
                <label style={labelStyle}>Total Value</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
                  <input
                    type="number"
                    step={100}
                    value={h.total_value}
                    onChange={(e) => updateHolding(idx, 'total_value', e.target.value)}
                    style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
                  />
                </div>
              </div>
            ) : (
              <>
                <div>
                  <label style={labelStyle}>Units</label>
                  <input
                    type="number"
                    step={0.0001}
                    value={h.units}
                    onChange={(e) => updateHolding(idx, 'units', e.target.value)}
                    style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Price Per Unit</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
                    <input
                      type="number"
                      step={0.01}
                      value={h.price_per_unit}
                      onChange={(e) => updateHolding(idx, 'price_per_unit', e.target.value)}
                      style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
                    />
                  </div>
                </div>
              </>
            )}
            <div>
              <label style={labelStyle}>Growth Rate</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <input
                  type="number"
                  step={0.001}
                  value={h.assumed_growth_rate}
                  onChange={(e) => updateHolding(idx, 'assumed_growth_rate', e.target.value)}
                  style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
                />
                <span style={{ color: '#8fa3b8', fontSize: 13 }}>%</span>
              </div>
            </div>
          </div>
          <div style={{ textAlign: 'right', marginTop: 8 }}>
            <button
              type="button"
              onClick={() => removeHolding(idx)}
              style={{
                background: 'transparent',
                border: '1px solid #e05252',
                color: '#e05252',
                borderRadius: 4,
                padding: '3px 10px',
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              Remove Holding
            </button>
          </div>
        </div>
      ))}
      <button
        type="button"
        onClick={addHolding}
        style={{
          background: 'transparent',
          border: '1px solid rgba(255,255,255,0.15)',
          color: '#8fa3b8',
          borderRadius: 6,
          padding: '5px 14px',
          cursor: 'pointer',
          fontSize: 12,
          marginBottom: 20,
        }}
      >
        + Add Holding
      </button>

      <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
        <button
          type="submit"
          style={{
            background: '#0e9aad',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            padding: '7px 20px',
            fontSize: 13,
            cursor: 'pointer',
            fontWeight: 500,
          }}
        >
          Save
        </button>
        <button
          type="button"
          onClick={onCancel}
          style={{
            background: 'transparent',
            color: '#8fa3b8',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 6,
            padding: '7px 16px',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          Cancel
        </button>
      </div>
    </form>
  )
}
