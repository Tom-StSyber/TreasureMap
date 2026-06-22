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
  const [file,     setFile]     = useState(null)
  const [hostname, setHostname] = useState('')
  const [vendor,   setVendor]   = useState('auto')
  const [status,   setStatus]   = useState(null)   // null | 'loading' | {ok} | {error}
  const fileRef = useRef()

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

  const panelStyle = {
    position: 'absolute', top: 10, right: 10, zIndex: 1000,
    background: '#1e293b', border: '1px solid #334155', borderRadius: 10,
    padding: 20, width: 320, color: '#e2e8f0', fontSize: 13,
    boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
  }
  const inp = {
    width: '100%', boxSizing: 'border-box', background: '#0f172a',
    border: '1px solid #334155', borderRadius: 6, padding: '7px 10px',
    color: '#f1f5f9', fontSize: 12, marginBottom: 10, outline: 'none',
  }
  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>📂 Ingest Config File</span>
        <button onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 16 }}>✕</button>
      </div>

      <label style={{ display: 'block', marginBottom: 6, fontSize: 11, color: '#94a3b8' }}>Config file</label>
      <input type="file" ref={fileRef} accept=".txt,.conf,.cfg,.log"
        onChange={e => setFile(e.target.files[0])} style={{ ...inp, padding: '4px 6px' }} />

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
        <button style={S.refreshBtn} onClick={load} disabled={loading}>
          {loading ? '⟳ Loading…' : '⟳ Refresh'}
        </button>
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
