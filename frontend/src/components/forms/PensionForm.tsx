/**
 * PensionForm.tsx
 * Full form for a PensionFund including drawdown configuration.
 */

import type { CSSProperties } from 'react'
import { useForm } from 'react-hook-form'

interface FormValues {
  id: string
  name: string
  pension_type: string
  owner_id: string
  current_value: number
  assumed_growth_rate: number
  drawdown_mode: string
  drawdown_rate: number
  drawdown_start_date: string
  drawdown_tax_free_lump_sum_pct: number
}

interface Props {
  pension?: any
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

export function PensionForm({ pension, people, onSave, onCancel }: Props) {
  const isEditing = !!pension
  const dc = pension?.drawdown_config ?? {}

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      id: pension?.id ?? '',
      name: pension?.name ?? '',
      pension_type: pension?.pension_type ?? 'SIPP',
      owner_id: pension?.owner_id ?? '',
      current_value: pension?.current_value ?? 0,
      assumed_growth_rate:
        pension?.assumed_growth_rate !== undefined
          ? parseFloat((pension.assumed_growth_rate * 100).toPrecision(6))
          : 7,
      drawdown_mode: dc.mode ?? 'pct_swr',
      drawdown_rate:
        dc.rate !== undefined ? parseFloat((dc.rate * 100).toPrecision(6)) : 4,
      drawdown_start_date: dc.start_date ?? '',
      drawdown_tax_free_lump_sum_pct:
        dc.tax_free_lump_sum_pct !== undefined
          ? parseFloat((dc.tax_free_lump_sum_pct * 100).toPrecision(6))
          : 25,
    },
  })

  function onSubmit(values: FormValues) {
    const payload: any = {
      ...pension,
      id: values.id,
      name: values.name,
      pension_type: values.pension_type,
      owner_id: values.owner_id,
      current_value: Number(values.current_value),
      assumed_growth_rate: Number(values.assumed_growth_rate) / 100,
      drawdown_config: {
        ...(pension?.drawdown_config ?? {}),
        mode: values.drawdown_mode,
        rate: Number(values.drawdown_rate) / 100,
        start_date: values.drawdown_start_date,
        tax_free_lump_sum_pct: Number(values.drawdown_tax_free_lump_sum_pct) / 100,
      },
    }
    onSave(payload)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ padding: '16px 0' }}>
      <div style={sectionHeadStyle}>Pension Fund</div>
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
          <label style={labelStyle}>Pension Type</label>
          <select {...register('pension_type', { required: true })} style={inputStyle}>
            <option value="SIPP">SIPP</option>
            <option value="workplace_DC">Workplace DC</option>
            <option value="DB">DB</option>
          </select>
          {errors.pension_type && <div style={errorStyle}>Required</div>}
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

      <div style={{ ...sectionHeadStyle, marginTop: 20 }}>Drawdown Configuration</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={fieldStyle}>
          <label style={labelStyle}>Drawdown Mode</label>
          <select {...register('drawdown_mode', { required: true })} style={inputStyle}>
            <option value="pct_swr">% Safe Withdrawal Rate</option>
            <option value="fixed_amount">Fixed Amount</option>
            <option value="annuity">Annuity</option>
          </select>
          {errors.drawdown_mode && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Rate</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="number"
              step={0.001}
              {...register('drawdown_rate', { required: true, min: 0, max: 100 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>%</span>
          </div>
          {errors.drawdown_rate && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Start Date</label>
          <input type="date" {...register('drawdown_start_date', { required: 'Start date is required' })} style={inputStyle} />
          {errors.drawdown_start_date && <div style={errorStyle}>{errors.drawdown_start_date.message}</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Tax-Free Lump Sum %</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="number"
              step={0.1}
              {...register('drawdown_tax_free_lump_sum_pct', { required: true, min: 0, max: 100 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>%</span>
          </div>
          {errors.drawdown_tax_free_lump_sum_pct && <div style={errorStyle}>Required</div>}
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
