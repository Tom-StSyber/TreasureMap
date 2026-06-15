/**
 * TreasureMap — Textual topology overview panel.
 * Shows a sortable, filterable table of devices and links.
 * Also displays the topology summary counters.
 */
import { useState, useMemo } from 'react'

const S = {
  panel: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', padding: 16, fontSize: 13, color: '#cbd5e1' },
  title: { fontSize: 14, fontWeight: 700, color: '#f1f5f9', marginBottom: 10 },
  summaryGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 },
  summaryCard: { background: '#1e293b', borderRadius: 6, padding: '8px 12px', textAlign: 'center' },
  summaryNum: { fontSize: 22, fontWeight: 700, color: '#f1f5f9' },
  summaryLabel: { fontSize: 11, color: '#64748b', marginTop: 2 },
  tabBar: { display: 'flex', gap: 4, marginBottom: 8 },
  tab: (active) => ({
    padding: '5px 14px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
    background: active ? '#3b82f6' : '#1e293b',
    color: active ? '#fff' : '#64748b',
  }),
  searchInput: {
    width: '100%', padding: '6px 10px', marginBottom: 8, borderRadius: 6,
    background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', fontSize: 12, outline: 'none',
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 12 },
  th: { textAlign: 'left', padding: '6px 8px', color: '#64748b', borderBottom: '1px solid #1e293b', cursor: 'pointer', userSelect: 'none' },
  td: { padding: '6px 8px', borderBottom: '1px solid #0f1117', verticalAlign: 'middle' },
  dot: (color) => ({ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: color, marginRight: 5 }),
  overflow: { overflowY: 'auto', flex: 1 },
}

const STATUS_DOT = { up: '#22c55e', down: '#ef4444', disabled: '#64748b' }
const LINK_COLOR = { 'edge-up': '#22c55e', 'edge-disabled': '#64748b', 'edge-acl': '#f97316', 'edge-trunk': '#3b82f6' }
const LINK_LABEL = { 'edge-up': 'Up', 'edge-disabled': 'Disabled', 'edge-acl': 'ACL/FW', 'edge-trunk': 'Trunk' }

function edgeClass(c) {
  if (c.status === 'disabled') return 'edge-disabled'
  if (c.has_acl || c.has_firewall) return 'edge-acl'
  if (c.link_type === 'trunk') return 'edge-trunk'
  return 'edge-up'
}

function SummaryCard({ num, label, color }) {
  return (
    <div style={S.summaryCard}>
      <div style={{ ...S.summaryNum, color: color || '#f1f5f9' }}>{num ?? '—'}</div>
      <div style={S.summaryLabel}>{label}</div>
    </div>
  )
}

export default function TextualView({ summary, nodes, edges }) {
  const [tab, setTab]     = useState('devices')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('label')
  const [sortAsc, setSortAsc] = useState(true)

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(a => !a)
    else { setSortKey(key); setSortAsc(true) }
  }

  const SortTh = ({ k, label }) => (
    <th style={S.th} onClick={() => handleSort(k)}>
      {label} {sortKey === k ? (sortAsc ? '▲' : '▼') : ''}
    </th>
  )

  const devices = useMemo(() => {
    if (!nodes) return []
    return nodes
      .map(n => n.data)
      .filter(d => !search || Object.values(d).some(v => String(v).toLowerCase().includes(search.toLowerCase())))
      .sort((a, b) => {
        const va = String(a[sortKey] || '')
        const vb = String(b[sortKey] || '')
        return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va)
      })
  }, [nodes, search, sortKey, sortAsc])

  const links = useMemo(() => {
    if (!edges) return []
    return edges
      .map(e => ({ ...e.data, cls: e.classes }))
      .filter(e => !search || [e.source, e.target, e.description, e.link_type].some(
        v => String(v || '').toLowerCase().includes(search.toLowerCase())
      ))
      .sort((a, b) => {
        const va = String(a[sortKey] || '')
        const vb = String(b[sortKey] || '')
        return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va)
      })
  }, [edges, search, sortKey, sortAsc])

  return (
    <div style={S.panel}>
      <div style={S.title}>📋 Topology Overview</div>

      {/* Summary counters */}
      {summary && (
        <div style={S.summaryGrid}>
          <SummaryCard num={summary.devices}      label="Devices"           color="#a5b4fc" />
          <SummaryCard num={summary.connections}   label="Links"             color="#94a3b8" />
          <SummaryCard num={summary.links_up}      label="Links Up"          color="#22c55e" />
          <SummaryCard num={summary.links_disabled} label="Disabled"         color="#64748b" />
          <SummaryCard num={summary.links_with_acl} label="ACL / Firewall"   color="#f97316" />
          <SummaryCard num={summary.trunk_links}    label="Trunk Links"      color="#3b82f6" />
        </div>
      )}

      {/* Tab bar */}
      <div style={S.tabBar}>
        <button style={S.tab(tab === 'devices')} onClick={() => setTab('devices')}>
          Devices ({nodes?.length || 0})
        </button>
        <button style={S.tab(tab === 'links')} onClick={() => setTab('links')}>
          Links ({edges?.length || 0})
        </button>
      </div>

      {/* Search */}
      <input
        style={S.searchInput}
        placeholder={`Filter ${tab}…`}
        value={search}
        onChange={e => setSearch(e.target.value)}
      />

      {/* Table */}
      <div style={S.overflow}>
        {tab === 'devices' && (
          <table style={S.table}>
            <thead>
              <tr>
                <SortTh k="label"         label="Name" />
                <SortTh k="device_type"   label="Type" />
                <SortTh k="vendor"        label="Vendor" />
                <SortTh k="management_ip" label="Mgmt IP" />
                <SortTh k="location"      label="Location" />
              </tr>
            </thead>
            <tbody>
              {devices.map(d => (
                <tr key={d.id} style={{ cursor: 'default' }}>
                  <td style={{ ...S.td, fontWeight: 600, color: '#e2e8f0' }}>{d.label}</td>
                  <td style={S.td}><span style={{ color: '#a5b4fc' }}>{d.device_type}</span></td>
                  <td style={S.td}>{d.vendor}</td>
                  <td style={{ ...S.td, fontFamily: 'monospace', color: '#7dd3fc' }}>{d.management_ip}</td>
                  <td style={S.td}>{d.location}</td>
                </tr>
              ))}
              {devices.length === 0 && (
                <tr><td colSpan={5} style={{ ...S.td, color: '#475569', textAlign: 'center' }}>No results</td></tr>
              )}
            </tbody>
          </table>
        )}

        {tab === 'links' && (
          <table style={S.table}>
            <thead>
              <tr>
                <SortTh k="source"      label="Source" />
                <SortTh k="target"      label="Target" />
                <SortTh k="status"      label="Status" />
                <SortTh k="link_type"   label="Type" />
                <th style={S.th}>Bw</th>
                <th style={S.th}>Flags</th>
              </tr>
            </thead>
            <tbody>
              {links.map(l => {
                const cls = edgeClass(l)
                const color = LINK_COLOR[cls]
                return (
                  <tr key={l.id}>
                    <td style={{ ...S.td, color: '#e2e8f0' }}>{l.source}<br /><span style={{ color: '#475569', fontSize: 11 }}>{l.src_interface}</span></td>
                    <td style={{ ...S.td, color: '#e2e8f0' }}>{l.target}<br /><span style={{ color: '#475569', fontSize: 11 }}>{l.dst_interface}</span></td>
                    <td style={S.td}>
                      <span style={S.dot(STATUS_DOT[l.status] || '#64748b')} />
                      {l.status}
                    </td>
                    <td style={{ ...S.td, color }}>
                      {LINK_LABEL[cls] || l.link_type}
                    </td>
                    <td style={{ ...S.td, fontFamily: 'monospace', fontSize: 11 }}>
                      {l.bandwidth_mbps ? `${l.bandwidth_mbps >= 1000 ? l.bandwidth_mbps / 1000 + 'G' : l.bandwidth_mbps + 'M'}` : ''}
                    </td>
                    <td style={S.td}>
                      {l.has_acl       && <span style={{ color: '#f97316', fontSize: 11 }}>ACL </span>}
                      {l.has_firewall  && <span style={{ color: '#ef4444', fontSize: 11 }}>FW </span>}
                    </td>
                  </tr>
                )
              })}
              {links.length === 0 && (
                <tr><td colSpan={6} style={{ ...S.td, color: '#475569', textAlign: 'center' }}>No results</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
