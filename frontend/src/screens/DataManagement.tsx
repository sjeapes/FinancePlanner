/**
 * DataManagement.tsx
 * Tabbed data management screen for editing all financial data via the API.
 * Tabs: People, Income, Savings, Investments, Pensions, Property & Mortgage,
 *       Expenses, Life Events.
 */

import type { CSSProperties, ReactNode } from 'react'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAllAccounts,
  useAddAccount,
  useUpdateAccount,
  useDeleteAccount,
  ACCOUNTS_QUERY_KEY,
} from '../api/hooks/useAccounts'
import { PersonForm } from '../components/forms/PersonForm'
import { IncomeForm } from '../components/forms/IncomeForm'
import { SavingsForm } from '../components/forms/SavingsForm'
import { InvestmentForm } from '../components/forms/InvestmentForm'
import { PensionForm } from '../components/forms/PensionForm'
import { PropertyForm } from '../components/forms/PropertyForm'
import { MortgageForm } from '../components/forms/MortgageForm'
import { ExpenseForm } from '../components/forms/ExpenseForm'
import { LifeEventForm } from '../components/forms/LifeEventForm'

// ── Types ───────────────────────────────────────────────────────────────────

type TabKey =
  | 'people'
  | 'income'
  | 'savings'
  | 'investments'
  | 'pensions'
  | 'property'
  | 'expenses'
  | 'life_events'
  | 'import'
  | 'backup'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'people', label: 'People' },
  { key: 'income', label: 'Income' },
  { key: 'savings', label: 'Savings' },
  { key: 'investments', label: 'Investments' },
  { key: 'pensions', label: 'Pensions' },
  { key: 'property', label: 'Property & Mortgage' },
  { key: 'expenses', label: 'Expenses' },
  { key: 'life_events', label: 'Life Events' },
  { key: 'import', label: '↑ Import' },
  { key: 'backup', label: '⇄ Backup' },
]

// ── Shared styles ────────────────────────────────────────────────────────────

const labelStyle: CSSProperties = {
  color: '#8fa3b8',
  fontSize: 11,
  fontWeight: 500,
}

const inputStyle: CSSProperties = {
  background: '#0f1b2d',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 6,
  color: '#e8edf2',
  fontSize: 12,
  padding: '6px 10px',
  width: '100%',
  outline: 'none',
}

const cardStyle: CSSProperties = {
  background: '#162236',
  border: '1px solid rgba(255,255,255,0.07)',
  borderRadius: 10,
  padding: '12px 16px',
  marginBottom: 8,
}

const cardNameStyle: CSSProperties = {
  color: '#e8edf2',
  fontWeight: 600,
  fontSize: 14,
  marginBottom: 4,
}

const cardMetaStyle: CSSProperties = {
  color: '#8fa3b8',
  fontSize: 12,
  fontFamily: 'DM Sans, sans-serif',
}

const monoStyle: CSSProperties = {
  fontFamily: 'DM Mono, monospace',
}

const btnSmall: CSSProperties = {
  background: 'transparent',
  border: '1px solid rgba(255,255,255,0.15)',
  color: '#8fa3b8',
  borderRadius: 5,
  padding: '3px 10px',
  cursor: 'pointer',
  fontSize: 11,
}

const btnDelete: CSSProperties = {
  background: 'transparent',
  border: '1px solid rgba(224,82,82,0.4)',
  color: '#e05252',
  borderRadius: 5,
  padding: '3px 8px',
  cursor: 'pointer',
  fontSize: 11,
}

const btnAdd: CSSProperties = {
  background: 'rgba(14,154,173,0.15)',
  border: '1px solid rgba(14,154,173,0.4)',
  color: '#0e9aad',
  borderRadius: 6,
  padding: '6px 16px',
  cursor: 'pointer',
  fontSize: 12,
  fontWeight: 500,
  marginBottom: 16,
}

const subHeadStyle: CSSProperties = {
  color: '#8fa3b8',
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.8px',
  marginBottom: 10,
  marginTop: 4,
  borderBottom: '1px solid rgba(255,255,255,0.07)',
  paddingBottom: 6,
}

// ── Toast helper ─────────────────────────────────────────────────────────────

function Toast({ message, isError }: { message: string; isError?: boolean }) {
  return (
    <div
      style={{
        display: 'inline-block',
        background: isError ? 'rgba(224,82,82,0.15)' : 'rgba(45,189,126,0.15)',
        border: `1px solid ${isError ? '#e05252' : '#2dbd7e'}`,
        color: isError ? '#e05252' : '#2dbd7e',
        borderRadius: 6,
        padding: '4px 12px',
        fontSize: 12,
        marginLeft: 12,
      }}
    >
      {message}
    </div>
  )
}

// ── Format helpers ────────────────────────────────────────────────────────────

function fmtMoney(v: number | undefined | null): string {
  if (v === undefined || v === null) return '—'
  return `£${v.toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function fmtPct(v: number | undefined | null): string {
  if (v === undefined || v === null) return '—'
  return `${(v * 100).toFixed(2)}%`
}

// ── Tab content components ────────────────────────────────────────────────────

interface TabSectionProps {
  people: any[]
}

// ─── People Tab ──────────────────────────────────────────────────────────────

function PeopleTab({ people }: TabSectionProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [toastError, setToastError] = useState(false)
  const add    = useAddAccount('person')
  const update = useUpdateAccount('person')
  const del    = useDeleteAccount('person')

  function showToast(msg: string, err = false) {
    setToast(msg)
    setToastError(err)
    setTimeout(() => setToast(null), 2500)
  }

  function handleAdd(data: any) {
    add.mutate(data, {
      onSuccess: () => { setAdding(false); showToast('Person added') },
      onError:   () => showToast('Add failed', true),
    })
  }

  function handleSave(data: any) {
    update.mutate({ id: data.id, data }, {
      onSuccess: () => { setEditingId(null); showToast('Saved') },
      onError:   () => showToast('Save failed', true),
    })
  }

  function handleDelete(id: string, name: string) {
    if (!window.confirm(`Remove ${name} from scenario?`)) return
    del.mutate(id, {
      onSuccess: () => showToast('Removed'),
      onError:   () => showToast('Delete failed', true),
    })
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ color: '#e8edf2', fontSize: 15, fontWeight: 600 }}>People</span>
        {toast && <Toast message={toast} isError={toastError} />}
      </div>

      {adding && (
        <div style={{ ...cardStyle, borderColor: 'rgba(14,154,173,0.3)', marginBottom: 16 }}>
          <PersonForm onSave={handleAdd} onCancel={() => setAdding(false)} />
        </div>
      )}
      {!adding && (
        <button style={btnAdd} onClick={() => setAdding(true)}>+ Add Person</button>
      )}

      {people.map((person: any) => (
        <div key={person.id}>
          {editingId === person.id ? (
            <div style={{ ...cardStyle, borderColor: 'rgba(14,154,173,0.3)' }}>
              <PersonForm person={person} onSave={handleSave} onCancel={() => setEditingId(null)} />
            </div>
          ) : (
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={cardNameStyle}>{person.name}</div>
                  <div style={cardMetaStyle}>
                    <span>DOB: {person.date_of_birth}</span>
                    <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                    <span>Retires: {person.retirement_age}</span>
                    <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                    <span>LE: {person.life_expectancy}</span>
                    {person.state_pension && (
                      <>
                        <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                        <span style={monoStyle}>
                          SP: {fmtMoney(person.state_pension.weekly_amount * 52)}/yr
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button style={btnSmall} onClick={() => { setAdding(false); setEditingId(person.id) }}>Edit</button>
                  <button style={btnDelete} onClick={() => handleDelete(person.id, person.name)}>×</button>
                </div>
              </div>
            </div>
          )}
        </div>
      ))}
      {people.length === 0 && !adding && (
        <div style={{ color: '#8fa3b8', fontSize: 13 }}>No people in scenario. Click "+ Add Person" to start.</div>
      )}
    </div>
  )
}

// ─── Generic CUD tab (Income / Savings / Investments / Pensions / Expenses / Life Events) ──

interface GenericTabProps {
  accountType: string
  items: any[]
  people: any[]
  renderCard: (item: any) => ReactNode
  renderForm: (item: any | null, onSave: (d: any) => void, onCancel: () => void) => ReactNode
  title: string
}

function GenericTab({ accountType, items, people: _people, renderCard, renderForm, title }: GenericTabProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [toastError, setToastError] = useState(false)

  const add = useAddAccount(accountType)
  const update = useUpdateAccount(accountType)
  const del = useDeleteAccount(accountType)

  function showToast(msg: string, err = false) {
    setToast(msg)
    setToastError(err)
    setTimeout(() => setToast(null), 2500)
  }

  function handleAdd(data: any) {
    add.mutate(data, {
      onSuccess: () => { setAdding(false); showToast('Added') },
      onError: () => showToast('Add failed', true),
    })
  }

  function handleUpdate(data: any) {
    update.mutate(
      { id: data.id, data },
      {
        onSuccess: () => { setEditingId(null); showToast('Saved') },
        onError: () => showToast('Save failed', true),
      }
    )
  }

  function handleDelete(id: string) {
    if (!window.confirm(`Delete "${id}"?`)) return
    del.mutate(id, {
      onSuccess: () => showToast('Deleted'),
      onError: () => showToast('Delete failed', true),
    })
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ color: '#e8edf2', fontSize: 15, fontWeight: 600 }}>{title}</span>
        {toast && <Toast message={toast} isError={toastError} />}
      </div>

      {adding && (
        <div style={{ ...cardStyle, borderColor: 'rgba(14,154,173,0.3)', marginBottom: 16 }}>
          {renderForm(null, handleAdd, () => setAdding(false))}
        </div>
      )}

      {!adding && (
        <button style={btnAdd} onClick={() => setAdding(true)}>+ Add</button>
      )}

      {items.map((item: any) => (
        <div key={item.id}>
          {editingId === item.id ? (
            <div style={{ ...cardStyle, borderColor: 'rgba(14,154,173,0.3)' }}>
              {renderForm(item, handleUpdate, () => setEditingId(null))}
            </div>
          ) : (
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  {renderCard(item)}
                </div>
                <div style={{ display: 'flex', gap: 6, marginLeft: 12, flexShrink: 0 }}>
                  <button style={btnSmall} onClick={() => { setAdding(false); setEditingId(item.id) }}>Edit</button>
                  <button style={btnDelete} onClick={() => handleDelete(item.id)}>×</button>
                </div>
              </div>
            </div>
          )}
        </div>
      ))}

      {items.length === 0 && !adding && (
        <div style={{ color: '#8fa3b8', fontSize: 13 }}>No items. Click "+ Add" to create one.</div>
      )}
    </div>
  )
}

// ─── Property & Mortgage Tab ─────────────────────────────────────────────────

function PropertyMortgageTab({ properties, mortgages }: { properties: any[]; mortgages: any[] }) {
  const [editingPropId, setEditingPropId] = useState<string | null>(null)
  const [addingProp, setAddingProp] = useState(false)
  const [editingMortId, setEditingMortId] = useState<string | null>(null)
  const [addingMort, setAddingMort] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [toastError, setToastError] = useState(false)

  const addProp = useAddAccount('property')
  const updateProp = useUpdateAccount('property')
  const delProp = useDeleteAccount('property')
  const addMort = useAddAccount('mortgage')
  const updateMort = useUpdateAccount('mortgage')
  const delMort = useDeleteAccount('mortgage')

  function showToast(msg: string, err = false) {
    setToast(msg)
    setToastError(err)
    setTimeout(() => setToast(null), 2500)
  }

  function handleAddProp(data: any) {
    addProp.mutate(data, {
      onSuccess: () => { setAddingProp(false); showToast('Property added') },
      onError: () => showToast('Add failed', true),
    })
  }

  function handleUpdateProp(data: any) {
    updateProp.mutate({ id: data.id, data }, {
      onSuccess: () => { setEditingPropId(null); showToast('Saved') },
      onError: () => showToast('Save failed', true),
    })
  }

  function handleDelProp(id: string) {
    if (!window.confirm(`Delete property "${id}"?`)) return
    delProp.mutate(id, {
      onSuccess: () => showToast('Deleted'),
      onError: () => showToast('Delete failed', true),
    })
  }

  function handleAddMort(data: any) {
    addMort.mutate(data, {
      onSuccess: () => { setAddingMort(false); showToast('Mortgage added') },
      onError: () => showToast('Add failed', true),
    })
  }

  function handleUpdateMort(data: any) {
    updateMort.mutate({ id: data.id, data }, {
      onSuccess: () => { setEditingMortId(null); showToast('Saved') },
      onError: () => showToast('Save failed', true),
    })
  }

  function handleDelMort(id: string) {
    if (!window.confirm(`Delete mortgage "${id}"?`)) return
    delMort.mutate(id, {
      onSuccess: () => showToast('Deleted'),
      onError: () => showToast('Delete failed', true),
    })
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ color: '#e8edf2', fontSize: 15, fontWeight: 600 }}>Property & Mortgage</span>
        {toast && <Toast message={toast} isError={toastError} />}
      </div>

      {/* Properties */}
      <div style={subHeadStyle}>Properties</div>
      {addingProp && (
        <div style={{ ...cardStyle, borderColor: 'rgba(14,154,173,0.3)', marginBottom: 16 }}>
          <PropertyForm onSave={handleAddProp} onCancel={() => setAddingProp(false)} />
        </div>
      )}
      {!addingProp && (
        <button style={btnAdd} onClick={() => setAddingProp(true)}>+ Add Property</button>
      )}
      {properties.map((prop: any) => (
        <div key={prop.id}>
          {editingPropId === prop.id ? (
            <div style={{ ...cardStyle, borderColor: 'rgba(14,154,173,0.3)' }}>
              <PropertyForm property={prop} onSave={handleUpdateProp} onCancel={() => setEditingPropId(null)} />
            </div>
          ) : (
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={cardNameStyle}>{prop.name}</div>
                  <div style={cardMetaStyle}>
                    <span>{prop.property_type}</span>
                    <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                    <span style={monoStyle}>{fmtMoney(prop.current_value)}</span>
                    {prop.assumed_growth_rate && (
                      <>
                        <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                        <span style={monoStyle}>{fmtPct(prop.assumed_growth_rate)}/yr</span>
                      </>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button style={btnSmall} onClick={() => { setAddingProp(false); setEditingPropId(prop.id) }}>Edit</button>
                  <button style={btnDelete} onClick={() => handleDelProp(prop.id)}>×</button>
                </div>
              </div>
            </div>
          )}
        </div>
      ))}

      {/* Mortgages */}
      <div style={{ ...subHeadStyle, marginTop: 24 }}>Mortgages</div>
      {addingMort && (
        <div style={{ ...cardStyle, borderColor: 'rgba(14,154,173,0.3)', marginBottom: 16 }}>
          <MortgageForm onSave={handleAddMort} onCancel={() => setAddingMort(false)} />
        </div>
      )}
      {!addingMort && (
        <button style={btnAdd} onClick={() => setAddingMort(true)}>+ Add Mortgage</button>
      )}
      {mortgages.map((mort: any) => (
        <div key={mort.id}>
          {editingMortId === mort.id ? (
            <div style={{ ...cardStyle, borderColor: 'rgba(14,154,173,0.3)' }}>
              <MortgageForm mortgage={mort} onSave={handleUpdateMort} onCancel={() => setEditingMortId(null)} />
            </div>
          ) : (
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={cardNameStyle}>{mort.name}</div>
                  <div style={cardMetaStyle}>
                    <span>{mort.mortgage_type}</span>
                    <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                    <span>Balance: </span>
                    <span style={monoStyle}>{fmtMoney(mort.current_balance)}</span>
                    <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                    <span>{mort.term_years} yr term</span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button style={btnSmall} onClick={() => { setAddingMort(false); setEditingMortId(mort.id) }}>Edit</button>
                  <button style={btnDelete} onClick={() => handleDelMort(mort.id)}>×</button>
                </div>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ─── Import Tab ──────────────────────────────────────────────────────────────

interface ParsedResult {
  format: string; institution: string; account_name: string
  suggested_type: string; currency: string; current_balance: number
  statement_date: string
  historical: { date_str: string; balance: number }[]
  holdings: { name: string; isin: string; units: number; price: number; value: number }[]
  confidence: number; warnings: string[]
}

const ACCOUNT_TYPE_OPTIONS = [
  // UK account types
  { value: 'general',              label: '🇬🇧 Current / Bank Account' },
  { value: 'savings',              label: '🇬🇧 Savings Account' },
  { value: 'cash_ISA',             label: '🇬🇧 Cash ISA' },
  { value: 'ISA',                  label: '🇬🇧 Stocks & Shares ISA' },
  { value: 'GIA',                  label: '🇬🇧 General Investment Account (GIA)' },
  { value: 'SIPP',                 label: '🇬🇧 SIPP (Self-Invested Pension)' },
  { value: 'workplace_DC',         label: '🇬🇧 Workplace Pension (DC)' },
  // US account types
  { value: 'k401',                 label: '🇺🇸 401(k)' },
  { value: 'roth_401k',            label: '🇺🇸 Roth 401(k)' },
  { value: 'k403b',                label: '🇺🇸 403(b)' },
  { value: 'roth_ira',             label: '🇺🇸 Roth IRA' },
  { value: 'ira',                  label: '🇺🇸 Traditional IRA' },
  { value: 'hsa',                  label: '🇺🇸 HSA (Health Savings Account)' },
  { value: 'plan_529',             label: '🇺🇸 529 College Savings Plan' },
  { value: 'money_market',         label: '🇺🇸 Money Market Account' },
  { value: 'taxable_brokerage',    label: '🇺🇸 Taxable Brokerage Account' },
]

function DropZone({ onFile }: { onFile: (f: File) => void }) {
  const [drag, setDrag] = useState(false)
  return (
    <label
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        border: `2px dashed ${drag ? '#0e9aad' : 'rgba(255,255,255,0.15)'}`,
        borderRadius: 12, padding: '32px 24px', cursor: 'pointer', marginBottom: 20,
        background: drag ? 'rgba(14,154,173,0.06)' : 'transparent',
        transition: 'all 0.15s',
      }}
      onDragOver={e => { e.preventDefault(); setDrag(true) }}
      onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) onFile(f) }}
    >
      <input type="file" accept=".csv,.ofx,.qfx,.pdf" style={{ display: 'none' }}
             onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f) }} />
      <span style={{ fontSize: 32, marginBottom: 10 }}>📄</span>
      <span style={{ color: '#e8edf2', fontWeight: 600, fontSize: 14 }}>Drop a statement here</span>
      <span style={{ color: '#8fa3b8', fontSize: 12, marginTop: 4 }}>CSV, OFX, QFX or PDF · max 10 MB</span>
    </label>
  )
}

function ConfidenceBadge({ score }: { score: number }) {
  const colour = score >= 0.8 ? '#2dbd7e' : score >= 0.5 ? '#f0a500' : '#e05252'
  const label  = score >= 0.8 ? 'High confidence' : score >= 0.5 ? 'Review data' : 'Low confidence'
  return (
    <span style={{ background: colour + '22', color: colour, border: `1px solid ${colour}44`,
                   borderRadius: 4, padding: '2px 8px', fontSize: 10, fontWeight: 600 }}>{label}</span>
  )
}

// ── Backup / Restore tab ─────────────────────────────────────────────────────

interface BackupListItem { name: string; size_bytes: number; created_at: string }

function apiBase(): string {
  const base = window.location.pathname.replace(/\/+$/, '')
  return `${window.location.protocol}//${window.location.host}${base}/api`
}

function fmtBytes(n: number): string {
  if (n >= 1_048_576) return `${(n / 1_048_576).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${n} B`
}

function BackupTab() {
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [exportedAt, setExportedAt] = useState<string | null>(null)

  const [importFile, setImportFile] = useState<File | null>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<any>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [confirmImport, setConfirmImport] = useState(false)

  const [backups, setBackups] = useState<BackupListItem[]>([])
  const [backupsLoading, setBackupsLoading] = useState(false)

  async function loadBackups() {
    setBackupsLoading(true)
    try {
      const res = await fetch(`${apiBase()}/backup/list`)
      if (res.ok) {
        const data = await res.json()
        setBackups(data.backups ?? [])
      }
    } catch {
      // non-fatal — safety-backup list is informational only
    } finally {
      setBackupsLoading(false)
    }
  }

  async function handleExport() {
    setExporting(true); setExportError(null)
    try {
      const res = await fetch(`${apiBase()}/backup/export`)
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const blob = await res.blob()
      const disposition = res.headers.get('Content-Disposition') ?? ''
      const match = /filename="([^"]+)"/.exec(disposition)
      const filename = match?.[1] ?? `lifeledger_backup_${Date.now()}.zip`

      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = filename
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
      setExportedAt(new Date().toLocaleString())
    } catch (e: any) {
      setExportError(e.message ?? 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  async function handleImport() {
    if (!importFile) return
    setImporting(true); setImportResult(null); setImportError(null)
    const form = new FormData()
    form.append('file', importFile)
    try {
      const res = await fetch(`${apiBase()}/backup/import`, { method: 'POST', body: form })
      const data = await res.json().catch(() => null)
      if (!res.ok) throw new Error(data?.detail ?? `Server error ${res.status}`)
      setImportResult(data)
      setConfirmImport(false)
      setImportFile(null)
      loadBackups()
    } catch (e: any) {
      setImportError(e.message ?? 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div style={{ maxWidth: 700 }}>
      {/* Export */}
      <div style={{ marginBottom: 28 }}>
        <span style={{ color: '#e8edf2', fontSize: 15, fontWeight: 600 }}>Export All Data</span>
        <p style={{ color: '#8fa3b8', fontSize: 12, marginTop: 4, marginBottom: 12 }}>
          Downloads a single ZIP with every scenario, checkpoint, comment, and config file
          (and, per your backup config, the database). Keep it somewhere safe — it can fully
          restore this instance on another device.
        </p>
        <button
          onClick={handleExport}
          disabled={exporting}
          style={{
            background: '#0e9aad', color: '#fff', border: 'none', borderRadius: 6,
            padding: '8px 18px', fontSize: 13, fontWeight: 600,
            cursor: exporting ? 'default' : 'pointer', opacity: exporting ? 0.6 : 1,
          }}
        >
          {exporting ? 'Building export…' : '↓ Export all data'}
        </button>
        {exportedAt && (
          <div style={{ color: '#2dbd7e', fontSize: 12, marginTop: 8 }}>
            ✓ Downloaded at {exportedAt}
          </div>
        )}
        {exportError && (
          <div style={{ color: '#e05252', fontSize: 12, marginTop: 8 }}>⚠ {exportError}</div>
        )}
      </div>

      <div style={{ borderTop: '1px solid rgba(255,255,255,0.07)', margin: '20px 0' }} />

      {/* Import */}
      <div style={{ marginBottom: 28 }}>
        <span style={{ color: '#e8edf2', fontSize: 15, fontWeight: 600 }}>Import / Restore</span>
        <p style={{ color: '#8fa3b8', fontSize: 12, marginTop: 4, marginBottom: 12 }}>
          Restores everything from a previously exported ZIP. A safety backup of your
          <em> current</em> data is always taken automatically before anything is overwritten,
          so this can be undone.
        </p>
        <input
          type="file" accept=".zip"
          onChange={(e) => { setImportFile(e.target.files?.[0] ?? null); setImportResult(null); setImportError(null) }}
          style={{ color: '#8fa3b8', fontSize: 12, marginBottom: 12, display: 'block' }}
        />
        {importFile && !confirmImport && (
          <button
            onClick={() => setConfirmImport(true)}
            style={{ background: '#d4a843', color: '#1a1f2b', border: 'none', borderRadius: 6,
                      padding: '8px 18px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
          >
            Restore "{importFile.name}"…
          </button>
        )}
        {confirmImport && (
          <div style={{ background: '#e0525211', border: '1px solid #e0525244', borderRadius: 8, padding: 14 }}>
            <div style={{ color: '#e05252', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
              This will overwrite your current scenarios, checkpoints, comments, and config
              with the contents of "{importFile?.name}".
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={handleImport}
                disabled={importing}
                style={{ background: '#e05252', color: '#fff', border: 'none', borderRadius: 6,
                          padding: '6px 16px', fontSize: 12, fontWeight: 600,
                          cursor: importing ? 'default' : 'pointer', opacity: importing ? 0.6 : 1 }}
              >
                {importing ? 'Restoring…' : 'Yes, restore now'}
              </button>
              <button
                onClick={() => setConfirmImport(false)}
                disabled={importing}
                style={{ background: 'transparent', color: '#8fa3b8', border: '1px solid #8fa3b855',
                          borderRadius: 6, padding: '6px 16px', fontSize: 12, cursor: 'pointer' }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
        {importResult && (
          <div style={{ color: '#2dbd7e', fontSize: 12, marginTop: 10 }}>
            ✓ {importResult.message}
            {importResult.safety_backup && <> — safety backup saved as <code>{importResult.safety_backup}</code></>}
            {importResult.warnings?.length > 0 && (
              <ul style={{ color: '#d4a843', marginTop: 6, paddingLeft: 18 }}>
                {importResult.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}
              </ul>
            )}
          </div>
        )}
        {importError && (
          <div style={{ color: '#e05252', fontSize: 12, marginTop: 8 }}>⚠ {importError}</div>
        )}
      </div>

      <div style={{ borderTop: '1px solid rgba(255,255,255,0.07)', margin: '20px 0' }} />

      {/* Safety backups list */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <span style={{ color: '#e8edf2', fontSize: 15, fontWeight: 600 }}>Local Safety Backups</span>
          <button onClick={loadBackups} disabled={backupsLoading}
                  style={{ background: 'transparent', color: '#0e9aad', border: 'none', fontSize: 11, cursor: 'pointer' }}>
            {backupsLoading ? 'loading…' : 'refresh'}
          </button>
        </div>
        {backups.length === 0 ? (
          <p style={{ color: '#8fa3b8', fontSize: 12 }}>None yet — created automatically before each import.</p>
        ) : (
          backups.map(b => (
            <div key={b.name} style={{ display: 'flex', justifyContent: 'space-between',
                                        fontSize: 12, color: '#8fa3b8', padding: '4px 0' }}>
              <span>{b.name}</span>
              <span>{fmtBytes(b.size_bytes)} · {new Date(b.created_at).toLocaleString()}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ── Key life dates (retirement / death) ──────────────────────────────────────

/** @brief Client-side mirror of Person.retirement_year()/death_year() for display only. */
function personKeyYears(p: any): { retirementYear: number | null; deathYear: number | null } {
  const dobYear = p?.date_of_birth ? new Date(p.date_of_birth).getFullYear() : null
  if (!dobYear) return { retirementYear: null, deathYear: null }
  return {
    retirementYear: dobYear + (p.retirement_age ?? 65),
    deathYear: dobYear + (p.life_expectancy ?? 90),
  }
}

function KeyLifeDatesPanel({ people }: { people: any[] }) {
  if (people.length === 0) return null
  return (
    <div style={{ background: '#0f1b2d', border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 8, padding: 14, marginBottom: 16 }}>
      <div style={{ color: '#e8edf2', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Key Life Dates</div>
      <p style={{ color: '#8fa3b8', fontSize: 12, marginTop: -6, marginBottom: 10 }}>
        Retirement and end-of-plan dates come from each person's <strong>People</strong> record
        (retirement age / life expectancy). Any life event below can link to these dates instead
        of a fixed one — edit them there and every linked event moves automatically.
      </p>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        {people.map(p => {
          const { retirementYear, deathYear } = personKeyYears(p)
          return (
            <div key={p.id} style={{ display: 'flex', gap: 16 }}>
              <div>
                <div style={labelStyle}>{p.name} — Retirement</div>
                <div style={monoStyle}>{retirementYear ?? '—'}</div>
              </div>
              <div>
                <div style={labelStyle}>{p.name} — Life Expectancy</div>
                <div style={monoStyle}>{deathYear ?? '—'}</div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ImportTab({ people, accounts }: { people: any[]; accounts: any }) {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [parsed, setParsed] = useState<ParsedResult | null>(null)
  const [parseError, setParseError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [applyResult, setApplyResult] = useState<string | null>(null)
  const [applyError, setApplyError] = useState<string | null>(null)

  // User choices
  const [action, setAction] = useState<'create'|'update'>('create')
  const [acctType, setAcctType] = useState('savings')
  const [acctName, setAcctName] = useState('')
  const [acctId, setAcctId] = useState('')
  const [ownerId, setOwnerId] = useState(people[0]?.id ?? '')
  const [importHistory, setImportHistory] = useState(true)
  const [importHoldings, setImportHoldings] = useState(true)

  // All existing accounts for the "update" dropdown
  const allAccounts: any[] = [
    ...(accounts?.savings ?? []),
    ...(accounts?.investment ?? []),
    ...(accounts?.pension ?? []),
    ...(accounts?.property ?? []),
  ]

  async function handleFile(f: File) {
    setFile(f); setParsed(null); setParseError(null); setApplyResult(null); setApplyError(null)
    setLoading(true)
    const form = new FormData()
    form.append('file', f)
    try {
      // Use relative URL — same pattern as apiClient
      const base = window.location.pathname.replace(/\/+$/, '')
      const res  = await fetch(`${window.location.protocol}//${window.location.host}${base}/api/import/parse`, {
        method: 'POST', body: form,
      })
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data: ParsedResult = await res.json()
      setParsed(data)
      setAcctType(data.suggested_type)
      setAcctName(data.account_name)
    } catch (e: any) {
      setParseError(e.message ?? 'Parse failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleApply() {
    if (!parsed) return
    setApplying(true); setApplyResult(null); setApplyError(null)
    try {
      const base = window.location.pathname.replace(/\/+$/, '')
      const res  = await fetch(`${window.location.protocol}//${window.location.host}${base}/api/import/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          parsed, action, account_type: acctType, account_id: acctId,
          account_name: acctName, owner_id: ownerId,
          import_holdings: importHoldings, import_history: importHistory,
        }),
      })
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()
      setApplyResult(data.message)
    } catch (e: any) {
      setApplyError(e.message ?? 'Apply failed')
    } finally {
      setApplying(false)
    }
  }

  const inputS = inputStyle as any

  return (
    <div style={{ maxWidth: 700 }}>
      <div style={{ marginBottom: 20 }}>
        <span style={{ color: '#e8edf2', fontSize: 15, fontWeight: 600 }}>Import Statement</span>
        <p style={{ color: '#8fa3b8', fontSize: 12, marginTop: 4, marginBottom: 0 }}>
          Upload a bank or broker statement to add or update an account automatically.
          Supports CSV, OFX (most UK banks), and PDF.
        </p>
      </div>

      <DropZone onFile={handleFile} />

      {loading && (
        <div style={{ color: '#8fa3b8', padding: 16, textAlign: 'center' }}>
          Parsing {file?.name}…
        </div>
      )}

      {parseError && (
        <div style={{ color: '#e05252', background: '#e0525211', borderRadius: 8,
                      padding: '10px 14px', marginBottom: 16, fontSize: 13 }}>
          ⚠ {parseError}
        </div>
      )}

      {parsed && (
        <>
          {/* Preview card */}
          <div style={{ ...cardStyle, borderColor: 'rgba(14,154,173,0.3)', marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <div>
                <div style={{ color: '#8b949e', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
                  {parsed.format.toUpperCase()} · {parsed.institution || 'Unknown institution'}
                </div>
                <div style={{ color: '#e8edf2', fontWeight: 600, fontSize: 15 }}>{parsed.account_name}</div>
              </div>
              <ConfidenceBadge score={parsed.confidence} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 12 }}>
              <div>
                <div style={{ color: '#8b949e', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Balance</div>
                <div style={{ color: '#e8edf2', fontSize: 18, fontWeight: 700, fontFamily: 'DM Mono, monospace' }}>
                  £{parsed.current_balance.toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div>
                <div style={{ color: '#8b949e', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Statement date</div>
                <div style={{ color: '#e8edf2', fontFamily: 'DM Mono, monospace' }}>{parsed.statement_date}</div>
              </div>
              <div>
                <div style={{ color: '#8b949e', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Data points</div>
                <div style={{ color: '#e8edf2', fontFamily: 'DM Mono, monospace' }}>
                  {parsed.historical.length} months{parsed.holdings.length > 0 ? ` · ${parsed.holdings.length} holdings` : ''}
                </div>
              </div>
            </div>

            {parsed.holdings.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={subHeadStyle}>Holdings detected</div>
                {parsed.holdings.slice(0, 5).map((h, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0',
                                        borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: 12 }}>
                    <span style={{ color: '#e8edf2' }}>{h.name}</span>
                    <span style={{ color: '#8fa3b8', fontFamily: 'DM Mono, monospace' }}>
                      {h.units.toFixed(2)} units · £{h.value.toLocaleString('en-GB')}
                    </span>
                  </div>
                ))}
                {parsed.holdings.length > 5 && (
                  <div style={{ color: '#8b949e', fontSize: 11, marginTop: 4 }}>
                    +{parsed.holdings.length - 5} more holdings
                  </div>
                )}
              </div>
            )}

            {parsed.warnings.length > 0 && parsed.warnings.map((w, i) => (
              <div key={i} style={{ color: '#f0a500', fontSize: 11, marginTop: 6 }}>⚠ {w}</div>
            ))}
          </div>

          {/* User choices */}
          <div style={{ ...cardStyle, marginBottom: 20 }}>
            <div style={subHeadStyle}>Account settings</div>

            {/* Action toggle */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ ...labelStyle, display: 'block', marginBottom: 6 }}>Action</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {(['create', 'update'] as const).map(a => (
                  <button key={a} onClick={() => setAction(a)} style={{
                    padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12,
                    background: action === a ? '#0e9aad' : '#1d2f47',
                    color: action === a ? '#fff' : '#8fa3b8', fontWeight: action === a ? 600 : 400,
                  }}>{a === 'create' ? 'Create new account' : 'Update existing account'}</button>
                ))}
              </div>
            </div>

            {action === 'update' && (
              <div style={{ marginBottom: 14 }}>
                <label style={{ ...labelStyle, display: 'block', marginBottom: 4 }}>Existing account</label>
                <select value={acctId} onChange={e => setAcctId(e.target.value)} style={inputS}>
                  <option value="">— select account —</option>
                  {allAccounts.map((a: any) => (
                    <option key={a.id} value={a.id}>{a.name} (£{a.current_value?.toLocaleString('en-GB') ?? '?'})</option>
                  ))}
                </select>
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
              <div>
                <label style={{ ...labelStyle, display: 'block', marginBottom: 4 }}>Account name</label>
                <input value={acctName} onChange={e => setAcctName(e.target.value)} style={inputS} />
              </div>
              <div>
                <label style={{ ...labelStyle, display: 'block', marginBottom: 4 }}>Account type</label>
                <select value={acctType} onChange={e => setAcctType(e.target.value)} style={inputS}>
                  {ACCOUNT_TYPE_OPTIONS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ ...labelStyle, display: 'block', marginBottom: 4 }}>Owner</label>
                <select value={ownerId} onChange={e => setOwnerId(e.target.value)} style={inputS}>
                  {people.map((p: any) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Options */}
            <div style={{ display: 'flex', gap: 16 }}>
              {parsed.historical.length > 0 && (
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12, color: '#8fa3b8' }}>
                  <input type="checkbox" checked={importHistory} onChange={e => setImportHistory(e.target.checked)} />
                  Import {parsed.historical.length} historical balance points
                </label>
              )}
              {parsed.holdings.length > 0 && (
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12, color: '#8fa3b8' }}>
                  <input type="checkbox" checked={importHoldings} onChange={e => setImportHoldings(e.target.checked)} />
                  Import {parsed.holdings.length} holdings
                </label>
              )}
            </div>
          </div>

          {/* Apply button */}
          <button
            onClick={handleApply}
            disabled={applying || (action === 'update' && !acctId)}
            style={{
              background: '#0e9aad', color: '#fff', border: 'none', borderRadius: 8,
              padding: '10px 28px', fontSize: 14, fontWeight: 600, cursor: applying ? 'not-allowed' : 'pointer',
              opacity: applying || (action === 'update' && !acctId) ? 0.6 : 1,
            }}
          >
            {applying ? 'Applying…' : action === 'create' ? 'Create account from statement' : 'Update account'}
          </button>

          {applyResult && (
            <div style={{ color: '#2dbd7e', background: '#2dbd7e11', borderRadius: 8,
                          padding: '10px 14px', marginTop: 12, fontSize: 13, border: '1px solid #2dbd7e44' }}>
              ✓ {applyResult}
            </div>
          )}
          {applyError && (
            <div style={{ color: '#e05252', background: '#e0525211', borderRadius: 8,
                          padding: '10px 14px', marginTop: 12, fontSize: 13, border: '1px solid #e0525244' }}>
              ✗ {applyError}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────





export function DataManagement() {
  const [activeTab, setActiveTab] = useState<TabKey>('people')
  const queryClient = useQueryClient()
  const { data, isLoading, isError } = useAllAccounts()

  // Invalidate on manual refresh
  function refresh() {
    queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY })
  }

  if (isLoading) {
    return (
      <div style={{ color: '#8fa3b8', padding: 32, textAlign: 'center' }}>
        Loading scenario data…
      </div>
    )
  }

  if (isError) {
    return (
      <div style={{ color: '#e05252', padding: 32, textAlign: 'center' }}>
        Failed to load scenario data. Is the backend running?
        <br />
        <button
          onClick={refresh}
          style={{ marginTop: 12, ...btnSmall, color: '#0e9aad', borderColor: '#0e9aad' }}
        >
          Retry
        </button>
      </div>
    )
  }

  const d = data!
  const people = d.people ?? []

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1
          style={{
            fontFamily: 'Playfair Display, serif',
            color: '#e8edf2',
            fontSize: 24,
            fontWeight: 700,
            margin: 0,
            marginBottom: 4,
          }}
        >
          Data Management
        </h1>
        <p style={{ color: '#8fa3b8', fontSize: 13, margin: 0 }}>
          Edit all financial data for the base scenario.
        </p>
      </div>

      {/* Tab bar */}
      <div
        style={{
          display: 'flex',
          gap: 0,
          borderBottom: '1px solid rgba(255,255,255,0.07)',
          marginBottom: 24,
          overflowX: 'auto',
        }}
      >
        {TABS.map((tab) => {
          const isActive = activeTab === tab.key
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid #0e9aad' : '2px solid transparent',
                color: isActive ? '#0e9aad' : '#8fa3b8',
                padding: '8px 16px',
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: isActive ? 600 : 400,
                whiteSpace: 'nowrap',
                transition: 'color 0.15s',
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.color = '#e8edf2'
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.color = '#8fa3b8'
              }}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'people' && (
          <PeopleTab people={people} />
        )}

        {activeTab === 'income' && (
          <GenericTab
            accountType="income"
            items={d.income ?? []}
            people={people}
            title="Income Sources"
            renderCard={(item) => (
              <>
                <div style={cardNameStyle}>{item.name}</div>
                <div style={cardMetaStyle}>
                  <span style={monoStyle}>{fmtMoney(item.gross_annual)}/yr</span>
                  <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                  <span>{item.tax_treatment}</span>
                  {item.person_id && (
                    <>
                      <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                      <span>{item.person_id}</span>
                    </>
                  )}
                </div>
              </>
            )}
            renderForm={(item, onSave, onCancel) => (
              <IncomeForm income={item ?? undefined} people={people} onSave={onSave} onCancel={onCancel} />
            )}
          />
        )}

        {activeTab === 'savings' && (
          <GenericTab
            accountType="savings"
            items={d.savings ?? []}
            people={people}
            title="Savings Accounts"
            renderCard={(item) => (
              <>
                <div style={cardNameStyle}>{item.name}</div>
                <div style={cardMetaStyle}>
                  <span>{item.account_type}</span>
                  <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                  <span style={monoStyle}>{fmtMoney(item.current_value)}</span>
                  {item.owner_id && (
                    <>
                      <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                      <span>{item.owner_id}</span>
                    </>
                  )}
                </div>
              </>
            )}
            renderForm={(item, onSave, onCancel) => (
              <SavingsForm account={item ?? undefined} people={people} onSave={onSave} onCancel={onCancel} />
            )}
          />
        )}

        {activeTab === 'investments' && (
          <GenericTab
            accountType="investment"
            items={d.investment ?? []}
            people={people}
            title="Investment Accounts"
            renderCard={(item) => (
              <>
                <div style={cardNameStyle}>{item.name}</div>
                <div style={cardMetaStyle}>
                  <span>{item.account_type}</span>
                  <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                  <span style={monoStyle}>{fmtMoney(item.current_value)}</span>
                  {item.assumed_growth_rate !== undefined && (
                    <>
                      <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                      <span style={monoStyle}>{fmtPct(item.assumed_growth_rate)}/yr</span>
                    </>
                  )}
                  {item.holdings?.length > 0 && (
                    <>
                      <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                      <span>{item.holdings.length} holding{item.holdings.length !== 1 ? 's' : ''}</span>
                    </>
                  )}
                </div>
              </>
            )}
            renderForm={(item, onSave, onCancel) => (
              <InvestmentForm account={item ?? undefined} people={people} onSave={onSave} onCancel={onCancel} />
            )}
          />
        )}

        {activeTab === 'pensions' && (
          <GenericTab
            accountType="pension"
            items={d.pension ?? []}
            people={people}
            title="Pension Funds"
            renderCard={(item) => (
              <>
                <div style={cardNameStyle}>{item.name}</div>
                <div style={cardMetaStyle}>
                  <span>{item.pension_type}</span>
                  <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                  {item.owner_id && <span>{item.owner_id}</span>}
                  <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                  <span style={monoStyle}>{fmtMoney(item.current_value)}</span>
                  {item.assumed_growth_rate !== undefined && (
                    <>
                      <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                      <span style={monoStyle}>{fmtPct(item.assumed_growth_rate)}/yr</span>
                    </>
                  )}
                </div>
              </>
            )}
            renderForm={(item, onSave, onCancel) => (
              <PensionForm pension={item ?? undefined} people={people} onSave={onSave} onCancel={onCancel} />
            )}
          />
        )}

        {activeTab === 'property' && (
          <PropertyMortgageTab
            properties={d.property ?? []}
            mortgages={d.mortgages ?? []}
          />
        )}

        {activeTab === 'expenses' && (
          <GenericTab
            accountType="expense"
            items={d.expenses ?? []}
            people={people}
            title="Expense Buckets"
            renderCard={(item) => (
              <>
                <div style={cardNameStyle}>{item.name}</div>
                <div style={cardMetaStyle}>
                  <span style={monoStyle}>{fmtMoney(item.annual_amount)}/yr</span>
                  {item.start_date && (
                    <>
                      <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                      <span>{item.start_date}</span>
                      {item.end_date && <span> → {item.end_date}</span>}
                    </>
                  )}
                  {item.inflation_linked && (
                    <>
                      <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                      <span>inflation-linked</span>
                    </>
                  )}
                </div>
              </>
            )}
            renderForm={(item, onSave, onCancel) => (
              <ExpenseForm expense={item ?? undefined} onSave={onSave} onCancel={onCancel} />
            )}
          />
        )}

        {activeTab === 'life_events' && (
          <>
            <KeyLifeDatesPanel people={people} />
            <GenericTab
              accountType="life_event"
              items={d.life_events ?? []}
              people={people}
              title="Life Events"
            renderCard={(item) => (
              <>
                <div style={cardNameStyle}>{item.name}</div>
                <div style={cardMetaStyle}>
                  <span>{item.event_type}</span>
                  <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                  <span style={monoStyle}>{item.date}</span>
                  {item.date_link && (
                    <>
                      <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                      <span style={{ color: '#0e9aad' }}>
                        🔗 linked to {item.date_link}
                      </span>
                    </>
                  )}
                  <span style={{ margin: '0 8px', opacity: 0.4 }}>|</span>
                  <span style={monoStyle}>{fmtMoney(item.amount)}</span>
                </div>
              </>
            )}
            renderForm={(item, onSave, onCancel) => (
              <LifeEventForm event={item ?? undefined} people={people} onSave={onSave} onCancel={onCancel} />
            )}
            />
          </>
        )}

        {activeTab === 'import' && (
          <ImportTab people={people} accounts={d} />
        )}

        {activeTab === 'backup' && <BackupTab />}
      </div>
    </div>
  )
}
