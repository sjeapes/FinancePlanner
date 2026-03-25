/**
 * PersonForm.tsx
 * Full form for editing a Person + StatePension.
 * Works for both edit mode (person prop provided) and view-only (no add for people).
 */

import type { CSSProperties } from 'react'
import { useForm } from 'react-hook-form'

interface FormValues {
  id: string
  name: string
  date_of_birth: string
  retirement_age: number
  life_expectancy: number
  state_pension_qualifying_years: number
  state_pension_full_qualifying_years: number
  state_pension_expected_start_age: number
  state_pension_weekly_amount: number
  state_pension_deferral_years: number
}

interface Props {
  person?: any
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

export function PersonForm({ person, onSave, onCancel }: Props) {
  const sp = person?.state_pension ?? {}
  const isEditing = !!person

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      id: person?.id ?? '',
      name: person?.name ?? '',
      date_of_birth: person?.date_of_birth ?? '',
      retirement_age: person?.retirement_age ?? 60,
      life_expectancy: person?.life_expectancy ?? 90,
      state_pension_qualifying_years: sp.qualifying_years ?? 0,
      state_pension_full_qualifying_years: sp.full_qualifying_years ?? 35,
      state_pension_expected_start_age: sp.expected_start_age ?? 67,
      state_pension_weekly_amount: sp.weekly_amount ?? 0,
      state_pension_deferral_years: sp.deferral_years ?? 0,
    },
  })

  function onSubmit(values: FormValues) {
    const payload: any = {
      ...person,
      id: values.id,
      name: values.name,
      date_of_birth: values.date_of_birth,
      retirement_age: Number(values.retirement_age),
      life_expectancy: Number(values.life_expectancy),
      state_pension: {
        ...(person?.state_pension ?? {}),
        qualifying_years: Number(values.state_pension_qualifying_years),
        full_qualifying_years: Number(values.state_pension_full_qualifying_years),
        expected_start_age: Number(values.state_pension_expected_start_age),
        weekly_amount: Number(values.state_pension_weekly_amount),
        deferral_years: Number(values.state_pension_deferral_years),
      },
    }
    onSave(payload)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ padding: '16px 0' }}>
      <div style={sectionHeadStyle}>Identity</div>
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
          <label style={labelStyle}>Date of Birth</label>
          <input type="date" {...register('date_of_birth', { required: 'Date of birth is required' })} style={inputStyle} />
          {errors.date_of_birth && <div style={errorStyle}>{errors.date_of_birth.message}</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Retirement Age</label>
          <input
            type="number"
            {...register('retirement_age', { required: true, min: 40, max: 80 })}
            style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
          />
          {errors.retirement_age && <div style={errorStyle}>Must be 40–80</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Life Expectancy</label>
          <input
            type="number"
            {...register('life_expectancy', { required: true, min: 60, max: 120 })}
            style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
          />
          {errors.life_expectancy && <div style={errorStyle}>Must be 60–120</div>}
        </div>
      </div>

      <div style={{ ...sectionHeadStyle, marginTop: 20 }}>State Pension</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={fieldStyle}>
          <label style={labelStyle}>Qualifying Years</label>
          <input
            type="number"
            {...register('state_pension_qualifying_years', { required: true, min: 0, max: 50 })}
            style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
          />
          {errors.state_pension_qualifying_years && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Full Qualifying Years</label>
          <input
            type="number"
            {...register('state_pension_full_qualifying_years', { required: true, min: 1, max: 50 })}
            style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
          />
          {errors.state_pension_full_qualifying_years && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Expected Start Age</label>
          <input
            type="number"
            {...register('state_pension_expected_start_age', { required: true, min: 60, max: 80 })}
            style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
          />
          {errors.state_pension_expected_start_age && <div style={errorStyle}>Must be 60–80</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Weekly Amount</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={1}
              {...register('state_pension_weekly_amount', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.state_pension_weekly_amount && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Deferral Years</label>
          <input
            type="number"
            {...register('state_pension_deferral_years', { required: true, min: 0, max: 10 })}
            style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
          />
          {errors.state_pension_deferral_years && <div style={errorStyle}>Must be 0–10</div>}
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
