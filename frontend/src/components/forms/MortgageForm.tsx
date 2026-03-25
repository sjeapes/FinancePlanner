/**
 * MortgageForm.tsx
 * Full form for a Mortgage including rate periods and lump sum payments.
 */

import type { CSSProperties } from 'react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

interface FormValues {
  id: string
  name: string
  property_id: string
  mortgage_type: string
  original_principal: number
  current_balance: number
  currency: string
  start_date: string
  term_years: number
}

interface RatePeriodRow {
  start_date: string
  end_date: string
  rate: string
  rate_type: string
}

interface LumpSumRow {
  date: string
  amount: string
  label: string
}

interface Props {
  mortgage?: any
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

function emptyRatePeriod(): RatePeriodRow {
  return { start_date: '', end_date: '', rate: '', rate_type: 'fixed' }
}

function emptyLumpSum(): LumpSumRow {
  return { date: '', amount: '', label: '' }
}

export function MortgageForm({ mortgage, onSave, onCancel }: Props) {
  const isEditing = !!mortgage

  const rawPeriods: RatePeriodRow[] = (mortgage?.rate_periods ?? []).map((p: any) => ({
    start_date: p.start_date ?? '',
    end_date: p.end_date ?? '',
    rate: p.rate !== undefined ? String(parseFloat((p.rate * 100).toPrecision(6))) : '',
    rate_type: p.rate_type ?? 'fixed',
  }))

  const rawLumps: LumpSumRow[] = (mortgage?.lump_sum_payments ?? []).map((l: any) => ({
    date: l.date ?? '',
    amount: l.amount !== undefined ? String(l.amount) : '',
    label: l.label ?? '',
  }))

  const [ratePeriods, setRatePeriods] = useState<RatePeriodRow[]>(rawPeriods.length > 0 ? rawPeriods : [emptyRatePeriod()])
  const [lumpSums, setLumpSums] = useState<LumpSumRow[]>(rawLumps)

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      id: mortgage?.id ?? '',
      name: mortgage?.name ?? '',
      property_id: mortgage?.property_id ?? '',
      mortgage_type: mortgage?.mortgage_type ?? 'repayment',
      original_principal: mortgage?.original_principal ?? 0,
      current_balance: mortgage?.current_balance ?? 0,
      currency: mortgage?.currency ?? 'GBP',
      start_date: mortgage?.start_date ?? '',
      term_years: mortgage?.term_years ?? 25,
    },
  })

  function updatePeriod(idx: number, field: keyof RatePeriodRow, value: string) {
    setRatePeriods((prev) => prev.map((p, i) => (i === idx ? { ...p, [field]: value } : p)))
  }

  function updateLump(idx: number, field: keyof LumpSumRow, value: string) {
    setLumpSums((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)))
  }

  function onSubmit(values: FormValues) {
    const parsedPeriods = ratePeriods
      .filter((p) => p.start_date.trim() !== '')
      .map((p) => ({
        start_date: p.start_date,
        end_date: p.end_date || null,
        rate: parseFloat(p.rate) / 100 || 0,
        rate_type: p.rate_type,
      }))

    const parsedLumps = lumpSums
      .filter((l) => l.date.trim() !== '')
      .map((l) => ({
        date: l.date,
        amount: parseFloat(l.amount) || 0,
        label: l.label,
      }))

    const payload: any = {
      ...mortgage,
      id: values.id,
      name: values.name,
      property_id: values.property_id,
      mortgage_type: values.mortgage_type,
      original_principal: Number(values.original_principal),
      current_balance: Number(values.current_balance),
      currency: values.currency,
      start_date: values.start_date,
      term_years: Number(values.term_years),
      rate_periods: parsedPeriods,
      lump_sum_payments: parsedLumps,
    }
    onSave(payload)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ padding: '16px 0' }}>
      <div style={sectionHeadStyle}>Mortgage</div>
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
          <label style={labelStyle}>Property ID</label>
          <input {...register('property_id', { required: 'Property ID is required' })} style={inputStyle} placeholder="e.g. london_house" />
          {errors.property_id && <div style={errorStyle}>{errors.property_id.message}</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Mortgage Type</label>
          <select {...register('mortgage_type', { required: true })} style={inputStyle}>
            <option value="repayment">Repayment</option>
            <option value="interest_only">Interest Only</option>
          </select>
          {errors.mortgage_type && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Original Principal</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={100}
              {...register('original_principal', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.original_principal && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Current Balance</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={100}
              {...register('current_balance', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.current_balance && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Currency</label>
          <input {...register('currency', { required: true })} style={inputStyle} />
          {errors.currency && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Start Date</label>
          <input type="date" {...register('start_date', { required: true })} style={inputStyle} />
          {errors.start_date && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Term (Years)</label>
          <input
            type="number"
            {...register('term_years', { required: true, min: 1, max: 50 })}
            style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
          />
          {errors.term_years && <div style={errorStyle}>Must be 1–50</div>}
        </div>
      </div>

      <div style={{ ...sectionHeadStyle, marginTop: 20 }}>Rate Periods</div>
      {ratePeriods.map((p, idx) => (
        <div
          key={idx}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr 1fr auto',
            gap: 10,
            alignItems: 'end',
            marginBottom: 10,
          }}
        >
          <div>
            <label style={labelStyle}>Start Date</label>
            <input type="date" value={p.start_date} onChange={(e) => updatePeriod(idx, 'start_date', e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>End Date (opt)</label>
            <input type="date" value={p.end_date} onChange={(e) => updatePeriod(idx, 'end_date', e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Rate</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                type="number"
                step={0.001}
                value={p.rate}
                onChange={(e) => updatePeriod(idx, 'rate', e.target.value)}
                style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
              />
              <span style={{ color: '#8fa3b8', fontSize: 13 }}>%</span>
            </div>
          </div>
          <div>
            <label style={labelStyle}>Rate Type</label>
            <select value={p.rate_type} onChange={(e) => updatePeriod(idx, 'rate_type', e.target.value)} style={inputStyle}>
              <option value="fixed">Fixed</option>
              <option value="variable">Variable</option>
              <option value="tracker">Tracker</option>
            </select>
          </div>
          <button
            type="button"
            onClick={() => setRatePeriods((prev) => prev.filter((_, i) => i !== idx))}
            style={{ background: 'transparent', border: '1px solid #e05252', color: '#e05252', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: 12 }}
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => setRatePeriods((prev) => [...prev, emptyRatePeriod()])}
        style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.15)', color: '#8fa3b8', borderRadius: 6, padding: '5px 14px', cursor: 'pointer', fontSize: 12, marginBottom: 20 }}
      >
        + Add Rate Period
      </button>

      <div style={{ ...sectionHeadStyle, marginTop: 8 }}>Lump Sum Payments</div>
      {lumpSums.map((l, idx) => (
        <div
          key={idx}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 2fr auto',
            gap: 10,
            alignItems: 'end',
            marginBottom: 10,
          }}
        >
          <div>
            <label style={labelStyle}>Date</label>
            <input type="date" value={l.date} onChange={(e) => updateLump(idx, 'date', e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Amount</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
              <input
                type="number"
                step={100}
                value={l.amount}
                onChange={(e) => updateLump(idx, 'amount', e.target.value)}
                style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
              />
            </div>
          </div>
          <div>
            <label style={labelStyle}>Label</label>
            <input value={l.label} onChange={(e) => updateLump(idx, 'label', e.target.value)} style={inputStyle} />
          </div>
          <button
            type="button"
            onClick={() => setLumpSums((prev) => prev.filter((_, i) => i !== idx))}
            style={{ background: 'transparent', border: '1px solid #e05252', color: '#e05252', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: 12 }}
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => setLumpSums((prev) => [...prev, emptyLumpSum()])}
        style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.15)', color: '#8fa3b8', borderRadius: 6, padding: '5px 14px', cursor: 'pointer', fontSize: 12, marginBottom: 20 }}
      >
        + Add Lump Sum Payment
      </button>

      <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
        <button
          type="submit"
          style={{ background: '#0e9aad', color: '#fff', border: 'none', borderRadius: 6, padding: '7px 20px', fontSize: 13, cursor: 'pointer', fontWeight: 500 }}
        >
          Save
        </button>
        <button
          type="button"
          onClick={onCancel}
          style={{ background: 'transparent', color: '#8fa3b8', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 6, padding: '7px 16px', fontSize: 13, cursor: 'pointer' }}
        >
          Cancel
        </button>
      </div>
    </form>
  )
}
