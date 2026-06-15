/**
 * TreasureMap — Device / edge detail panel (right sidebar).
 * Shows device metadata, interfaces, and ACLs when a node is selected.
 * Shows link metadata when an edge is selected.
 */
import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

const S = {
  panel: {
    display: 'flex', flexDirection: 'column', gap: 12,
    padding: 16, overflowY: 'auto', height: '100%',
    fontSize: 13, color: '#cbd5e1',
  },
  heading: { fontSize: 15, fontWeight: 700, color: '#f1f5f9', marginBottom: 4 },
  subheading: { fontSize: 12, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 1, marginTop: 10, marginBottom: 4 },
  kv: { display: 'flex', gap: 8, marginBottom: 2 },
  key: { color: '#64748b', minWidth: 110 },
  val: { color: '#e2e8f0', wordBreak: 'break-all' },
  chip: {
    display: 'inline-block', padding: '2px 8px', borderRadius: 999,
    fontSize: 11, fontWeight: 600, marginRight: 4, marginBottom: 2,
  },
  ifaceRow: {
    padding: '6px 8px', marginBottom: 4, borderRadius: 4,
    background: '#1e293b', borderLeft: '3px solid #334155',
  },
  aclRow: { padding: '6px 8px', marginBottom: 4, borderRadius: 4, background: '#1e293b' },
  ruleRow: { padding: '3px 0', borderBottom: '1px solid #1e293b', fontSize: 12 },
  empty: { color: '#475569', fontStyle: 'italic', fontSize: 12 },
}

const STATUS_COLOR = { up: '#22c55e', down: '#ef4444', disabled: '#64748b' }
const LINK_COLOR   = { 'edge-up': '#22c55e', 'edge-disabled': '#64748b', 'edge-acl': '#f97316', 'edge-trunk': '#3b82f6' }
const LINK_LABEL   = { 'edge-up': 'Up (clean)', 'edge-disabled': 'Disabled', 'edge-acl': 'ACL / Firewall', 'edge-trunk': 'Trunk' }

function KV({ k, v }) {
  if (v == null || v === '') return null
  return (
    <div style={S.kv}>
      <span style={S.key}>{k}</span>
      <span style={S.val}>{String(v)}</span>
    </div>
  )
}

function Chip({ label, color }) {
  return <span style={{ ...S.chip, background: color + '22', color, border: `1px solid ${color}55` }}>{label}</span>
}

// ─── Edge detail ─────────────────────────────────────────────────
function EdgeDetail({ data }) {
  const cls = data.classes || ''
  const color = LINK_COLOR[cls] || '#94a3b8'
  const typeLabel = LINK_LABEL[cls] || data.link_type

  return (
    <div style={S.panel}>
      <div style={S.heading}>Link Detail</div>
      <Chip label={typeLabel} color={color} />
      <KV k="Source"      v={`${data.source} : ${data.src_interface}`} />
      <KV k="Target"      v={`${data.target} : ${data.dst_interface}`} />
      <KV k="Status"      v={data.status} />
      <KV k="Link type"   v={data.link_type} />
      <KV k="Bandwidth"   v={data.bandwidth_mbps ? `${data.bandwidth_mbps} Mbps` : ''} />
      <KV k="Description" v={data.description} />
      {data.has_acl     && <Chip label="ACL applied"      color="#f97316" />}
      {data.has_firewall && <Chip label="Firewall policy"  color="#ef4444" />}
    </div>
  )
}

// ─── Node detail ─────────────────────────────────────────────────
function NodeDetail({ data }) {
  const [ifaces, setIfaces]   = useState([])
  const [acls,   setAcls]     = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!data?.id) return
    setLoading(true)
    Promise.all([
      api.deviceIfaces(data.id).catch(() => []),
      api.deviceAcls(data.id).catch(() => []),
    ]).then(([i, a]) => {
      setIfaces(i)
      setAcls(a)
    }).finally(() => setLoading(false))
  }, [data?.id])

  if (!data) return <div style={{ ...S.panel, ...S.empty }}>Select a device or link to see details.</div>

  const statusColor = STATUS_COLOR['up'] // devices don't have a top-level status
  return (
    <div style={S.panel}>
      <div style={S.heading}>{data.label}</div>
      <div style={{ color: '#94a3b8', marginBottom: 4 }}>{data.device_type?.toUpperCase()} · {data.vendor}</div>

      <KV k="Hostname"    v={data.hostname} />
      <KV k="Mgmt IP"     v={data.management_ip} />
      <KV k="Model"       v={data.model} />
      <KV k="OS"          v={data.os} />
      <KV k="Location"    v={data.location} />
      {(data.tags || []).map(t => <Chip key={t} label={t} color="#6366f1" />)}

      {loading && <div style={S.empty}>Loading …</div>}

      {/* Interfaces */}
      {ifaces.length > 0 && (
        <>
          <div style={S.subheading}>Interfaces ({ifaces.length})</div>
          {ifaces.map(iface => (
            <div key={iface.id} style={{
              ...S.ifaceRow,
              borderLeftColor: STATUS_COLOR[iface.admin_status] || '#475569',
            }}>
              <div style={{ fontWeight: 600, color: '#e2e8f0' }}>{iface.name}</div>
              {iface.description && <div style={{ color: '#64748b', fontSize: 11 }}>{iface.description}</div>}
              {iface.ip_address && (
                <div style={{ color: '#a5b4fc', fontSize: 11 }}>{iface.ip_address}/{iface.prefix_length}</div>
              )}
              <div style={{ marginTop: 2 }}>
                <Chip label={iface.admin_status} color={STATUS_COLOR[iface.admin_status] || '#64748b'} />
                {iface.vlan_mode !== 'none' && <Chip label={iface.vlan_mode} color="#0891b2" />}
                {iface.vlan_id && <Chip label={`VLAN ${iface.vlan_id}`} color="#0e7490" />}
                {iface.trunk_vlans?.length > 0 && (
                  <Chip label={`Trunk: ${iface.trunk_vlans.join(',')}`} color="#0369a1" />
                )}
                {iface.acl_in  && <Chip label={`ACL-in: ${iface.acl_in}`}   color="#f97316" />}
                {iface.acl_out && <Chip label={`ACL-out: ${iface.acl_out}`} color="#ea580c" />}
                {iface.firewall_policy && <Chip label={`FW: ${iface.firewall_policy}`} color="#dc2626" />}
              </div>
            </div>
          ))}
        </>
      )}

      {/* ACLs */}
      {acls.length > 0 && (
        <>
          <div style={S.subheading}>ACLs ({acls.length})</div>
          {acls.map(acl => (
            <div key={acl.id} style={S.aclRow}>
              <div style={{ fontWeight: 600, color: '#fb923c', marginBottom: 4 }}>{acl.name}</div>
              {(acl.rules || []).map(rule => (
                <div key={rule.sequence} style={S.ruleRow}>
                  <span style={{ color: '#64748b', marginRight: 6 }}>{rule.sequence}</span>
                  <span style={{ color: rule.action === 'permit' ? '#22c55e' : '#ef4444', fontWeight: 600, marginRight: 6 }}>
                    {rule.action.toUpperCase()}
                  </span>
                  <span style={{ color: '#94a3b8' }}>
                    {rule.protocol.toUpperCase()}
                    {rule.src_network !== 'any' ? ` src:${rule.src_network}` : ''}
                    {rule.dst_network !== 'any' ? ` dst:${rule.dst_network}` : ''}
                    {rule.dst_port ? `:${rule.dst_port}` : ''}
                  </span>
                  {rule.description && (
                    <span style={{ color: '#475569', marginLeft: 6, fontSize: 11 }}>— {rule.description}</span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </>
      )}
    </div>
  )
}

// ─── Export ──────────────────────────────────────────────────────
export default function DeviceDetails({ selectedNode, selectedEdge }) {
  if (selectedEdge) return <EdgeDetail data={selectedEdge} />
  if (selectedNode) return <NodeDetail data={selectedNode} />
  return (
    <div style={{ ...S.panel, justifyContent: 'center', alignItems: 'center', opacity: 0.4 }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>🗺</div>
        <div>Click a device or link<br />to see details</div>
      </div>
    </div>
  )
}
