import { useEffect, useRef } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';

cytoscape.use(dagre);

const STYLESHEET = [
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      'background-color': 'data(color)',
      color: '#e2e8f0',
      'font-size': 9,
      'text-valign': 'bottom',
      'text-margin-y': 4,
      'text-outline-color': '#0f1117',
      'text-outline-width': 2,
      width: 'data(size)',
      height: 'data(size)',
      'border-width': 2,
      'border-color': '#0f1117',
    },
  },
  {
    selector: 'node.stub',
    style: { opacity: 0.55 },
  },
  {
    selector: 'node:selected',
    style: {
      'border-color': '#ffffff',
      'border-width': 3,
      'text-outline-color': '#1e3a5f',
    },
  },
  {
    selector: 'node.faded',
    style: { opacity: 0.12 },
  },
  // Edges
  {
    selector: 'edge',
    style: {
      width: 1.5,
      'line-color': 'data(color)',
      'curve-style': 'bezier',
      opacity: 0.7,
      'target-arrow-shape': 'none',
    },
  },
  {
    selector: 'edge[link_type="bgp"]',
    style: {
      'line-style': 'dashed',
      'line-dash-pattern': [6, 3],
      width: 2,
    },
  },
  {
    selector: 'edge:selected',
    style: { opacity: 1, width: 3 },
  },
  {
    selector: 'edge.faded',
    style: { opacity: 0.05 },
  },
];

const LAYOUTS = {
  dagre: {
    name: 'dagre',
    rankDir: 'TB',
    nodeSep: 60,
    rankSep: 120,
    animate: true,
    animationDuration: 400,
  },
  cose: {
    name: 'cose',
    idealEdgeLength: 120,
    nodeOverlap: 20,
    animate: true,
    animationDuration: 600,
    fit: true,
  },
  grid: {
    name: 'grid',
    animate: true,
  },
};

export default function TopologyMap({ elements, layout, onNodeClick, onBgClick }) {
  const cyRef = useRef(null);

  // Re-run layout whenever elements or layout choice changes
  useEffect(() => {
    if (!cyRef.current) return;
    cyRef.current.layout(LAYOUTS[layout] || LAYOUTS.dagre).run();
  }, [elements, layout]);

  function handleCy(cy) {
    cyRef.current = cy;

    cy.on('tap', 'node', e => {
      const node = e.target;
      // Highlight connected neighbourhood
      cy.elements().addClass('faded');
      node.removeClass('faded');
      node.connectedEdges().removeClass('faded');
      node.connectedEdges().connectedNodes().removeClass('faded');
      onNodeClick && onNodeClick(node.data());
    });

    cy.on('tap', e => {
      if (e.target === cy) {
        cy.elements().removeClass('faded');
        onBgClick && onBgClick();
      }
    });
  }

  return (
    <CytoscapeComponent
      elements={elements}
      stylesheet={STYLESHEET}
      layout={LAYOUTS[layout] || LAYOUTS.dagre}
      style={{ width: '100%', height: '100%', background: '#0f1117' }}
      cy={handleCy}
      minZoom={0.05}
      maxZoom={5}
    />
  );
}