/**
 * LifeEventForm.tsx
 * Full form for a LifeEvent. Supports linking the event's date to a
 * person's retirement or end-of-plan (life expectancy) date instead of
 * typing a fixed date — the link is re-resolved from that person's
 * current retirement_age/life_expectancy every time the scenario loads.
 */

import type { CSSProperties } from 'react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

type DateLink = 'none' | 'retirement' | 'death'

interface FormValues {
  id: string
  name: string
  event_type: string
  date: string
  amount: number
  currency: string
  affects_account_id: string
}

interface Props {
  event?: any
  people?: any[]
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

export function LifeEventForm({ event, people = [], onSave, onCancel }: Props) {
  const isEditing = !!event

  const [dateLink, setDateLink] = useState<DateLink>(
    event?.date_link === 'retirement' || event?.date_link === 'death' ? event.date_link : 'none'
  )
  const [linkPersonId, setLinkPersonId] = useState<string>(
    event?.date_link_person_id ?? people[0]?.id ?? ''
  )

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      id: event?.id ?? '',
      name: event?.name ?? '',
      event_type: event?.event_type ?? 'major_expense',
      date: event?.date ?? '',
      amount: event?.amount ?? 0,
      currency: event?.currency ?? 'GBP',
      affects_account_id: event?.affects_account_id ?? '',
    },
  })

  function onSubmit(values: FormValues) {
    const payload: any = {
      ...event,
      id: values.id,
      name: values.name,
      event_type: values.event_type,
      date: values.date,
      amount: Number(values.amount),
      currency: values.currency,
      affects_account_id: values.affects_account_id || null,
      date_link: dateLink === 'none' ? null : dateLink,
      date_link_person_id: dateLink === 'none' ? null : (linkPersonId || null),
    }
    onSave(payload)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ padding: '16px 0' }}>
      <div style={sectionHeadStyle}>Life Event</div>
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
          <label style={labelStyle}>Event Type</label>
          <select {...register('event_type', { required: true })} style={inputStyle}>
            <option value="major_expense">Major Expense</option>
            <option value="inheritance">Inheritance</option>
            <option value="windfall">Windfall</option>
            <option value="other">Other</option>
          </select>
          {errors.event_type && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Date</label>
          {dateLink === 'none' ? (
            <input type="date" {...register('date', { required: dateLink === 'none' ? 'Date is required' : false })} style={inputStyle} />
          ) : (
            <div style={{ ...inputStyle, color: '#8fa3b8', display: 'flex', alignItems: 'center' }}>
              Tracks {dateLink === 'retirement' ? 'retirement date' : 'end-of-plan date'} — see below
            </div>
          )}
          {errors.date && dateLink === 'none' && <div style={errorStyle}>{errors.date.message}</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Amount</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8fa3b8', fontSize: 13 }}>£</span>
            <input
              type="number"
              step={100}
              {...register('amount', { required: true, min: 0 })}
              style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }}
            />
          </div>
          {errors.amount && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Currency</label>
          <input {...register('currency', { required: true })} style={inputStyle} />
          {errors.currency && <div style={errorStyle}>Required</div>}
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Affects Account ID (optional)</label>
          <input {...register('affects_account_id')} style={inputStyle} placeholder="e.g. vanguard_isa" />
        </div>
      </div>

      <div style={{ ...sectionHeadStyle, marginTop: 20 }}>Date Link</div>
      <p style={{ color: '#8fa3b8', fontSize: 12, marginTop: -6, marginBottom: 10 }}>
        Instead of a fixed date, tie this event to a person's key life date. If their
        retirement age or life expectancy changes later (in the People tab), this event's
        date moves with it automatically.
      </p>
      <div style={{ display: 'flex', gap: 18, marginBottom: 14, flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#e8edf2', cursor: 'pointer' }}>
          <input type="checkbox" checked={dateLink === 'none'}
                 onChange={() => setDateLink('none')} />
          Fixed date
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#e8edf2', cursor: 'pointer' }}>
          <input type="checkbox" checked={dateLink === 'retirement'}
                 onChange={() => setDateLink('retirement')} />
          Link to retirement date
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#e8edf2', cursor: 'pointer' }}>
          <input type="checkbox" checked={dateLink === 'death'}
                 onChange={() => setDateLink('death')} />
          Link to end-of-plan (life expectancy) date
        </label>
      </div>
      {dateLink !== 'none' && (
        <div style={{ ...fieldStyle, maxWidth: 300 }}>
          <label style={labelStyle}>Which person?</label>
          <select value={linkPersonId} onChange={(e) => setLinkPersonId(e.target.value)} style={inputStyle}>
            {people.length === 0 && <option value="">No people found</option>}
            {people.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}

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
