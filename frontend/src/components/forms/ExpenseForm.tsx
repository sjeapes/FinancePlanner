/**
 * ExpenseForm.tsx
 * Full form for an ExpenseBucket.
 */

import type { CSSProperties } from 'react'
import { useForm } from 'react-hook-form'

interface FormValues {
  id: string
  name: string
  annual_amount: number
  currency: string
  start_date: string
  end_date: string
  inflation_linked: boolean
}

interface Props {
  expense?: any
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

export function ExpenseForm({ expense, onSave, onCancel }: Props) {
  const isEditing = !!expense

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      id: expense?.id ?? '',
      name: expense?.name ?? '',
      annual_amount: expense?.annual_amount ?? 0,
      currency: expense?.currency ?? 'GBP',
      start_date: expense?.start_date ?? '',
      end_date: expense?.end_date ?? '',
      inflation_linked: expense?.inflation_linked ?? true,
    },
  })

  function onSubmit(values: FormValues) {
    const payload: any = {
      ...expense,
      id: values.id,
      name: values.name,
      annual_amount: Number(values.annual_amount),
      currency: values.currency,
      start_date: values.start_date,
      end_date: values.end_date || null,
      inflation_linked: Boolean(values.inflation_linked),
    }
    onSave(payload)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ padding: '16px 0' }}>
      <div style={sectionHeadStyle}>Expense Bucket</div>
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
          <label style={labelStyle}>Annual Amount</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={100}
              {...register('annual_amount', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.annual_amount && <div style={errorStyle}>Required</div>}
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
        <div style={{ ...fieldStyle, display: 'flex', alignItems: 'center', gap: 10, gridColumn: '1 / -1' }}>
          <input
            type="checkbox"
            id="inflation_linked"
            {...register('inflation_linked')}
            style={{ width: 16, height: 16, cursor: 'pointer', accentColor: '#0e9aad' }}
          />
          <label
            htmlFor="inflation_linked"
            style={{ ...labelStyle, marginBottom: 0, cursor: 'pointer', textTransform: 'none', letterSpacing: 0, fontSize: 13, color: '#e8edf2' }}
          >
            Inflation-linked
          </label>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
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
