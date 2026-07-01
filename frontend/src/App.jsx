/**
 * TreasureMap — Root application shell.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────┐
 *   │  Header (title + legend + ingest button + refresh)  │
 *   ├─────────────┬───────────────────────┬───────────────┤
 *   │ Left panel  │   Cytoscape graph     │  Right panel  │
 *   │ (tab-based) │   (fills remaining)   │  (detail /    │
 *   │  - Textual  │                       │   path result)│
 *   │  - PathFind │                       │               │
 *   └─────────────┴───────────────────────┴───────────────┘
 *
 * New in this version:
 *   • Right-click context menu on nodes (path query / assign POP)
 *   • POP compound nodes + colour-coded boxes in the graph
 *   • Config file ingest panel (upload Juniper/Huawei/Cisco configs)
 *   • Legend updated with gateway ♦ and OOB markers
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import TopologyGraph  from './components/TopologyGraph.jsx'
import TextualView    from './components/TextualView.jsx'
import PathSearch     from './components/PathSearch.jsx'
import DeviceDetails  from './components/DeviceDetails.jsx'
import PopAssignModal from './components/PopAssignModal.jsx'
import { api }        from './api/client.js'

// ─── Layout constants ─────────────────────────────────────────────
const LEFT_W  = 340
const RIGHT_W = 320

const S = {
  root: { display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw',
          overflow: 'hidden', background: '#0f1117' },
  header: {
    display: 'flex', alignItems: 'center', gap: 16,
    padding: '0 16px', height: 50, flexShrink: 0,
    background: '#111827', borderBottom: '1px solid #1e293b',
  },
  logo:    { fontSize: 18, fontWeight: 800, color: '#f1f5f9', letterSpacing: -0.5 },
  logoSub: { fontSize: 12, color: '#64748b', marginLeft: 6 },
  legend:  { display: 'flex', gap: 14, marginLeft: 'auto', alignItems: 'center',
              fontSize: 12, color: '#94a3b8' },
  legendItem: { display: 'flex', alignItems: 'center', gap: 5 },
  body:    { display: 'flex', flex: 1, overflow: 'hidden' },
  leftPanel: {
    width: LEFT_W, flexShrink: 0, borderRight: '1px solid #1e293b',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  leftTabs: { display: 'flex', borderBottom: '1px solid #1e293b', flexShrink: 0 },
  leftTab: (active) => ({
    flex: 1, padding: '10px 0', border: 'none', cursor: 'pointer',
    fontSize: 12, fontWeight: 600,
    background: active ? '#0f1117' : '#111827',
    color: active ? '#f1f5f9' : '#64748b',
    borderBottom: active ? '2px solid #3b82f6' : '2px solid transparent',
  }),
  graphArea: { flex: 1, position: 'relative', overflow: 'hidden' },
  rightPanel: {
    width: RIGHT_W, flexShrink: 0, borderLeft: '1px solid #1e293b',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  statusBar: {
    height: 26, padding: '0 16px', display: 'flex', alignItems: 'center', gap: 12,
    background: '#111827', borderTop: '1px solid #1e293b', flexShrink: 0,
    fontSize: 11, color: '#64748b',
  },
  refreshBtn: {
    padding: '4px 12px', borderRadius: 6, border: '1px solid #334155',
    background: '#1e293b', color: '#94a3b8', cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  ingestBtn: {
    padding: '4px 12px', borderRadius: 6, border: '1px solid #1d4ed8',
    background: '#1e3a5f', color: '#93c5fd', cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  dot: (c) => ({ width: 8, height: 8, borderRadius: '50%', background: c, display: 'inline-block' }),
}

// ─── Legend helpers ───────────────────────────────────────────────
function LegendLine({ color, dashed, thick }) {
  if (thick)   return <div style={{ width: 28, height: 4, background: color, borderRadius: 2 }} />
  if (dashed)  return <div style={{ width: 24, height: 0, borderTop: `2px dashed ${color}` }} />
  return <div style={{ width: 24, height: 2, background: color, borderRadius: 1 }} />
}
function LegendIcon({ shape }) {
  if (shape === 'diamond')
    return <span style={{ color: '#f59e0b', fontSize: 14, lineHeight: 1 }}>◆</span>
  if (shape === 'oob')
    return <span style={{ color: '#d946ef', fontSize: 14, lineHeight: 1 }}>⊞</span>
  return null
}
function LegendItem({ color, label, dashed, thick, shape }) {
  return (
    <div style={S.legendItem}>
      {shape ? <LegendIcon shape={shape} /> : <LegendLine color={color} dashed={dashed} thick={thick} />}
      <span>{label}</span>
    </div>
  )
}

// ─── Ingest panel ─────────────────────────────────────────────────
function IngestPanel({ onIngested, onClose }) {
  const [mode,     setMode]     = useState('single')   // 'single' | 'bulk'
  // Single-file mode
  const [file,     setFile]     = useState(null)
  const [hostname, setHostname] = useState('')
  const [vendor,   setVendor]   = useState('auto')
  const [status,   setStatus]   = useState(null)   // null | 'loading' | {ok} | {error}
  // Bulk mode
  const [bulkFiles,    setBulkFiles]    = useState([])   // File[]
  const [bulkProgress, setBulkProgress] = useState(null) // null | {done,total,results:[]}
  const fileRef = useRef()
  const folderRef = useRef()

  // ── Single file upload ──────────────────────────────────────────
  async function handleUpload() {
    if (!file) return
    setStatus('loading')
    const form = new FormData()
    form.append('file', file)
    form.append('hostname', hostname || 'unknown')
    form.append('vendor', vendor)
    try {
      const res = await fetch('/api/ingest/config', { method: 'POST', body: form })
      const json = await res.json()
      if (!res.ok) throw new Error(json.detail || res.statusText)
      setStatus({ ok: true, data: json })
      onIngested?.()
    } catch (e) {
      setStatus({ ok: false, error: e.message })
    }
  }

  // ── Bulk upload (folder or multi-file) ─────────────────────────
  async function handleBulkUpload() {
    if (!bulkFiles.length) return
    const accepted = ['.txt', '.conf', '.cfg', '.log', '.config']
    const toUpload = bulkFiles.filter(f =>
      accepted.some(ext => f.name.toLowerCase().endsWith(ext))
    )
    if (!toUpload.length) {
      setBulkProgress({ done: 0, total: 0, results: [], error: 'No supported files found (.txt .conf .cfg .log .config)' })
      return
    }

    const results = []
    setBulkProgress({ done: 0, total: toUpload.length, results })

    for (let i = 0; i < toUpload.length; i++) {
      const f = toUpload[i]
      const form = new FormData()
      form.append('file', f)
      form.append('hostname', 'unknown')   // auto-detect from content
      form.append('vendor', 'auto')
      try {
        const res = await fetch('/api/ingest/config', { method: 'POST', body: form })
        const json = await res.json()
        if (!res.ok) throw new Error(json.detail || res.statusText)
        results.push({ name: f.name, ok: true, device: json.device, vendor: json.vendor })
      } catch (e) {
        results.push({ name: f.name, ok: false, error: e.message })
      }
      setBulkProgress({ done: i + 1, total: toUpload.length, results: [...results] })
    }

    onIngested?.()
  }

  const panelStyle = {
    position: 'absolute', top: 10, right: 10, zIndex: 1000,
    background: '#1e293b', border: '1px solid #334155', borderRadius: 10,
    padding: 20, width: 360, color: '#e2e8f0', fontSize: 13,
    boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
    maxHeight: '80vh', overflowY: 'auto',
  }
  const inp = {
    width: '100%', boxSizing: 'border-box', background: '#0f172a',
    border: '1px solid #334155', borderRadius: 6, padding: '7px 10px',
    color: '#f1f5f9', fontSize: 12, marginBottom: 10, outline: 'none',
  }
  const tabBtn = (active) => ({
    flex: 1, padding: '6px 0', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
    borderRadius: 6,
    background: active ? '#1d4ed8' : '#0f172a',
    color: active ? '#fff' : '#64748b',
  })

  const isBulkRunning = bulkProgress && bulkProgress.done < bulkProgress.total

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>📂 Ingest Config Files</span>
        <button onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 16 }}>✕</button>
      </div>

      {/* Mode tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 14, background: '#0f172a', padding: 4, borderRadius: 8 }}>
        <button style={tabBtn(mode === 'single')} onClick={() => { setMode('single'); setStatus(null) }}>
          Single File
        </button>
        <button style={tabBtn(mode === 'bulk')} onClick={() => { setMode('bulk'); setBulkProgress(null) }}>
          Folder / Multiple
        </button>
      </div>

      {/* ── Single file mode ── */}
      {mode === 'single' && (
        <>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 11, color: '#94a3b8' }}>Config file</label>
          <input type="file" ref={fileRef} accept=".txt,.conf,.cfg,.log,.config"
            onChange={e => { setFile(e.target.files[0]); setStatus(null) }}
            style={{ ...inp, padding: '4px 6px' }} />

          <label style={{ display: 'block', marginBottom: 6, fontSize: 11, color: '#94a3b8' }}>
            Hostname override <span style={{ color: '#475569' }}>(leave blank to auto-detect)</span>
          </label>
          <input style={inp} type="text" placeholder="eqx-nyc-rtr-01"
            value={hostname} onChange={e => setHostname(e.target.value)} />

          <label style={{ display: 'block', marginBottom: 6, fontSize: 11, color: '#94a3b8' }}>Vendor</label>
          <select style={inp} value={vendor} onChange={e => setVendor(e.target.value)}>
            <option value="auto">Auto-detect</option>
            <option value="cisco">Cisco IOS / NX-OS</option>
            <option value="juniper">Juniper JunOS</option>
            <option value="huawei">Huawei VRP</option>
          </select>

          {status === 'loading' && (
            <div style={{ color: '#60a5fa', marginBottom: 10, fontSize: 12 }}>⟳ Parsing and indexing…</div>
          )}
          {status?.ok && (
            <div style={{ color: '#4ade80', marginBottom: 10, fontSize: 12 }}>
              ✓ {status.data.device} ({status.data.vendor}) ingested
              — POP: {status.data.pop || 'undetected'}, {status.data.interfaces} interfaces
            </div>
          )}
          {status?.error && (
            <div style={{ color: '#f87171', marginBottom: 10, fontSize: 12 }}>⚠ {status.error}</div>
          )}

          <button
            style={{
              width: '100%', padding: '9px 0', borderRadius: 6, border: 'none',
              background: !file || status === 'loading' ? '#1e293b' : '#1d4ed8',
              color: '#f1f5f9', fontWeight: 700, cursor: !file ? 'not-allowed' : 'pointer',
              opacity: !file || status === 'loading' ? 0.5 : 1,
            }}
            onClick={handleUpload}
            disabled={!file || status === 'loading'}
          >
            Upload & Parse
          </button>
        </>
      )}

      {/* ── Bulk mode ── */}
      {mode === 'bulk' && (
        <>
          <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 10 }}>
            Select a folder or multiple files. Vendor and hostname are auto-detected
            from each file's content and name.
          </div>

          {/* Folder picker */}
          <label style={{ display: 'block', marginBottom: 6, fontSize: 11, color: '#94a3b8' }}>Select folder</label>
          <input
            type="file"
            ref={folderRef}
            // webkitdirectory lets the browser show a folder picker
            // and exposes all files within it
            webkitdirectory=""
            directory=""
            multiple
            style={{ ...inp, padding: '4px 6px' }}
            onChange={e => { setBulkFiles(Array.from(e.target.files)); setBulkProgress(null) }}
          />

          {/* Or multi-file picker */}
          <label style={{ display: 'block', marginBottom: 6, fontSize: 11, color: '#94a3b8' }}>
            — or select multiple files individually —
          </label>
          <input
            type="file"
            multiple
            accept=".txt,.conf,.cfg,.log,.config"
            style={{ ...inp, padding: '4px 6px' }}
            onChange={e => { setBulkFiles(Array.from(e.target.files)); setBulkProgress(null) }}
          />

          {bulkFiles.length > 0 && !bulkProgress && (
            <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 10 }}>
              {bulkFiles.length} file{bulkFiles.length !== 1 ? 's' : ''} selected
            </div>
          )}

          {/* Progress */}
          {bulkProgress && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: '#60a5fa', marginBottom: 6 }}>
                {bulkProgress.done < bulkProgress.total
                  ? `⟳ Processing ${bulkProgress.done + 1} of ${bulkProgress.total}…`
                  : `✓ Done — ${bulkProgress.done} file${bulkProgress.done !== 1 ? 's' : ''} processed`}
              </div>
              {/* Progress bar */}
              <div style={{ background: '#0f172a', borderRadius: 4, height: 6, marginBottom: 8 }}>
                <div style={{
                  background: '#1d4ed8', borderRadius: 4, height: 6,
                  width: `${Math.round((bulkProgress.done / bulkProgress.total) * 100)}%`,
                  transition: 'width 0.2s',
                }} />
              </div>
              {/* Per-file results (scrollable) */}
              <div style={{ maxHeight: 180, overflowY: 'auto', fontSize: 11 }}>
                {bulkProgress.results.map((r, i) => (
                  <div key={i} style={{ color: r.ok ? '#4ade80' : '#f87171', marginBottom: 2 }}>
                    {r.ok
                      ? `✓ ${r.name} → ${r.device} (${r.vendor})`
                      : `✗ ${r.name}: ${r.error}`}
                  </div>
                ))}
              </div>
              {bulkProgress.error && (
                <div style={{ color: '#f87171', fontSize: 12, marginTop: 6 }}>{bulkProgress.error}</div>
              )}
            </div>
          )}

          <button
            style={{
              width: '100%', padding: '9px 0', borderRadius: 6, border: 'none',
              background: !bulkFiles.length || isBulkRunning ? '#1e293b' : '#1d4ed8',
              color: '#f1f5f9', fontWeight: 700,
              cursor: !bulkFiles.length || isBulkRunning ? 'not-allowed' : 'pointer',
              opacity: !bulkFiles.length || isBulkRunning ? 0.5 : 1,
            }}
            onClick={handleBulkUpload}
            disabled={!bulkFiles.length || isBulkRunning}
          >
            {isBulkRunning ? 'Uploading…' : `Upload ${bulkFiles.length || ''} Files`}
          </button>
        </>
      )}
    </div>
  )
}


// ─── App root ─────────────────────────────────────────────────────
export default function App() {
  const [elements,     setElements]     = useState(null)
  const [summary,      setSummary]      = useState(null)
  const [leftTab,      setLeftTab]      = useState('topology')
  const [selectedNode, setSelectedNode] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [pathResult,   setPathResult]   = useState(null)
  const [loading,      setLoading]      = useState(false)
  const [esStatus,     setEsStatus]     = useState('checking')
  const [showIngest,   setShowIngest]   = useState(false)
  const [popModal,     setPopModal]     = useState(null)   // { nodeData } | null
  const [pops,         setPops]         = useState([])     // known POP labels
  const [discoverStatus, setDiscoverStatus] = useState(null) // null | 'running' | {result} | {error}
  const [wipeStatus,   setWipeStatus]   = useState(null) // null | 'running' | {ok} | {error}
  // For path query pre-fill from context menu
  const [pathSource,   setPathSource]   = useState(null)

  const pathSearchRef = useRef()

  const handleEdgeClick = useCallback(data => {
    setSelectedEdge(data); setSelectedNode(null)
  }, [])
  const handleNodeClick = useCallback(data => {
    setSelectedNode(data); setSelectedEdge(null)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [topo, summ, health, popList] = await Promise.all([
        api.topology(),
        api.topologySummary().catch(() => null),
        api.health().catch(() => ({ status: 'error' })),
        fetch('/api/ingest/pops').then(r => r.json()).catch(() => []),
      ])
      const edgesWithClass = topo.edges.map(e => ({
        ...e, data: { ...e.data, classes: e.classes },
      }))
      setElements({ nodes: topo.nodes, edges: edgesWithClass })
      setSummary(summ)
      setEsStatus(health.status === 'ok' ? health.elasticsearch : 'error')
      setPops((popList || []).map(p => p.pop).filter(Boolean))
    } catch (err) {
      console.error('Failed to load topology:', err)
      setEsStatus('error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleDiscover = useCallback(async () => {
    setDiscoverStatus('running')
    try {
      const res = await fetch('/api/ingest/discover-connections', { method: 'POST' })
      const json = await res.json()
      if (!res.ok) throw new Error(json.detail || res.statusText)
      setDiscoverStatus({ result: json })
      // Refresh topology so new connections appear immediately
      await load()
      // Auto-clear the notification after 8 seconds
      setTimeout(() => setDiscoverStatus(null), 8000)
    } catch (e) {
      setDiscoverStatus({ error: e.message })
      setTimeout(() => setDiscoverStatus(null), 6000)
    }
  }, [load])

  const handleClearMap = useCallback(async () => {
    const ok = window.confirm(
      'Clear the entire map?\n\n' +
      'This permanently deletes ALL devices, interfaces, connections, and ACLs ' +
      'currently ingested. This cannot be undone — you would need to re-import ' +
      'your config files from scratch.'
    )
    if (!ok) return

    setWipeStatus('running')
    try {
      const res = await fetch('/api/ingest/wipe', { method: 'DELETE' })
      const json = await res.json()
      if (!res.ok) throw new Error(json.detail || res.statusText)
      setWipeStatus({ ok: true })
      // Clear any stale selections pointing at now-deleted data
      setSelectedNode(null); setSelectedEdge(null); setPathResult(null)
      await load()
      setTimeout(() => setWipeStatus(null), 5000)
    } catch (e) {
      setWipeStatus({ error: e.message })
      setTimeout(() => setWipeStatus(null), 6000)
    }
  }, [load])

  // Handle right-click "Path Query from here" — switch to pathfind tab and pre-fill
  const handlePathQueryFrom = useCallback(nodeData => {
    setLeftTab('pathfind')
    setPathSource(nodeData?.label || nodeData?.id || '')
  }, [])

  // Handle right-click "Assign to POP"
  const handleAssignPop = useCallback(nodeData => {
    setPopModal({ nodeData })
  }, [])

  // Commit POP assignment via API
  const handlePopAssign = useCallback(async (deviceName, pop) => {
    const res = await fetch(`/api/ingest/devices/${encodeURIComponent(deviceName)}/pop`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pop }),
    })
    if (!res.ok) {
      const j = await res.json().catch(() => ({}))
      throw new Error(j.detail || 'Failed to assign POP')
    }
    // Refresh topology so the POP box appears immediately
    await load()
  }, [load])

  const cyElements = elements ? [...elements.nodes, ...elements.edges] : []

  return (
    <div style={S.root}>
      {/* ── Header ─────────────────────────────────────────── */}
      <header style={S.header}>
        <div>
          <span style={S.logo}>🗺 TreasureMap</span>
          <span style={S.logoSub}>Network Topology</span>
        </div>

        <div style={S.legend}>
          <LegendItem color="#22c55e" label="Up"        />
          <LegendItem color="#64748b" label="Disabled"  dashed />
          <LegendItem color="#f97316" label="ACL/FW"    />
          <LegendItem color="#3b82f6" label="Trunk"     thick />
          <LegendItem shape="diamond" label="Gateway"   />
          <LegendItem shape="oob"     label="OOB"       />
        </div>

        <button style={S.ingestBtn} onClick={() => setShowIngest(v => !v)}>
          📂 Ingest
        </button>
        <button
          style={{
            ...S.ingestBtn,
            borderColor: '#065f46', background: '#064e3b', color: '#6ee7b7',
            opacity: discoverStatus === 'running' ? 0.6 : 1,
          }}
          onClick={handleDiscover}
          disabled={discoverStatus === 'running'}
          title="Auto-detect connections between devices using subnet matching and interface descriptions"
        >
          {discoverStatus === 'running' ? '⟳ Discovering…' : '🔗 Discover'}
        </button>
        <button style={S.refreshBtn} onClick={load} disabled={loading}>
          {loading ? '⟳ Loading…' : '⟳ Refresh'}
        </button>
        <button
          style={{
            ...S.refreshBtn,
            borderColor: '#7f1d1d', background: '#450a0a', color: '#fca5a5',
            opacity: wipeStatus === 'running' ? 0.6 : 1,
          }}
          onClick={handleClearMap}
          disabled={wipeStatus === 'running'}
          title="Delete all devices, interfaces, connections, and ACLs — start over before importing a new set of configs"
        >
          {wipeStatus === 'running' ? '⟳ Clearing…' : '🗑 Clear Map'}
        </button>

        {/* Clear-map result notification */}
        {wipeStatus && wipeStatus !== 'running' && (
          <div style={{
            position: 'fixed', bottom: 40, right: 24, zIndex: 2000,
            background: wipeStatus.error ? '#450a0a' : '#052e16',
            border: `1px solid ${wipeStatus.error ? '#991b1b' : '#166534'}`,
            borderRadius: 10, padding: '14px 18px', color: '#e2e8f0',
            fontSize: 13, boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            minWidth: 280,
          }}>
            {wipeStatus.error ? (
              <div style={{ color: '#fca5a5' }}>⚠ Clear failed: {wipeStatus.error}</div>
            ) : (
              <div style={{ color: '#6ee7b7' }}>🗑 Map cleared — all devices, interfaces, connections, and ACLs deleted.</div>
            )}
          </div>
        )}

        {/* Discovery result notification */}
        {discoverStatus && discoverStatus !== 'running' && (
          <div style={{
            position: 'fixed', bottom: 40, right: 24, zIndex: 2000,
            background: discoverStatus.error ? '#450a0a' : '#052e16',
            border: `1px solid ${discoverStatus.error ? '#991b1b' : '#166534'}`,
            borderRadius: 10, padding: '14px 18px', color: '#e2e8f0',
            fontSize: 13, boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            minWidth: 280,
          }}>
            {discoverStatus.error ? (
              <div style={{ color: '#fca5a5' }}>⚠ Discovery failed: {discoverStatus.error}</div>
            ) : (
              <>
                <div style={{ fontWeight: 700, color: '#6ee7b7', marginBottom: 6 }}>
                  🔗 Connection Discovery Complete
                </div>
                <div>Found: <b>{discoverStatus.result.discovered}</b> new connections</div>
                <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
                  subnet: {discoverStatus.result.by_method?.subnet ?? 0} ·
                  description: {discoverStatus.result.by_method?.description ?? 0} ·
                  cdp/lldp: {discoverStatus.result.by_method?.cdp_lldp ?? 0}
                </div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                  Total connections in topology: {discoverStatus.result.total}
                </div>
              </>
            )}
          </div>
        )}
      </header>

      {/* ── Body ───────────────────────────────────────────── */}
      <div style={S.body}>

        {/* Left panel */}
        <aside style={S.leftPanel}>
          <div style={S.leftTabs}>
            <button style={S.leftTab(leftTab === 'topology')} onClick={() => setLeftTab('topology')}>
              📋 Overview
            </button>
            <button style={S.leftTab(leftTab === 'pathfind')} onClick={() => setLeftTab('pathfind')}>
              🔍 Path Query
            </button>
          </div>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            {leftTab === 'topology' && (
              <TextualView summary={summary} nodes={elements?.nodes} edges={elements?.edges} />
            )}
            {leftTab === 'pathfind' && (
              <PathSearch
                ref={pathSearchRef}
                prefillSource={pathSource}
                onPrefillConsumed={() => setPathSource(null)}
                onResult={r => setPathResult(r)}
                onClear={() => setPathResult(null)}
              />
            )}
          </div>
        </aside>

        {/* Graph area */}
        <main style={S.graphArea}>
          {!elements && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              color: '#334155', fontSize: 14,
            }}>
              {loading ? 'Loading topology…' : 'No data — is Elasticsearch running?'}
            </div>
          )}
          <TopologyGraph
            elements={cyElements}
            pathResult={pathResult}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
            onPathQueryFrom={handlePathQueryFrom}
            onAssignPop={handleAssignPop}
          />

          {/* Config ingest float panel */}
          {showIngest && (
            <IngestPanel
              onIngested={() => { load(); setShowIngest(false) }}
              onClose={() => setShowIngest(false)}
            />
          )}
        </main>

        {/* Right panel */}
        <aside style={S.rightPanel}>
          <DeviceDetails selectedNode={selectedNode} selectedEdge={selectedEdge} />
        </aside>

      </div>

      {/* ── Status bar ─────────────────────────────────────── */}
      <div style={S.statusBar}>
        <span style={S.dot(esStatus === 'error' ? '#ef4444' : esStatus === 'checking' ? '#f59e0b' : '#22c55e')} />
        <span>Elasticsearch {esStatus}</span>
        {summary && (
          <>
            <span>·</span><span>{summary.devices} devices</span>
            <span>·</span><span>{summary.connections} links</span>
            {pops.length > 0 && <><span>·</span><span>{pops.length} POPs</span></>}
          </>
        )}
        {selectedNode && <><span>·</span><span>Selected: {selectedNode.label}</span></>}
      </div>

      {/* POP assignment modal */}
      {popModal && (
        <PopAssignModal
          device={popModal.nodeData}
          pops={pops}
          onAssign={handlePopAssign}
          onClose={() => setPopModal(null)}
        />
      )}
    </div>
  )
}
