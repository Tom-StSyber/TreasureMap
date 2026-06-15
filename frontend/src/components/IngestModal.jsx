/**
 * TreasureMap — Ingest Configs modal.
 *
 * Two modes:
 *   • Upload File  — single-file upload (auto-detects vendor)
 *   • Folder Scan  — server-side folder scan via SSE stream
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
  tabs: {
    display: 'flex', borderBottom: '1px solid #1e293b', flexShrink: 0,
  },
  tab: (active) => ({
    flex: 1, padding: '10px 0', border: 'none', cursor: 'pointer',
    fontSize: 12, fontWeight: 600,
    background: active ? '#111827' : '#0f1117',
    color: active ? '#f1f5f9' : '#64748b',
    borderBottom: active ? '2px solid #3b82f6' : '2px solid transparent',
  }),
  body: { padding: 20, display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto', flex: 1 },
  label: { fontSize: 11, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 4, display: 'block' },
  input: {
    width: '100%', padding: '9px 12px', borderRadius: 6,
    background: '#1e293b', border: '1px solid #334155',
    color: '#e2e8f0', fontSize: 13, outline: 'none', fontFamily: 'monospace',
    boxSizing: 'border-box',
  },
  select: {
    width: '100%', padding: '9px 12px', borderRadius: 6,
    background: '#1e293b', border: '1px solid #334155',
    color: '#e2e8f0', fontSize: 13, outline: 'none',
    boxSizing: 'border-box',
  },
  hint: { fontSize: 11, color: '#475569', marginTop: 4 },
  dropZone: (drag) => ({
    border: `2px dashed ${drag ? '#3b82f6' : '#334155'}`,
    borderRadius: 8, padding: '32px 20px',
    textAlign: 'center', cursor: 'pointer',
    background: drag ? 'rgba(59,130,246,0.06)' : '#0f1117',
    transition: 'all 0.15s',
    color: '#64748b',
  }),
  dropIcon: { fontSize: 32, marginBottom: 8 },
  dropText: { fontSize: 13, color: '#94a3b8', marginBottom: 4 },
  dropHint: { fontSize: 11, color: '#475569' },
  fileChip: {
    display: 'flex', alignItems: 'center', gap: 10,
    background: '#1e293b', border: '1px solid #334155', borderRadius: 6,
    padding: '8px 12px', fontSize: 13,
  },
  fileName: { color: '#e2e8f0', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  fileSize: { color: '#64748b', fontSize: 11, flexShrink: 0 },
  removeBtn: { background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 16, padding: '0 4px', lineHeight: 1 },
  uploadResult: (ok) => ({
    padding: '12px 14px', borderRadius: 6,
    background: ok ? '#052e16' : '#450a0a',
    border: `1px solid ${ok ? '#166534' : '#7f1d1d'}`,
    color: ok ? '#86efac' : '#fca5a5',
    fontSize: 13,
  }),
  uploadGrid: { display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginTop: 10 },
  uploadCard: { background: 'rgba(0,0,0,0.3)', borderRadius: 4, padding: '8px 10px', textAlign: 'center' },
  uploadNum:  { fontSize: 18, fontWeight: 700, color: '#4ade80' },
  uploadLbl:  { fontSize: 10, color: '#166534', marginTop: 2 },
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
    padding: 12, maxHeight: 240, overflowY: 'auto', fontFamily: 'monospace',
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

// ─── Helper components ────────────────────────────────────────────
function LogEntry({ event }) {
  if (event.type === 'start')
    return <div style={S.logLine('info')}>▶ Starting ingest from: <span style={{color:'#7dd3fc'}}>{event.folder}</span></div>
  if (event.type === 'scan')
    return <div style={S.logLine('info')}>🔍 Found <strong style={{color:'#f1f5f9'}}>{event.found}</strong> config file{event.found !== 1 ? 's' : ''}</div>
  if (event.type === 'wipe')
    return <div style={S.logLine('warn')}>⚠ {event.message}</div>
  if (event.type === 'file') {
    if (event.status === 'error')
      return <div style={S.logLine('error')}>✗ {event.name} — {event.error}</div>
    return (
      <div style={S.logLine('ok')}>
        ✓ <span style={{color:'#e2e8f0', fontWeight:600}}>{event.hostname || event.name}</span>
        <span style={{color:'#64748b', marginLeft:6}}>{event.vendor} {event.os}</span>
        <span style={{color:'#475569', marginLeft:8}}>{event.interfaces}i · {event.acls}a · {event.bgp_peers}b</span>
      </div>
    )
  }
  if (event.type === 'link')
    return <div style={S.logLine('info')}>🔗 Built <strong style={{color:'#f1f5f9'}}>{event.connections}</strong> connection{event.connections !== 1 ? 's' : ''} from BGP peering</div>
  if (event.type === 'error')
    return <div style={S.logLine('error')}>✗ Error: {event.message}</div>
  return null
}

function SummaryCard({ num, label }) {
  return (
    <div style={S.summaryCard}>
      <div style={S.summaryNum}>{num}</div>
      <div style={S.summaryLabel}>{label}</div>
    </div>
  )
}

function fmtBytes(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

// ─── Upload File tab ──────────────────────────────────────────────
function UploadTab({ onSuccess }) {
  const [file, setFile]         = useState(null)
  const [vendor, setVendor]     = useState('')
  const [drag, setDrag]         = useState(false)
  const [uploading, setUploading] = useState(false)
  const [result, setResult]     = useState(null) // { ok, data } | null
  const fileInputRef            = useRef(null)

  function pickFile(f) {
    if (!f) return
    setFile(f)
    setResult(null)
  }

  function handleDrop(e) {
    e.preventDefault()
    setDrag(false)
    const f = e.dataTransfer.files[0]
    if (f) pickFile(f)
  }

  async function upload() {
    if (!file) return
    setUploading(true)
    setResult(null)
    const fd = new FormData()
    fd.append('file', file)
    if (vendor) fd.append('vendor', vendor)
    try {
      const res = await fetch('/api/ingest/upload', { method: 'POST', body: fd })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
      setResult({ ok: true, data })
      onSuccess?.()
    } catch (err) {
      setResult({ ok: false, error: err.message })
    } finally {
      setUploading(false)
    }
  }

  function reset() {
    setFile(null)
    setResult(null)
    setVendor('')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Drop zone */}
      {!file ? (
        <div
          style={S.dropZone(drag)}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={handleDrop}
        >
          <div style={S.dropIcon}>📄</div>
          <div style={S.dropText}>Drop a config file here, or click to browse</div>
          <div style={S.dropHint}>Cisco IOS · JunOS · Huawei VRP · Dell OS10 · HPE Aruba OS-CX</div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.cfg,.conf,.log"
            style={{ display: 'none' }}
            onChange={e => pickFile(e.target.files[0])}
          />
        </div>
      ) : (
        <div style={S.fileChip}>
          <span style={{ fontSize: 20 }}>📄</span>
          <span style={S.fileName}>{file.name}</span>
          <span style={S.fileSize}>{fmtBytes(file.size)}</span>
          {!uploading && !result?.ok && (
            <button style={S.removeBtn} onClick={reset} title="Remove">×</button>
          )}
        </div>
      )}

      {/* Vendor hint */}
      {file && !result?.ok && (
        <div>
          <label style={S.label}>Vendor hint (optional — auto-detected if blank)</label>
          <select
            style={S.select}
            value={vendor}
            onChange={e => setVendor(e.target.value)}
            disabled={uploading}
          >
            <option value="">Auto-detect</option>
            <option value="cisco">Cisco IOS / IOS-XE / NX-OS</option>
            <option value="junos">JunOS (hierarchical or set-format)</option>
            <option value="huawei">Huawei VRP</option>
            <option value="dell">Dell OS10 (PowerSwitch)</option>
            <option value="hpe">HPE Aruba OS-CX</option>
          </select>
        </div>
      )}

      {/* Upload button */}
      {file && !result?.ok && (
        <button
          style={{ ...S.btnPrimary, alignSelf: 'flex-start', opacity: uploading ? 0.6 : 1 }}
          onClick={upload}
          disabled={uploading}
        >
          {uploading ? <><span style={S.spinner} />Uploading…</> : '⬆ Upload & Parse'}
        </button>
      )}

      {/* Result */}
      {result && (
        <div style={S.uploadResult(result.ok)}>
          {result.ok ? (
            <>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>
                ✅ Indexed: <span style={{ color: '#f1f5f9' }}>{result.data.hostname}</span>
                {result.data.pop && (
                  <span style={{ color: '#93c5fd', marginLeft: 8, fontSize: 12 }}>POP: {result.data.pop}</span>
                )}
                {result.data.role && (
                  <span style={{ color: '#a5b4fc', marginLeft: 6, fontSize: 12 }}>({result.data.role})</span>
                )}
              </div>
              <div style={{ fontSize: 12, color: '#475569', marginBottom: 6 }}>
                {result.data.vendor} · {result.data.os}
              </div>
              <div style={S.uploadGrid}>
                {[
                  [result.data.interfaces,  'Interfaces'],
                  [result.data.acls,        'ACLs'],
                  [result.data.bgp_peers,   'BGP Peers'],
                  [result.data.connections, 'Connections'],
                ].map(([n, l]) => (
                  <div key={l} style={S.uploadCard}>
                    <div style={S.uploadNum}>{n ?? 0}</div>
                    <div style={S.uploadLbl}>{l}</div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 11, color: '#166534', marginTop: 8 }}>
                Click ⟳ Refresh to update the topology graph.
              </div>
            </>
          ) : (
            <div>✗ {result.error}</div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Folder Scan tab ──────────────────────────────────────────────
function FolderTab({ onSuccess }) {
  const [folder, setFolder] = useState('')
  const [wipe, setWipe]     = useState(false)
  const [log, setLog]       = useState([])
  const [running, setRunning] = useState(false)
  const [done, setDone]     = useState(false)
  const [summary, setSummary] = useState(null)
  const [total,   setTotal]   = useState(0)
  const [processed, setProcessed] = useState(0)
  const [phase,   setPhase]   = useState('')
  const sseRef    = useRef(null)
  const logBoxRef = useRef(null)

  useEffect(() => {
    if (logBoxRef.current) logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight
  }, [log])

  useEffect(() => () => sseRef.current?.close(), [])

  const start = useCallback(() => {
    if (!folder.trim()) return
    sseRef.current?.close()
    setRunning(true); setDone(false); setSummary(null); setLog([])
    setTotal(0); setProcessed(0); setPhase('scanning')

    const url = `/api/ingest/stream?folder_path=${encodeURIComponent(folder.trim())}&wipe=${wipe}`
    const sse = new EventSource(url)
    sseRef.current = sse

    sse.onmessage = (e) => {
      let event
      try { event = JSON.parse(e.data) } catch { return }
      setLog(prev => [...prev, event])
      if (event.type === 'scan')  { setTotal(event.found); setPhase('parsing') }
      else if (event.type === 'file') setProcessed(prev => prev + 1)
      else if (event.type === 'link') setPhase('linking')
      else if (event.type === 'done') {
        setPhase('done'); setSummary(event.summary)
        setDone(true); setRunning(false); sse.close(); onSuccess?.()
      } else if (event.type === 'error') { setRunning(false); sse.close() }
    }
    sse.onerror = () => {
      setLog(prev => [...prev, { type: 'error', message: 'Connection lost. Is the backend running?' }])
      setRunning(false); sse.close()
    }
  }, [folder, wipe, onSuccess])

  const cancel = () => { sseRef.current?.close(); setRunning(false); setLog(prev => [...prev, { type: 'error', message: 'Cancelled.' }]) }
  const reset  = () => { setLog([]); setDone(false); setSummary(null); setTotal(0); setProcessed(0); setPhase('') }

  return (
    <>
      <div>
        <label style={S.label}>Config folder path</label>
        <input
          style={S.input}
          value={folder}
          onChange={e => setFolder(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !running && start()}
          placeholder="/app/data  or  /external-data/configs/lab"
          disabled={running}
          spellCheck={false}
        />
        <div style={S.hint}>
          Path on the backend server (Docker container). Use <code style={{color:'#7dd3fc'}}>/app/data</code> for
          files in <code style={{color:'#7dd3fc'}}>backend/data/</code>.
          Scans recursively for .cfg .conf .txt files.
          Supports: Cisco IOS · JunOS · Huawei VRP · Dell OS10 · HPE Aruba OS-CX.
        </div>
      </div>

      <label style={S.checkRow(wipe)}>
        <input type="checkbox" style={S.checkbox} checked={wipe} onChange={e => setWipe(e.target.checked)} disabled={running} />
        <span>
          <strong>⚠ Replace existing data</strong>
          <span style={{ fontWeight: 400, marginLeft: 6 }}>— wipes all treasuremap_* indices before ingesting</span>
        </span>
      </label>

      {(running || done) && (
        <div style={S.progressWrap}>
          <div style={S.progressHeader}>
            <span>
              {phase === 'scanning' && '🔍 Scanning…'}
              {phase === 'parsing'  && `Parsing — ${processed} / ${total || '?'} files`}
              {phase === 'linking'  && 'Building connections…'}
              {phase === 'done'     && `✅ Done — ${processed} file${processed !== 1 ? 's' : ''} ingested`}
            </span>
            <span style={{ color: done ? '#4ade80' : '#60a5fa' }}>
              {done ? '100%' : total ? `${Math.round((processed / total) * 100)}%` : '…'}
            </span>
          </div>
          <div style={S.progressTrack}>
            <div style={S.progressFill(done ? 100 : total ? Math.max(4, Math.round((processed / total) * 100)) : 4, done)} />
          </div>
          {phase === 'linking' && <div style={S.progressPhase}>Cross-referencing BGP peers…</div>}
        </div>
      )}

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

      {done && summary && (
        <div style={S.summary}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>
            ✅ Ingest complete
            {summary.errors > 0 && <span style={{ color: '#fca5a5', marginLeft: 10 }}>({summary.errors} failed)</span>}
          </div>
          <div style={S.summaryGrid}>
            <SummaryCard num={summary.devices}     label="Devices" />
            <SummaryCard num={summary.interfaces}  label="Interfaces" />
            <SummaryCard num={summary.connections} label="Connections" />
            <SummaryCard num={summary.acls}        label="ACLs" />
          </div>
        </div>
      )}

      {/* Footer buttons — inline so they share running state */}
      <div style={{ display: 'flex', gap: 10, paddingTop: 4 }}>
        {!running && !done && (
          <button style={S.btnPrimary} onClick={start} disabled={!folder.trim()}>▶ Start Ingest</button>
        )}
        {running && (
          <button style={{ ...S.btnPrimary, background: '#dc2626' }} onClick={cancel}>■ Cancel</button>
        )}
        {done && (
          <button style={S.btnPrimary} onClick={reset}>↺ Ingest Another</button>
        )}
        {!running && !done && (
          <div style={{ marginLeft: 'auto', fontSize: 11, color: '#475569', alignSelf: 'center' }}>
            i=interfaces · a=ACLs · b=BGP peers
          </div>
        )}
      </div>
    </>
  )
}

// ─── Main component ───────────────────────────────────────────────
export default function IngestModal({ onClose, onSuccess }) {
  const [tab, setTab] = useState('upload') // 'upload' | 'folder'

  useEffect(() => {
    if (document.getElementById('tm-ingest-style')) return
    const style = document.createElement('style')
    style.id = 'tm-ingest-style'
    style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }'
    document.head.appendChild(style)
  }, [])

  return (
    <div style={S.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={S.modal}>

        <div style={S.header}>
          <div style={S.title}>⚙ Ingest Network Configs</div>
          <button style={S.close} onClick={onClose}>×</button>
        </div>

        <div style={S.tabs}>
          <button style={S.tab(tab === 'upload')} onClick={() => setTab('upload')}>📄 Upload File</button>
          <button style={S.tab(tab === 'folder')} onClick={() => setTab('folder')}>📁 Folder Scan</button>
        </div>

        <div style={S.body}>
          {tab === 'upload'
            ? <UploadTab onSuccess={onSuccess} />
            : <FolderTab onSuccess={onSuccess} />
          }
        </div>

        <div style={S.footer}>
          <button style={S.btnSecondary} onClick={onClose}>Close</button>
        </div>

      </div>
    </div>
  )
}
