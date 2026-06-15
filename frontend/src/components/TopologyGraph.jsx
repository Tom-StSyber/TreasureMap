/**
 * TreasureMap — Cytoscape.js topology graph.
 *
 * Edge classes → visual encoding:
 *   edge-up       green solid line
 *   edge-disabled black dashed line
 *   edge-acl      orange solid line
 *   edge-trunk    thick blue solid line
 *
 * When a pathfind result is active:
 *   edge-path     highlighted gold line (overlaid on top of existing style)
 *   node-path     highlighted node
 *   node-src      source node
 *   node-dst      destination node
 */
import { useEffect, useRef, useCallback } from 'react'
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
  // All nodes
  {
    selector: 'node',
    style: {
      'background-color': '#1e293b',
      'border-width': 2,
      'border-color': '#475569',
      'label': 'data(label)',
      'color': '#e2e8f0',
      'font-size': 11,
      'text-valign': 'bottom',
      'text-halign': 'center',
      'text-margin-y': 6,
      'width': 64,
      'height': 64,
      'shape': 'roundrectangle',
      'text-wrap': 'wrap',
      'text-max-width': 100,
      'background-fit': 'contain',
      'background-clip': 'node',
      'background-image-opacity': 0.9,
      'background-width': '70%',
      'background-height': '70%',
    },
  },
  // Device-type specific colours + icons
  {
    selector: '.node-router',
    style: {
      'background-color': '#1d4ed8',
      'border-color': '#60a5fa',
      'background-image': 'url(/icons/router.svg)',
    },
  },
  {
    selector: '.node-switch',
    style: {
      'background-color': '#065f46',
      'border-color': '#34d399',
      'background-image': 'url(/icons/switch.svg)',
    },
  },
  {
    selector: '.node-firewall',
    style: {
      'background-color': '#7c2d12',
      'border-color': '#fb923c',
      'background-image': 'url(/icons/firewall.svg)',
    },
  },
  {
    selector: '.node-server',
    style: {
      'background-color': '#1e1b4b',
      'border-color': '#a78bfa',
      'background-image': 'url(/icons/server.svg)',
    },
  },
  {
    selector: '.node-host',
    style: {
      'background-color': '#312e81',
      'border-color': '#c4b5fd',
      'background-image': 'url(/icons/host.svg)',
    },
  },
  { selector: '.node-cloud',    style: { 'background-color': '#164e63', 'border-color': '#38bdf8' } },

  // ── Edge base ────────────────────────────────────────────────
  {
    selector: 'edge',
    style: {
      'curve-style': 'bezier',
      'width': 2,
      'label': '',
      'font-size': 10,
      'color': '#94a3b8',
      'text-background-color': '#0f1117',
      'text-background-opacity': 0.8,
      'text-background-padding': 2,
    },
  },
  // GREEN — physically up, no ACLs
  {
    selector: '.edge-up',
    style: {
      'line-color': '#22c55e',
      'target-arrow-color': '#22c55e',
      'line-style': 'solid',
    },
  },
  // BLACK DASHED — admin disabled
  {
    selector: '.edge-disabled',
    style: {
      'line-color': '#64748b',
      'target-arrow-color': '#64748b',
      'line-style': 'dashed',
      'line-dash-pattern': [8, 4],
      'width': 1.5,
      'opacity': 0.6,
    },
  },
  // ORANGE — ACL or firewall policy applied
  {
    selector: '.edge-acl',
    style: {
      'line-color': '#f97316',
      'target-arrow-color': '#f97316',
      'line-style': 'solid',
    },
  },
  // THICK BLUE — trunk link
  {
    selector: '.edge-trunk',
    style: {
      'line-color': '#3b82f6',
      'target-arrow-color': '#3b82f6',
      'line-style': 'solid',
      'width': 5,
    },
  },
  // PURPLE DASHED — BGP session
  {
    selector: '.edge-bgp',
    style: {
      'line-color': '#a855f7',
      'target-arrow-color': '#a855f7',
      'line-style': 'dashed',
      'line-dash-pattern': [6, 3],
      'width': 1.5,
      'opacity': 0.75,
    },
  },

  // ── Path highlight ───────────────────────────────────────────
  {
    selector: '.edge-path',
    style: {
      'line-color': '#facc15',
      'target-arrow-color': '#facc15',
      'width': 6,
      'z-index': 10,
      'opacity': 1,
    },
  },
  {
    selector: '.node-path',
    style: {
      'border-color': '#facc15',
      'border-width': 3,
    },
  },
  {
    selector: '.node-src',
    style: {
      'border-color': '#4ade80',
      'border-width': 4,
      'background-color': '#14532d',
    },
  },
  {
    selector: '.node-dst',
    style: {
      'border-color': '#f87171',
      'border-width': 4,
      'background-color': '#450a0a',
    },
  },

  // Selected node
  {
    selector: 'node:selected',
    style: {
      'border-color': '#f59e0b',
      'border-width': 3,
    },
  },
]

// ─────────────────────────────────────────────────────────────────

export default function TopologyGraph({ elements, pathResult, onNodeClick, onEdgeClick }) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)

  // Initialise Cytoscape once
  useEffect(() => {
    if (!containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: STYLESHEET,
      layout: { name: 'preset' },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      minZoom: 0.1,
      maxZoom: 4,
    })

    cy.on('tap', 'node', evt => {
      onNodeClick?.(evt.target.data())
    })
    cy.on('tap', 'edge', evt => {
      onEdgeClick?.(evt.target.data())
    })
    cy.on('tap', evt => {
      if (evt.target === cy) {
        onNodeClick?.(null)
        onEdgeClick?.(null)
      }
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

    // Run dagre layout
    cy.layout({
      name: 'dagre',
      rankDir: 'TB',
      nodeSep: 40,
      rankSep: 120,
      ranker: 'network-simplex',
      animate: true,
      animationDuration: 400,
    }).run()

  }, [elements])

  // Highlight path without re-running layout
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    // Clear previous highlights
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

    // Fit view to highlighted path
    const pathEls = cy.$('.edge-path, .node-src, .node-dst, .node-path')
    if (pathEls.length) {
      cy.fit(pathEls, 80)
    }
  }, [pathResult])

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', background: '#0f1117' }} />
  )
}
