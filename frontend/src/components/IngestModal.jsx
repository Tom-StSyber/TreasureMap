/**
 * TreasureMap — Ingest Configs modal.
 *
 * User specifies a folder path on the server filesystem.
 * The backend scans for running-config files, parses them, and indexes
 * into Elasticsearch, streaming per-file progress via SSE.
 */
import { useState, useRef, useCallback, useEffect } from 'react'

// ─── Styles ──────────────────────────────────────────────────────
const S = {
  overlay: {
    position: 'fixed', inset: 0, zIndex: 1000,
    background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(3px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  modal: {
    background: '#111827', border: '1px solid #1e293b',
    borderRadius: 12, width: 620, maxWidth: '95vw',
    maxHeight: '85vh', display: 'flex', flexDirection: 'column',
    boxShadow: '0 25px 50px rgba(0,0,0,0.6)',
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '16px 20px', borderBottom: '1px solid #1e293b', flexShrink: 0,
  },
  title: { fontSize: 16, fontWeight: 700, color: '#f1f5f9' },
  close: {
    background: 'none', border: 'none', color: '#64748b',
    cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: 4,
  },
  body: { padding: 20, display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto', flex: 1 },
  label: { fontSize: 11, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 4, display: 'block' },
  input: {
    width: '100%', padding: '9px 12px', borderRadius: 6,
    background: '#1e293b', border: '1px solid #334155',
    color: '#e2e8f0', fontSize: 13, outline: 'none', fontFamily: 'monospace',
  },
  hint: { fontSize: 11, color: '#475569', marginTop: 4 },
  checkRow: (checked) => ({
    display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, cursor: 'pointer',
    padding: '8px 10px', borderRadius: 6, transition: 'background 0.15s',
    background: checked ? 'rgba(239,68,68,0.08)' : 'transparent',
    border: checked ? '1px solid rgba(239,68,68,0.35)' : '1px solid transparent',
    color: checked ? '#fca5a5' : '#94a3b8',
  }),
  checkbox: { width: 16, height: 16, accentColor: '#ef4444', cursor: 'pointer', flexShrink: 0 },
  progressWrap: {
    background: '#0f1117', border: '1px solid #1e293b', borderRadius: 6, padding: '12px 14px',
  },
  progressHeader: { display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#94a3b8', marginBottom: 8 },
  progressTrack: { height: 8, background: '#1e293b', borderRadius: 4, overflow: 'hidden' },
  progressFill: (pct, done) => ({
    height: '100%', borderRadius: 4,
    width: `${pct}%`,
    background: done ? '#22c55e' : 'linear-gradient(90deg, #3b82f6, #60a5fa)',
    transition: 'width 0.3s ease, background 0.4s ease',
  }),
  progressPhase: { fontSize: 11, color: '#475569', marginTop: 6 },
  footer: {
    padding: '14px 20px', borderTop: '1px solid #1e293b',
    display: 'flex', gap: 10, alignItems: 'center', flexShrink: 0,
  },
  btnPrimary: {
    padding: '9px 20px', borderRadius: 6, border: 'none', cursor: 'pointer',
    background: '#3b82f6', color: '#fff', fontWeight: 600, fontSize: 13,
  },
  btnSecondary: {
    padding: '9px 16px', borderRadius: 6, cursor: 'pointer',
    background: '#1e293b', border: '1px solid #334155', color: '#94a3b8', fontSize: 13,
  },
  progressBox: {
    background: '#0f1117', border: '1px solid #1e293b', borderRadius: 6,
    padding: 12, maxHeight: 280, overflowY: 'auto', fontFamily: 'monospace',
    fontSize: 12, color: '#94a3b8', lineHeight: 1.6,
  },
  logLine: (status) => ({
    color: status === 'error' ? '#fca5a5'
         : status === 'ok'    ? '#86efac'
         : status === 'info'  ? '#94a3b8'
         : status === 'warn'  ? '#fcd34d'
         : '#e2e8f0',
  }),
  summary: {
    background: '#0f2a1e', border: '1px solid #166534', borderRadius: 6,
    padding: '12px 16px', color: '#86efac',
  },
  summaryGrid: { display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginTop: 8 },
  summaryCard: { background: '#052e16', borderRadius: 4, padding: '8px 10px', textAlign: 'center' },
  summaryNum: { fontSize: 20, fontWeight: 700, color: '#4ade80' },
  summaryLabel: { fontSize: 10, color: '#166534', marginTop: 2 },
  spinner: {
    display: 'inline-block', width: 14, height: 14,
    border: '2px solid #334155', borderTopColor: '#3b82f6',
    borderRadius: '50%', animation: 'spin 0.7s linear infinite',
    marginRight: 8, verticalAlign: 'middle',
  },
}

// ─── Log entry component ──────────────────────────────────────────
function LogEntry({ event }) {
  if (event.type === 'start') {
    return <div style={S.logLine('info')}>▶ Starting ingest from: <span style={{color:'#7dd3fc'}}>{event.folder}</span></div>
  }
  if (event.type === 'scan') {
    return <div style={S.logLine('info')}>🔍 Found <strong style={{color:'#f1f5f9'}}>{event.found}</strong> config file{event.found !== 1 ? 's' : ''}</div>
  }
  if (event.type === 'wipe') {
    return <div style={S.logLine('warn')}>⚠ {event.message}</div>
  }
  if (event.type === 'file') {
    if (event.status === 'error') {
      return <div style={S.logLine('error')}>✗ {event.name} — {event.error}</div>
    }
    return (
      <div style={S.logLine('ok')}>
        ✓ <span style={{color:'#e2e8f0', fontWeight:600}}>{event.hostname || event.name}</span>
        <span style={{color:'#64748b', marginLeft:6}}>{event.vendor} {event.os}</span>
        <span style={{color:'#475569', marginLeft:8}}>
          {event.interfaces}i · {event.acls}a · {event.bgp_peers}b
        </span>
      </div>
    )
  }
  if (event.type === 'link') {
    return <div style={S.logLine('info')}>🔗 Built <strong style={{color:'#f1f5f9'}}>{event.connections}</strong> connection{event.connections !== 1 ? 's' : ''} from BGP peering</div>
  }
  if (event.type === 'error') {
    return <div style={S.logLine('error')}>✗ Error: {event.message}</div>
  }
  return null
}

// ─── Summary card ─────────────────────────────────────────────────
function SummaryCard({ num, label }) {
  return (
    <div style={S.summaryCard}>
      <div style={S.summaryNum}>{num}</div>
      <div style={S.summaryLabel}>{label}</div>
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────
export default function IngestModal({ onClose, onSuccess }) {
  const [folder, setFolder] = useState('')
  const [wipe, setWipe]     = useState(false)
  const [log, setLog]       = useState([])
  const [running, setRunning] = useState(false)
  const [done, setDone]     = useState(false)
  const [summary, setSummary] = useState(null)
  const [total,   setTotal]   = useState(0)
  const [processed, setProcessed] = useState(0)
  const [phase,   setPhase]   = useState('')   // 'scanning' | 'parsing' | 'linking' | 'done'
  const sseRef   = useRef(null)
  const logBoxRef = useRef(null)

  // Auto-scroll log to bottom
  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight
    }
  }, [log])

  // Cleanup SSE on unmount
  useEffect(() => () => sseRef.current?.close(), [])

  const start = useCallback(() => {
    if (!folder.trim()) return
    sseRef.current?.close()
    setRunning(true)
    setDone(false)
    setSummary(null)
    setLog([])
    setTotal(0)
    setProcessed(0)
    setPhase('scanning')

    const url = `/api/ingest/stream?folder_path=${encodeURIComponent(folder.trim())}&wipe=${wipe}`
    const sse = new EventSource(url)
    sseRef.current = sse

    sse.onmessage = (e) => {
      let event
      try { event = JSON.parse(e.data) } catch { return }

      setLog(prev => [...prev, event])

      if (event.type === 'scan') {
        setTotal(event.found)
        setPhase('parsing')
      } else if (event.type === 'file') {
        setProcessed(prev => prev + 1)
      } else if (event.type === 'link') {
        setPhase('linking')
      } else if (event.type === 'done') {
        setPhase('done')
        setSummary(event.summary)
        setDone(true)
        setRunning(false)
        sse.close()
        onSuccess?.()
      } else if (event.type === 'error') {
        setRunning(false)
        sse.close()
      }
    }

    sse.onerror = () => {
      setLog(prev => [...prev, { type: 'error', message: 'Connection to server lost. Is the backend running?' }])
      setRunning(false)
      sse.close()
    }
  }, [folder, wipe, onSuccess])

  const cancel = () => {
    sseRef.current?.close()
    setRunning(false)
    setLog(prev => [...prev, { type: 'error', message: 'Cancelled by user.' }])
  }

  const reset = () => {
    setLog([])
    setDone(false)
    setSummary(null)
    setTotal(0)
    setProcessed(0)
    setPhase('')
  }

  // Inject CSS animation for spinner
  useEffect(() => {
    if (document.getElementById('tm-ingest-style')) return
    const style = document.createElement('style')
    style.id = 'tm-ingest-style'
    style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }'
    document.head.appendChild(style)
  }, [])

  return (
    <div style={S.overlay} onClick={(e) => e.target === e.currentTarget && !running && onClose()}>
      <div style={S.modal}>

        {/* Header */}
        <div style={S.header}>
          <div style={S.title}>⚙ Ingest Network Configs</div>
          <button style={S.close} onClick={onClose} disabled={running}>×</button>
        </div>

        {/* Body */}
        <div style={S.body}>

          {/* Folder input */}
          <div>
            <label style={S.label}>Config folder path</label>
            <input
              style={S.input}
              value={folder}
              onChange={e => setFolder(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !running && start()}
              placeholder="D:\Home-Lab\TreasureMap\data\samples\batfish\tests\roles\networks\example\configs"
              disabled={running}
              spellCheck={false}
            />
            <div style={S.hint}>
              Absolute path on the machine running the backend. Subdirectories are scanned recursively.
              Supported: Cisco IOS / IOS-XE / NX-OS running configs (.cfg .conf .txt).
            </div>
          </div>

          {/* Wipe toggle */}
          <label style={S.checkRow(wipe)}>
            <input
              type="checkbox"
              style={S.checkbox}
              checked={wipe}
              onChange={e => setWipe(e.target.checked)}
              disabled={running}
            />
            <span>
              <strong>⚠ Replace existing data</strong>
              <span style={{ fontWeight: 400, marginLeft: 6 }}>
                — wipes all treasuremap_* indices before ingesting
              </span>
            </span>
          </label>

          {/* Progress bar */}
          {(running || done) && (
            <div style={S.progressWrap}>
              <div style={S.progressHeader}>
                <span>
                  {phase === 'scanning' && '🔍 Scanning folder…'}
                  {phase === 'parsing'  && `Parsing configs — ${processed} / ${total || '?'} files`}
                  {phase === 'linking'  && `Building connections…`}
                  {phase === 'done'     && `✅ Done — ${processed} file${processed !== 1 ? 's' : ''} ingested`}
                </span>
                <span style={{ color: done ? '#4ade80' : '#60a5fa' }}>
                  {done ? '100%' : total ? `${Math.round((processed / total) * 100)}%` : '…'}
                </span>
              </div>
              <div style={S.progressTrack}>
                <div style={S.progressFill(
                  done ? 100 : total ? Math.max(4, Math.round((processed / total) * 100)) : 4,
                  done
                )} />
              </div>
              {phase === 'linking' && (
                <div style={S.progressPhase}>Cross-referencing BGP peers across devices…</div>
              )}
            </div>
          )}

          {/* Progress log */}
          {log.length > 0 && (
            <div>
              <label style={S.label}>
                {running && <span style={S.spinner} />}
                {running ? 'Ingesting…' : done ? 'Complete' : 'Log'}
              </label>
              <div style={S.progressBox} ref={logBoxRef}>
                {log.map((event, i) => <LogEntry key={i} event={event} />)}
              </div>
            </div>
          )}

          {/* Summary */}
          {done && summary && (
            <div style={S.summary}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>
                ✅ Ingest complete
                {summary.errors > 0 && (
                  <span style={{ color: '#fca5a5', marginLeft: 10 }}>
                    ({summary.errors} file{summary.errors !== 1 ? 's' : ''} failed)
                  </span>
                )}
              </div>
              <div style={S.summaryGrid}>
                <SummaryCard num={summary.devices}     label="Devices" />
                <SummaryCard num={summary.interfaces}  label="Interfaces" />
                <SummaryCard num={summary.connections} label="Connections" />
                <SummaryCard num={summary.acls}        label="ACLs" />
              </div>
              <div style={{ fontSize: 11, color: '#166534', marginTop: 8 }}>
                Topology refreshed automatically. Click any device to see details.
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={S.footer}>
          {!running && !done && (
            <button style={S.btnPrimary} onClick={start} disabled={!folder.trim()}>
              ▶ Start Ingest
            </button>
          )}
          {running && (
            <button style={{ ...S.btnPrimary, background: '#dc2626' }} onClick={cancel}>
              ■ Cancel
            </button>
          )}
          {done && (
            <button style={S.btnPrimary} onClick={reset}>
              ↺ Ingest Another
            </button>
          )}
          <button style={S.btnSecondary} onClick={onClose} disabled={running}>
            {done ? 'Close' : 'Cancel'}
          </button>

          {!running && !done && (
            <div style={{ marginLeft: 'auto', fontSize: 11, color: '#475569' }}>
              Legend in log: i=interfaces · a=ACLs · b=BGP peers
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
