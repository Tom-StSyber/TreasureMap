/**
 * TreasureMap — Cytoscape.js topology graph.
 *
 * Edge classes → visual encoding:
 *   edge-up       green solid line
 *   edge-disabled black dashed line
 *   edge-acl      orange solid line
 *   edge-trunk    thick blue solid line
 *
 * Node role classes:
 *   node-role-gateway   gold star border + larger node
 *   node-role-oob       magenta border + dashed outline
 *   node-role-core      teal accent border
 *
 * POP compound nodes:
 *   pop-box         semi-transparent labelled box around POP members
 *   pop-unassigned  invisible parent for devices with no detected POP
 *
 * When a pathfind result is active:
 *   edge-path     highlighted gold line
 *   node-path     highlighted node
 *   node-src      source node
 *   node-dst      destination node
 *
 * Right-click context menu:
 *   - Path Query from here  → calls onPathQueryFrom(nodeData)
 *   - Assign to POP…        → calls onAssignPop(nodeData)
 */
import { useEffect, useRef, useCallback, useState } from 'react'
import cytoscape from 'cytoscape'
import dagre from 'dagre'
import cytoscapeDagre from 'cytoscape-dagre'

cytoscapeDagre(cytoscape, dagre)

// ─── Node icon mapping ───────────────────────────────────────────
const DEVICE_EMOJI = {
  router:   '🔀',
  switch:   '⎇',
  firewall: '🛡',
  server:   '🖥',
  host:     '💻',
  cloud:    '☁',
  default:  '📦',
}

// ─── Cytoscape stylesheet ────────────────────────────────────────
const STYLESHEET = [
  // ── POP compound boxes ─────────────────────────────────────────
  {
    selector: '.pop-box',
    style: {
      'background-color':       'data(bg)',
      'background-opacity':     0.35,
      'border-color':           'data(border)',
      'border-width':           2,
      'border-style':           'solid',
      'label':                  'data(label)',
      'color':                  '#94a3b8',
      'font-size':              13,
      'font-weight':            700,
      'text-valign':            'top',
      'text-halign':            'center',
      'text-margin-y':          -8,
      'text-background-color':  '#0f1117',
      'text-background-opacity':0.7,
      'text-background-padding':4,
      'padding':                24,
      'shape':                  'round-rectangle',
    },
  },
  {
    selector: '.pop-unassigned',
    style: {
      'background-opacity': 0,
      'border-width':       0,
      'label':              '',
      'padding':            16,
    },
  },

  // ── Base device node ─────────────────────────────────────────
  {
    selector: 'node:childless',   // only leaf (device) nodes get this
    style: {
      'background-color':  '#1e293b',
      'background-opacity': 0,
      'border-width':      0,
      'label':             'data(label)',
      'color':             '#e2e8f0',
      'font-size':         11,
      'text-valign':       'bottom',
      'text-halign':       'center',
      'text-margin-y':     6,
      'width':             64,
      'height':            64,
      'text-wrap':         'wrap',
      'text-max-width':    100,
      'background-fit':    'contain',
      'background-clip':   'none',
    },
  },

  // Device-type icons (PNG) — Cytoscape programmatic API needs raw URL, no url() wrapper
  { selector: '.node-router',
    style: { 'background-image': `${window.location.origin}/icons/router.png`, 'background-opacity': 0 } },
  { selector: '.node-switch',
    style: { 'background-image': `${window.location.origin}/icons/switch.png`, 'background-opacity': 0 } },
  { selector: '.node-firewall',
    style: { 'background-image': `${window.location.origin}/icons/firewall.png`, 'background-opacity': 0 } },
  { selector: '.node-server',
    style: { 'background-image': `${window.location.origin}/icons/server.png`, 'background-opacity': 0 } },
  { selector: '.node-host',
    style: { 'background-image': `${window.location.origin}/icons/host.png`, 'background-opacity': 0 } },
  // Cloud/internet — no icon file, keep coloured shape
  { selector: '.node-cloud',
    style: { 'background-color': '#164e63', 'background-opacity': 1,
             'border-width': 2, 'border-color': '#38bdf8' } },

  // ── Role overlays ───────────────────────────────────────────
  // Gateway — gold star border, larger, bold label
  {
    selector: '.node-role-gateway',
    style: {
      'border-color':  '#f59e0b',
      'border-width':  4,
      'width':         60,
      'height':        60,
      'font-weight':   700,
      'font-size':     12,
      'shape':         'diamond',
    },
  },
  // OOB — magenta dashed border
  {
    selector: '.node-role-oob',
    style: {
      'border-color':  '#d946ef',
      'border-width':  3,
      'border-style':  'dashed',
      'opacity':       0.85,
    },
  },
  // Core — teal border
  {
    selector: '.node-role-core',
    style: {
      'border-color': '#14b8a6',
      'border-width': 3,
    },
  },

  // ── Edge base ────────────────────────────────────────────────
  {
    selector: 'edge',
    style: {
      'curve-style':              'bezier',
      'width':                    2,
      'label':                    '',
      'font-size':                10,
      'color':                    '#94a3b8',
      'text-background-color':    '#0f1117',
      'text-background-opacity':  0.8,
      'text-background-padding':  2,
    },
  },
  { selector: '.edge-up',
    style: { 'line-color': '#22c55e', 'target-arrow-color': '#22c55e', 'line-style': 'solid' } },
  { selector: '.edge-disabled',
    style: { 'line-color': '#64748b', 'target-arrow-color': '#64748b',
              'line-style': 'dashed', 'line-dash-pattern': [8, 4], 'width': 1.5, 'opacity': 0.6 } },
  { selector: '.edge-acl',
    style: { 'line-color': '#f97316', 'target-arrow-color': '#f97316', 'line-style': 'solid' } },
  { selector: '.edge-trunk',
    style: { 'line-color': '#3b82f6', 'target-arrow-color': '#3b82f6', 'line-style': 'solid', 'width': 5 } },

  // ── Path highlight ───────────────────────────────────────────
  { selector: '.edge-path',
    style: { 'line-color': '#facc15', 'target-arrow-color': '#facc15', 'width': 6, 'z-index': 10, 'opacity': 1 } },
  { selector: '.node-path',
    style: { 'border-color': '#facc15', 'border-width': 3 } },
  { selector: '.node-src',
    style: { 'border-color': '#4ade80', 'border-width': 4, 'background-color': '#14532d' } },
  { selector: '.node-dst',
    style: { 'border-color': '#f87171', 'border-width': 4, 'background-color': '#450a0a' } },

  // Selected
  { selector: 'node:childless:selected',
    style: { 'border-color': '#f59e0b', 'border-width': 3, 'background-opacity': 0.15,
             'background-color': '#f59e0b' } },
]

// ─── Context menu ─────────────────────────────────────────────────
const MENU_STYLE = {
  position: 'fixed',
  zIndex:   9999,
  background:   '#1e293b',
  border:       '1px solid #334155',
  borderRadius: 8,
  boxShadow:    '0 8px 32px rgba(0,0,0,0.5)',
  minWidth:     180,
  overflow:     'hidden',
  fontSize:     13,
  color:        '#e2e8f0',
}
const MENU_ITEM_STYLE = {
  padding:    '9px 16px',
  cursor:     'pointer',
  display:    'flex',
  alignItems: 'center',
  gap:        8,
  transition: 'background 0.1s',
}
const MENU_DIVIDER = { height: 1, background: '#334155', margin: '4px 0' }

function ContextMenu({ x, y, nodeData, onClose, onPathQuery, onAssignPop }) {
  const [hovered, setHovered] = useState(null)

  const item = (icon, label, action) => (
    <div
      style={{
        ...MENU_ITEM_STYLE,
        background: hovered === label ? '#334155' : 'transparent',
      }}
      onMouseEnter={() => setHovered(label)}
      onMouseLeave={() => setHovered(null)}
      onClick={() => { action(); onClose(); }}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </div>
  )

  return (
    <div style={{ ...MENU_STYLE, left: x, top: y }} onContextMenu={e => e.preventDefault()}>
      <div style={{ padding: '6px 16px 4px', fontSize: 11, color: '#64748b', fontWeight: 600 }}>
        {nodeData?.label || 'Device'}
      </div>
      <div style={MENU_DIVIDER} />
      {item('🔍', 'Path Query from here', () => onPathQuery(nodeData))}
      {item('📍', 'Assign to POP…',       () => onAssignPop(nodeData))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────

export default function TopologyGraph({
  elements,
  pathResult,
  onNodeClick,
  onEdgeClick,
  onPathQueryFrom,   // (nodeData) → pre-fill PathSearch source
  onAssignPop,       // (nodeData) → open POP assign modal
}) {
  const containerRef = useRef(null)
  const cyRef        = useRef(null)
  const [menu, setMenu] = useState(null)   // { x, y, nodeData }

  // Close context menu on outside click
  useEffect(() => {
    if (!menu) return
    const close = () => setMenu(null)
    window.addEventListener('click', close)
    window.addEventListener('contextmenu', close)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('contextmenu', close)
    }
  }, [menu])

  // Initialise Cytoscape once
  useEffect(() => {
    if (!containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: STYLESHEET,
      layout: { name: 'preset' },
      userZoomingEnabled:  true,
      userPanningEnabled:  true,
      boxSelectionEnabled: false,
      minZoom: 0.05,
      maxZoom: 4,
      wheelSensitivity: 0.1,
    })

    // Left-click → select node/edge
    cy.on('tap', 'node:childless', evt => {
      onNodeClick?.(evt.target.data())
    })
    cy.on('tap', 'edge', evt => {
      onEdgeClick?.(evt.target.data())
    })
    cy.on('tap', evt => {
      if (evt.target === cy) {
        onNodeClick?.(null)
        onEdgeClick?.(null)
        setMenu(null)
      }
    })

    // Right-click on device node → context menu
    cy.on('cxttap', 'node:childless', evt => {
      evt.originalEvent?.preventDefault()
      const rendPos = evt.renderedPosition
      const container = containerRef.current.getBoundingClientRect()
      setMenu({
        x: container.left + rendPos.x,
        y: container.top  + rendPos.y,
        nodeData: evt.target.data(),
      })
    })

    cyRef.current = cy
    return () => cy.destroy()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Load / reload elements whenever topology data changes
  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !elements) return

    cy.batch(() => {
      cy.elements().remove()
      cy.add(elements)
    })

    // Run dagre layout on device nodes; POP boxes follow their children
    cy.layout({
      name:             'dagre',
      rankDir:          'TB',
      nodeSep:          70,
      rankSep:          110,
      animate:          true,
      animationDuration:400,
      // Only apply layout to childless nodes (devices), not POP boxes
      fit:              true,
      padding:          40,
    }).run()

  }, [elements])

  // Highlight path
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('edge-path node-path node-src node-dst')
    if (!pathResult?.found || !pathResult.path?.length) return

    pathResult.path.forEach((nodeName, idx) => {
      const n = cy.$(`#${CSS.escape(nodeName)}`)
      if (idx === 0) n.addClass('node-src')
      else if (idx === pathResult.path.length - 1) n.addClass('node-dst')
      else n.addClass('node-path')
    })
    pathResult.edges?.forEach(edgeId => {
      cy.$(`#${CSS.escape(edgeId)}`).addClass('edge-path')
    })
    const pathEls = cy.$('.edge-path, .node-src, .node-dst, .node-path')
    if (pathEls.length) cy.fit(pathEls, 80)
  }, [pathResult])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%', background: '#0f1117' }}
      />

      {/* Context menu */}
      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          nodeData={menu.nodeData}
          onClose={() => setMenu(null)}
          onPathQuery={data => { onPathQueryFrom?.(data); setMenu(null) }}
          onAssignPop={data => { onAssignPop?.(data);    setMenu(null) }}
        />
      )}
    </div>
  )
}
