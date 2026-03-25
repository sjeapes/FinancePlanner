/**
 * PropertyForm.tsx
 * Full form for a PropertyAsset.
 */

import type { CSSProperties } from 'react'
import { useForm } from 'react-hook-form'

interface FormValues {
  id: string
  name: string
  property_type: string
  current_value: number
  currency: string
  assumed_growth_rate: number
  rental_income_annual: number
  purchase_date: string
  purchase_price: number
  mortgage_id: string
}

interface Props {
  property?: any
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

export function PropertyForm({ property, onSave, onCancel }: Props) {
  const isEditing = !!property

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      id: property?.id ?? '',
      name: property?.name ?? '',
      property_type: property?.property_type ?? 'residential',
      current_value: property?.current_value ?? 0,
      currency: property?.currency ?? 'GBP',
      assumed_growth_rate:
        property?.assumed_growth_rate !== undefined
          ? parseFloat((property.assumed_growth_rate * 100).toPrecision(6))
          : 3.5,
      rental_income_annual: property?.rental_income_annual ?? 0,
      purchase_date: property?.purchase_date ?? '',
      purchase_price: property?.purchase_price ?? 0,
      mortgage_id: property?.mortgage_id ?? '',
    },
  })

  function onSubmit(values: FormValues) {
    const payload: any = {
      ...property,
      id: values.id,
      name: values.name,
      property_type: values.property_type,
      current_value: Number(values.current_value),
      currency: values.currency,
      assumed_growth_rate: Number(values.assumed_growth_rate) / 100,
      rental_income_annual: Number(values.rental_income_annual),
      purchase_date: values.purchase_date,
      purchase_price: Number(values.purchase_price),
      mortgage_id: values.mortgage_id || null,
    }
    onSave(payload)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ padding: '16px 0' }}>
      <div style={sectionHeadStyle}>Property Asset</div>
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
          <label style={labelStyle}>Property Type</label>
          <select {...register('property_type', { required: true })} style={inputStyle}>
            <option value="residential">Residential</option>
            <option value="commercial">Commercial</option>
            <option value="rental">Rental</option>
          </select>
          {errors.property_type && <div style={errorStyle}>Required</div>}
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
        <div style={fieldStyle}>
          <label style={labelStyle}>Rental Income (Annual)</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={100}
              {...register('rental_income_annual', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.rental_income_annual && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Purchase Date</label>
          <input type="date" {...register('purchase_date', { required: 'Purchase date is required' })} style={inputStyle} />
          {errors.purchase_date && <div style={errorStyle}>{errors.purchase_date.message}</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Purchase Price</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={100}
              {...register('purchase_price', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.purchase_price && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Mortgage ID (optional)</label>
          <input {...register('mortgage_id')} style={inputStyle} placeholder="e.g. london_mortgage" />
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
