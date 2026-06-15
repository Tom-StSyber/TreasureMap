/**
 * TreasureMap — Root application shell.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────┐
 *   │  Header (title + legend + refresh)                  │
 *   ├─────────────┬───────────────────────┬───────────────┤
 *   │ Left panel  │   Cytoscape graph     │  Right panel  │
 *   │ (tab-based) │   (fills remaining)   │  (detail /    │
 *   │  - Textual  │                       │   path result)│
 *   │  - PathFind │                       │               │
 *   └─────────────┴───────────────────────┴───────────────┘
 */
import { useState, useEffect, useCallback } from 'react'
import TopologyGraph from './components/TopologyGraph.jsx'
import IngestModal   from './components/IngestModal.jsx'
import TextualView   from './components/TextualView.jsx'
import PathSearch    from './components/PathSearch.jsx'
import DeviceDetails from './components/DeviceDetails.jsx'
import { api }       from './api/client.js'

// ─── Layout constants ─────────────────────────────────────────────
const LEFT_W  = 340
const RIGHT_W = 320

const S = {
  root: { display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden', background: '#0f1117' },
  header: {
    display: 'flex', alignItems: 'center', gap: 16,
    padding: '0 16px', height: 50, flexShrink: 0,
    background: '#111827', borderBottom: '1px solid #1e293b',
  },
  logo: { fontSize: 18, fontWeight: 800, color: '#f1f5f9', letterSpacing: -0.5 },
  logoSub: { fontSize: 12, color: '#64748b', marginLeft: 6 },
  legend: { display: 'flex', gap: 14, marginLeft: 'auto', alignItems: 'center', fontSize: 12, color: '#94a3b8' },
  legendItem: { display: 'flex', alignItems: 'center', gap: 5 },
  legendLine: (color, dashed, thick) => ({
    width: thick ? 28 : 24, height: thick ? 4 : 2, background: color,
    borderRadius: 2,
    borderTop: dashed ? `2px dashed ${color}` : 'none',
    background: dashed ? 'transparent' : color,
  }),
  body: { display: 'flex', flex: 1, overflow: 'hidden' },
  leftPanel: {
    width: LEFT_W, flexShrink: 0, borderRight: '1px solid #1e293b',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  leftTabs: { display: 'flex', borderBottom: '1px solid #1e293b', flexShrink: 0 },
  leftTab: (active) => ({
    flex: 1, padding: '10px 0', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
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
    background: '#1e3a8a', color: '#93c5fd', cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  dot: (c) => ({ width: 8, height: 8, borderRadius: '50%', background: c, display: 'inline-block' }),
}

function LegendItem({ color, label, dashed, thick }) {
  const lineStyle = thick
    ? { width: 28, height: 4, background: color, borderRadius: 2 }
    : dashed
    ? { width: 24, height: 0, borderTop: `2px dashed ${color}` }
    : { width: 24, height: 2, background: color, borderRadius: 1 }
  return (
    <div style={S.legendItem}>
      <div style={lineStyle} />
      <span>{label}</span>
    </div>
  )
}

export default function App() {
  const [elements,    setElements]    = useState(null)
  const [summary,     setSummary]     = useState(null)
  const [leftTab,     setLeftTab]     = useState('topology')  // 'topology' | 'pathfind'
  const [selectedNode, setSelectedNode] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [pathResult,  setPathResult]  = useState(null)
  const [loading,     setLoading]     = useState(false)
  const [esStatus,    setEsStatus]    = useState('checking')
  const [showIngest,  setShowIngest]  = useState(false)

  // Flatten edge classes into data for DeviceDetails
  const handleEdgeClick = useCallback((data) => {
    setSelectedEdge(data)
    setSelectedNode(null)
  }, [])
  const handleNodeClick = useCallback((data) => {
    setSelectedNode(data)
    setSelectedEdge(null)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [topo, summ, health] = await Promise.all([
        api.topology(),
        api.topologySummary().catch(() => null),
        api.health().catch(() => ({ status: 'error' })),
      ])
      // Attach edge classes to data so DeviceDetails can render them
      const edgesWithClass = topo.edges.map(e => ({
        ...e,
        data: { ...e.data, classes: e.classes },
      }))
      setElements({ nodes: topo.nodes, edges: edgesWithClass })
      setSummary(summ)
      setEsStatus(health.status === 'ok' ? health.elasticsearch : 'error')
    } catch (err) {
      console.error('Failed to load topology:', err)
      setEsStatus('error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const cyElements = elements
    ? (() => {
        const nodeIds = new Set(elements.nodes.map(n => n.data.id))
        const validEdges = elements.edges.filter(
          e => nodeIds.has(e.data.source) && nodeIds.has(e.data.target)
        )
        return [...elements.nodes, ...validEdges]
      })()
    : []

  return (
    <div style={S.root}>
      {/* ── Header ─────────────────────────────────────────── */}
      <header style={S.header}>
        <div>
          <span style={S.logo}>🗺 TreasureMap</span>
          <span style={S.logoSub}>Network Topology</span>
        </div>

        <div style={S.legend}>
          <LegendItem color="#22c55e" label="Up"       />
          <LegendItem color="#64748b" label="Disabled" dashed />
          <LegendItem color="#f97316" label="ACL/FW"   />
          <LegendItem color="#3b82f6" label="Trunk"    thick />
          <LegendItem color="#a855f7" label="BGP"      dashed />
        </div>

        <button style={S.ingestBtn} onClick={() => setShowIngest(true)}>
          ⚙ Ingest Configs
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
              <TextualView
                summary={summary}
                nodes={elements?.nodes}
                edges={elements?.edges}
              />
            )}
            {leftTab === 'pathfind' && (
              <PathSearch
                onResult={(r) => { setPathResult(r); }}
                onClear={() => setPathResult(null)}
              />
            )}
          </div>
        </aside>

        {/* Graph */}
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
          />
        </main>

        {/* Right panel */}
        <aside style={S.rightPanel}>
          <DeviceDetails
            selectedNode={selectedNode}
            selectedEdge={selectedEdge}
          />
        </aside>

      </div>

      {/* ── Status bar ─────────────────────────────────────── */}
      <div style={S.statusBar}>
        <span style={S.dot(esStatus === 'error' ? '#ef4444' : esStatus === 'checking' ? '#f59e0b' : '#22c55e')} />
        <span>Elasticsearch {esStatus}</span>
        {summary && (
          <>
            <span>·</span>
            <span>{summary.devices} devices</span>
            <span>·</span>
            <span>{summary.connections} links</span>
          </>
        )}
        {selectedNode && <><span>·</span><span>Selected: {selectedNode.label}</span></>}
      </div>

      {/* ── Ingest modal ───────────────────────────────────── */}
      {showIngest && (
        <IngestModal
          onClose={() => setShowIngest(false)}
          onSuccess={() => {
            setShowIngest(false)
            load()
          }}
        />
      )}
    </div>
  )
}
