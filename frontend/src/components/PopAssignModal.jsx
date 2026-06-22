/**
 * TreasureMap — Modal for manually assigning a device to a POP.
 * Triggered via right-click → "Assign to POP…"
 *
 * Props:
 *   device      { id, label, pop }  — the device being assigned
 *   pops        string[]            — list of known POP labels
 *   onAssign    (deviceName, pop) → Promise  — called on confirm
 *   onClose     ()                  — called to dismiss
 */
import { useState } from 'react'

const OVERLAY = {
  position:       'fixed',
  inset:          0,
  background:     'rgba(0,0,0,0.65)',
  display:        'flex',
  alignItems:     'center',
  justifyContent: 'center',
  zIndex:         10000,
}
const MODAL = {
  background:   '#1e293b',
  border:       '1px solid #334155',
  borderRadius: 12,
  padding:      24,
  minWidth:     360,
  maxWidth:     480,
  color:        '#e2e8f0',
  boxShadow:    '0 24px 64px rgba(0,0,0,0.7)',
}
const TITLE = { fontSize: 16, fontWeight: 700, marginBottom: 4, color: '#f1f5f9' }
const SUB   = { fontSize: 12, color: '#64748b', marginBottom: 20 }
const LABEL = { fontSize: 12, color: '#94a3b8', marginBottom: 6, display: 'block' }
const INPUT = {
  width:        '100%',
  background:   '#0f172a',
  border:       '1px solid #334155',
  borderRadius: 6,
  padding:      '8px 10px',
  color:        '#f1f5f9',
  fontSize:     13,
  outline:      'none',
  boxSizing:    'border-box',
}
const SELECT_STYLE = { ...INPUT, cursor: 'pointer' }
const ROW   = { display: 'flex', gap: 10, marginTop: 20 }
const BTN   = (primary) => ({
  flex:         1,
  padding:      '9px 0',
  borderRadius: 6,
  border:       primary ? 'none' : '1px solid #334155',
  background:   primary ? '#2563eb' : '#1e293b',
  color:        '#f1f5f9',
  cursor:       'pointer',
  fontWeight:   600,
  fontSize:     13,
})

export default function PopAssignModal({ device, pops, onAssign, onClose }) {
  // Start with device's current POP if it has one
  const [selected, setSelected] = useState(device?.pop || '')
  const [custom,   setCustom]   = useState('')
  const [mode,     setMode]     = useState(device?.pop ? 'existing' : 'existing')  // 'existing' | 'new'
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState(null)

  const finalPop = mode === 'new' ? custom.trim().toUpperCase() : selected

  async function handleConfirm() {
    if (!finalPop) return
    setLoading(true)
    setError(null)
    try {
      await onAssign(device.label, finalPop)
      onClose()
    } catch (e) {
      setError(e.message || 'Assignment failed')
      setLoading(false)
    }
  }

  return (
    <div style={OVERLAY} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={MODAL}>
        <div style={TITLE}>📍 Assign to POP</div>
        <div style={SUB}>Device: <strong style={{ color: '#f1f5f9' }}>{device?.label}</strong></div>

        {/* Mode tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          {['existing', 'new'].map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                padding:      '5px 14px',
                borderRadius: 6,
                border:       mode === m ? 'none' : '1px solid #334155',
                background:   mode === m ? '#1d4ed8' : '#0f172a',
                color:        '#f1f5f9',
                cursor:       'pointer',
                fontSize:     12,
                fontWeight:   600,
              }}
            >
              {m === 'existing' ? '📋 Existing POP' : '➕ New POP'}
            </button>
          ))}
        </div>

        {mode === 'existing' ? (
          <>
            <label style={LABEL}>Select POP</label>
            <select
              style={SELECT_STYLE}
              value={selected}
              onChange={e => setSelected(e.target.value)}
            >
              <option value="">— choose a POP —</option>
              {(pops || []).map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </>
        ) : (
          <>
            <label style={LABEL}>
              New POP name
              <span style={{ color: '#64748b', fontWeight: 400, marginLeft: 8 }}>
                e.g. EQX-NYC, DRT-VA, CHI
              </span>
            </label>
            <input
              style={INPUT}
              type="text"
              placeholder="EQX-NYC"
              value={custom}
              onChange={e => setCustom(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleConfirm() }}
              autoFocus
            />
          </>
        )}

        {error && (
          <div style={{ marginTop: 10, color: '#f87171', fontSize: 12 }}>⚠ {error}</div>
        )}

        <div style={ROW}>
          <button style={BTN(false)} onClick={onClose} disabled={loading}>Cancel</button>
          <button
            style={{ ...BTN(true), opacity: (!finalPop || loading) ? 0.5 : 1 }}
            onClick={handleConfirm}
            disabled={!finalPop || loading}
          >
            {loading ? 'Saving…' : 'Assign'}
          </button>
        </div>
      </div>
    </div>
  )
}
