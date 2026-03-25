/**
 * SavingsForm.tsx
 * Full form for a SavingsAccount including interest rate periods table.
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
  annual_contribution: number
}

interface RatePeriodRow {
  start_date: string
  end_date: string
  rate: string
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

function emptyPeriod(): RatePeriodRow {
  return { start_date: '', end_date: '', rate: '' }
}

export function SavingsForm({ account, people, onSave, onCancel }: Props) {
  const isEditing = !!account

  const rawPeriods: RatePeriodRow[] = (account?.interest_rate_periods ?? []).map((p: any) => ({
    start_date: p.start_date ?? '',
    end_date: p.end_date ?? '',
    rate: p.rate !== undefined ? String(parseFloat((p.rate * 100).toPrecision(6))) : '',
  }))

  const [periods, setPeriods] = useState<RatePeriodRow[]>(rawPeriods.length > 0 ? rawPeriods : [emptyPeriod()])

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      id: account?.id ?? '',
      name: account?.name ?? '',
      account_type: account?.account_type ?? 'general',
      current_value: account?.current_value ?? 0,
      currency: account?.currency ?? 'GBP',
      owner_id: account?.owner_id ?? '',
      annual_contribution: account?.annual_contribution ?? 0,
    },
  })

  function addPeriod() {
    setPeriods((prev) => [...prev, emptyPeriod()])
  }

  function removePeriod(idx: number) {
    setPeriods((prev) => prev.filter((_, i) => i !== idx))
  }

  function updatePeriod(idx: number, field: keyof RatePeriodRow, value: string) {
    setPeriods((prev) => prev.map((p, i) => (i === idx ? { ...p, [field]: value } : p)))
  }

  function onSubmit(values: FormValues) {
    const parsedPeriods = periods
      .filter((p) => p.start_date.trim() !== '')
      .map((p) => ({
        start_date: p.start_date,
        end_date: p.end_date || null,
        rate: parseFloat(p.rate) / 100 || 0,
      }))

    const payload: any = {
      ...account,
      id: values.id,
      name: values.name,
      account_type: values.account_type,
      current_value: Number(values.current_value),
      currency: values.currency,
      owner_id: values.owner_id,
      annual_contribution: Number(values.annual_contribution),
      interest_rate_periods: parsedPeriods,
    }
    onSave(payload)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ padding: '16px 0' }}>
      <div style={sectionHeadStyle}>Savings Account</div>
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
            <option value="cash_ISA">Cash ISA</option>
            <option value="ISA">ISA</option>
            <option value="GIA">GIA</option>
            <option value="LISA">LISA</option>
            <option value="general">General</option>
            <option value="savings">Savings</option>
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
          <label style={labelStyle}>Annual Contribution</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={100}
              {...register('annual_contribution', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.annual_contribution && <div style={errorStyle}>Required</div>}
        </div>
      </div>

      <div style={{ ...sectionHeadStyle, marginTop: 20 }}>Interest Rate Periods</div>
      {periods.map((p, idx) => (
        <div
          key={idx}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr auto',
            gap: 10,
            alignItems: 'end',
            marginBottom: 10,
          }}
        >
          <div>
            <label style={labelStyle}>Start Date</label>
            <input
              type="date"
              value={p.start_date}
              onChange={(e) => updatePeriod(idx, 'start_date', e.target.value)}
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>End Date (optional)</label>
            <input
              type="date"
              value={p.end_date}
              onChange={(e) => updatePeriod(idx, 'end_date', e.target.value)}
              style={inputStyle}
            />
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
          <button
            type="button"
            onClick={() => removePeriod(idx)}
            style={{
              background: 'transparent',
              border: '1px solid #e05252',
              color: '#e05252',
              borderRadius: 4,
              padding: '4px 8px',
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={addPeriod}
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
        + Add Period
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
