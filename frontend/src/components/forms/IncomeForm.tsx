/**
 * IncomeForm.tsx
 * Full form for an IncomeSource including contribution routing rows.
 */

import type { CSSProperties } from 'react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

interface FormValues {
  id: string
  name: string
  gross_annual: number
  person_id: string
  tax_treatment: string
  currency: string
  start_date: string
  end_date: string
  annual_growth_rate: number
}

interface ContributionRow {
  destination_account_id: string
  rate: string
  employer_top_up: string
  cap_annual: string
}

interface Props {
  income?: any
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

function emptyContribution(): ContributionRow {
  return { destination_account_id: '', rate: '', employer_top_up: '', cap_annual: '' }
}

export function IncomeForm({ income, people, onSave, onCancel }: Props) {
  const isEditing = !!income

  const rawContributions: ContributionRow[] = (income?.contributions ?? []).map((c: any) => ({
    destination_account_id: c.destination_account_id ?? '',
    rate: c.rate !== undefined ? String(parseFloat((c.rate * 100).toPrecision(6))) : '',
    employer_top_up: c.employer_top_up !== undefined ? String(parseFloat((c.employer_top_up * 100).toPrecision(6))) : '',
    cap_annual: c.cap_annual !== undefined ? String(c.cap_annual) : '',
  }))

  const [contributions, setContributions] = useState<ContributionRow[]>(
    rawContributions.length > 0 ? rawContributions : []
  )

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      id: income?.id ?? '',
      name: income?.name ?? '',
      gross_annual: income?.gross_annual ?? 0,
      person_id: income?.person_id ?? '',
      tax_treatment: income?.tax_treatment ?? 'PAYE',
      currency: income?.currency ?? 'GBP',
      start_date: income?.start_date ?? '',
      end_date: income?.end_date ?? '',
      annual_growth_rate:
        income?.annual_growth_rate !== undefined
          ? parseFloat((income.annual_growth_rate * 100).toPrecision(6))
          : 0,
    },
  })

  function addContribution() {
    setContributions((prev) => [...prev, emptyContribution()])
  }

  function removeContribution(idx: number) {
    setContributions((prev) => prev.filter((_, i) => i !== idx))
  }

  function updateContribution(idx: number, field: keyof ContributionRow, value: string) {
    setContributions((prev) =>
      prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c))
    )
  }

  function onSubmit(values: FormValues) {
    const parsedContributions = contributions
      .filter((c) => c.destination_account_id.trim() !== '')
      .map((c) => {
        const row: any = {
          destination_account_id: c.destination_account_id,
          rate: parseFloat(c.rate) / 100 || 0,
        }
        if (c.employer_top_up !== '') row.employer_top_up = parseFloat(c.employer_top_up) / 100
        if (c.cap_annual !== '') row.cap_annual = parseFloat(c.cap_annual)
        return row
      })

    const payload: any = {
      ...income,
      id: values.id,
      name: values.name,
      gross_annual: Number(values.gross_annual),
      person_id: values.person_id,
      tax_treatment: values.tax_treatment,
      currency: values.currency,
      start_date: values.start_date,
      end_date: values.end_date || null,
      annual_growth_rate: Number(values.annual_growth_rate) / 100,
      contributions: parsedContributions,
    }
    onSave(payload)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ padding: '16px 0' }}>
      <div style={sectionHeadStyle}>Income Source</div>
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
          <label style={labelStyle}>Gross Annual (£/year)</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={100}
              {...register('gross_annual', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.gross_annual && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Person</label>
          <select {...register('person_id', { required: 'Person is required' })} style={inputStyle}>
            <option value="">— Select person —</option>
            {people.map((p: any) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          {errors.person_id && <div style={errorStyle}>{errors.person_id.message}</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Tax Treatment</label>
          <select {...register('tax_treatment', { required: true })} style={inputStyle}>
            <option value="PAYE">PAYE</option>
            <option value="self_employed">Self Employed</option>
            <option value="dividend">Dividend</option>
            <option value="rental">Rental</option>
            <option value="pension">Pension</option>
            <option value="exempt">Exempt</option>
          </select>
          {errors.tax_treatment && <div style={errorStyle}>Required</div>}
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
          <label style={labelStyle}>End Date (optional)</label>
          <input type="date" {...register('end_date')} style={inputStyle} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Annual Growth Rate</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="number"
              step={0.001}
              {...register('annual_growth_rate', { required: true })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>%</span>
          </div>
          {errors.annual_growth_rate && <div style={errorStyle}>Required</div>}
        </div>
      </div>

      <div style={{ ...sectionHeadStyle, marginTop: 20 }}>Contribution Routing</div>
      {contributions.map((c, idx) => (
        <div
          key={idx}
          style={{
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 8,
            padding: '10px 12px',
            marginBottom: 10,
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 10, alignItems: 'end' }}>
            <div>
              <label style={labelStyle}>Destination Account ID</label>
              <input
                value={c.destination_account_id}
                onChange={(e) => updateContribution(idx, 'destination_account_id', e.target.value)}
                style={inputStyle}
                placeholder="e.g. vanguard_isa"
              />
            </div>
            <div>
              <label style={labelStyle}>Rate</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <input
                  type="number"
                  step={0.1}
                  value={c.rate}
                  onChange={(e) => updateContribution(idx, 'rate', e.target.value)}
                  style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
                />
                <span style={{ color: '#8fa3b8', fontSize: 13 }}>%</span>
              </div>
            </div>
            <div>
              <label style={labelStyle}>Employer Top-up</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <input
                  type="number"
                  step={0.1}
                  value={c.employer_top_up}
                  onChange={(e) => updateContribution(idx, 'employer_top_up', e.target.value)}
                  style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
                  placeholder="opt"
                />
                <span style={{ color: '#8fa3b8', fontSize: 13 }}>%</span>
              </div>
            </div>
            <div>
              <label style={labelStyle}>Cap Annual</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
                <input
                  type="number"
                  step={100}
                  value={c.cap_annual}
                  onChange={(e) => updateContribution(idx, 'cap_annual', e.target.value)}
                  style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
                  placeholder="opt"
                />
              </div>
            </div>
            <button
              type="button"
              onClick={() => removeContribution(idx)}
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
        </div>
      ))}
      <button
        type="button"
        onClick={addContribution}
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
        + Add Contribution Row
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
