/**
 * TreasureMap — Path search panel.
 *
 * Lets the user specify:
 *   • source device / IP
 *   • destination device / IP / "internet"
 *   • optional: protocol (or service alias like "ssh", "https")
 *   • optional: destination port
 *
 * Then calls POST /pathfind and renders the per-hop results.
 */
import { useState, useCallback, useRef } from 'react'
import { api } from '../api/client.js'

const S = {
  panel: { display: 'flex', flexDirection: 'column', gap: 10, padding: 16, height: '100%', overflowY: 'auto', fontSize: 13 },
  title: { fontSize: 14, fontWeight: 700, color: '#f1f5f9', marginBottom: 4 },
  label: { fontSize: 11, color: '#94a3b8', marginBottom: 3, display: 'block' },
  input: {
    width: '100%', padding: '7px 10px', borderRadius: 6,
    background: '#1e293b', border: '1px solid #334155',
    color: '#e2e8f0', fontSize: 13, outline: 'none',
  },
  row: { display: 'flex', gap: 8 },
  btn: {
    padding: '8px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
    fontWeight: 600, fontSize: 13,
  },
  btnPrimary: { background: '#3b82f6', color: '#fff' },
  btnSecondary: { background: '#1e293b', color: '#94a3b8', border: '1px solid #334155' },
  verdict: (ok) => ({
    padding: '10px 12px', borderRadius: 6, marginTop: 4,
    background: ok === true ? '#052e16' : ok === false ? '#450a0a' : '#1e1b4b',
    border: `1px solid ${ok === true ? '#166534' : ok === false ? '#7f1d1d' : '#312e81'}`,
    color: ok === true ? '#86efac' : ok === false ? '#fca5a5' : '#a5b4fc',
    fontWeight: 600,
  }),
  hopRow: {
    padding: '8px 10px', marginBottom: 4, borderRadius: 4,
    background: '#1e293b', borderLeft: '3px solid #334155',
    fontSize: 12,
  },
  hopNum: { color: '#64748b', marginRight: 6, fontWeight: 700 },
  tag: (color) => ({
    display: 'inline-block', padding: '1px 7px', borderRadius: 999,
    background: color + '22', color, border: `1px solid ${color}44`,
    fontSize: 11, fontWeight: 600, marginLeft: 6,
  }),
  hint: { color: '#475569', fontSize: 11, fontStyle: 'italic' },
  divider: { borderTop: '1px solid #1e293b', margin: '4px 0' },
  suggest: {
    position: 'absolute', zIndex: 100, width: '100%',
    background: '#1e293b', border: '1px solid #334155',
    borderRadius: 6, maxHeight: 180, overflowY: 'auto', top: '100%', left: 0,
  },
  suggestItem: {
    padding: '6px 10px', cursor: 'pointer', color: '#cbd5e1',
    borderBottom: '1px solid #0f1117',
  },
}

const ACL_COLOR = { permit: '#22c55e', deny: '#ef4444', 'no-acl': '#64748b', 'no-acl-data': '#f59e0b' }

function SuggestInput({ value, onChange, placeholder, id }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const timer = useRef(null)

  const handleChange = (e) => {
    const v = e.target.value
    onChange(v)
    clearTimeout(timer.current)
    if (v.length < 2) { setSuggestions([]); setOpen(false); return }
    timer.current = setTimeout(() => {
      api.searchNodes(v).then(res => {
        setSuggestions(res)
        setOpen(res.length > 0)
      }).catch(() => {})
    }, 250)
  }

  const pick = (item) => {
    onChange(item.name)
    setOpen(false)
  }

  return (
    <div style={{ position: 'relative' }}>
      <input
        id={id}
        style={S.input}
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        autoComplete="off"
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onFocus={() => suggestions.length > 0 && setOpen(true)}
      />
      {open && (
        <div style={S.suggest}>
          {suggestions.map(s => (
            <div
              key={s.name}
              style={S.suggestItem}
              onMouseDown={() => pick(s)}
            >
              <span style={{ fontWeight: 600 }}>{s.name}</span>
              <span style={{ color: '#64748b', marginLeft: 8 }}>{s.management_ip}</span>
              <span style={{ color: '#475569', marginLeft: 8, fontSize: 11 }}>{s.device_type}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function PathSearch({ onResult, onClear }) {
  const [src, setSrc]       = useState('')
  const [dst, setDst]       = useState('')
  const [proto, setProto]   = useState('')
  const [port, setPort]     = useState('')
  const [srcIp, setSrcIp]   = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState(null)

  const submit = useCallback(async (e) => {
    e.preventDefault()
    if (!src || !dst) return
    setLoading(true)
    setError(null)
    setResult(null)
    onClear?.()

    const req = {
      source: src,
      destination: dst,
      protocol: proto || undefined,
      dst_port: port ? parseInt(port) : undefined,
      src_ip: srcIp || undefined,
    }

    try {
      const res = await api.pathfind(req)
      setResult(res)
      onResult?.(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [src, dst, proto, port, srcIp, onResult, onClear])

  const clear = () => {
    setResult(null)
    setError(null)
    onClear?.()
  }

  return (
    <div style={S.panel}>
      <div style={S.title}>🔍 Path Query</div>

      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div>
          <label style={S.label} htmlFor="src">Source (device / IP)</label>
          <SuggestInput id="src" value={src} onChange={setSrc} placeholder="jumpbox-01 or 10.10.30.10" />
        </div>
        <div>
          <label style={S.label} htmlFor="dst">Destination (device / IP / "internet")</label>
          <SuggestInput id="dst" value={dst} onChange={setDst} placeholder="server-01 or internet" />
        </div>

        <div style={S.row}>
          <div style={{ flex: 1 }}>
            <label style={S.label} htmlFor="proto">Protocol / Service</label>
            <input
              id="proto"
              style={S.input}
              value={proto}
              onChange={e => setProto(e.target.value)}
              placeholder="ssh · https · tcp · icmp"
            />
          </div>
          <div style={{ width: 90 }}>
            <label style={S.label} htmlFor="port">Dst Port</label>
            <input
              id="port"
              style={S.input}
              value={port}
              onChange={e => setPort(e.target.value)}
              placeholder="22"
              type="number"
              min="1" max="65535"
            />
          </div>
        </div>

        <div>
          <label style={S.label} htmlFor="srcip">Source IP (for ACL evaluation)</label>
          <input
            id="srcip"
            style={S.input}
            value={srcIp}
            onChange={e => setSrcIp(e.target.value)}
            placeholder="Optional — e.g. 10.10.30.10"
          />
        </div>

        <div style={S.row}>
          <button type="submit" style={{ ...S.btn, ...S.btnPrimary, flex: 1 }} disabled={loading}>
            {loading ? 'Searching …' : 'Find Path'}
          </button>
          {(result || error) && (
            <button type="button" style={{ ...S.btn, ...S.btnSecondary }} onClick={clear}>
              Clear
            </button>
          )}
        </div>
      </form>

      {error && (
        <div style={{ color: '#fca5a5', background: '#450a0a', padding: '8px 12px', borderRadius: 6, fontSize: 12 }}>
          ⚠ {error}
        </div>
      )}

      {result && (
        <>
          {/* Verdict banner */}
          <div style={S.verdict(result.authorized)}>
            {result.authorized === true  && '✅ PERMITTED'}
            {result.authorized === false && '🚫 DENIED'}
            {result.authorized === null  && 'ℹ PATH FOUND — no ACL data'}
            {!result.found && '❌ NO PATH'}
          </div>

          <div style={{ color: '#94a3b8', fontSize: 12, lineHeight: 1.5 }}>{result.summary}</div>

          {result.found && (
            <>
              <div style={S.divider} />
              <div style={{ color: '#64748b', fontSize: 11, marginBottom: 4 }}>
                PATH ({result.path?.length || 0} nodes · {result.edges?.length || 0} hops)
              </div>

              {result.hops?.map(hop => (
                <div key={hop.hop} style={{
                  ...S.hopRow,
                  borderLeftColor: hop.acl_result === 'deny' ? '#ef4444'
                                 : hop.acl_result === 'permit' ? '#22c55e'
                                 : '#334155',
                }}>
                  <span style={S.hopNum}>#{hop.hop}</span>
                  <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{hop.device_name}</span>
                  {hop.interface_out && (
                    <span style={{ color: '#64748b', marginLeft: 6 }}>→ {hop.interface_out}</span>
                  )}
                  {hop.acl_result && hop.acl_result !== 'no-acl' && (
                    <span style={S.tag(ACL_COLOR[hop.acl_result] || '#94a3b8')}>
                      {hop.acl_result.toUpperCase()}
                    </span>
                  )}
                  {hop.acl_name && (
                    <div style={{ color: '#f97316', fontSize: 11, marginTop: 2 }}>
                      {hop.acl_name}
                      {hop.acl_rule_seq && <span style={{ color: '#64748b' }}> (seq {hop.acl_rule_seq})</span>}
                    </div>
                  )}
                  {hop.notes && (
                    <div style={{ color: '#64748b', fontSize: 11, marginTop: 1 }}>{hop.notes}</div>
                  )}
                </div>
              ))}
            </>
          )}

          <div style={S.hint}>
            Path highlighted in gold on the graph. Source = green border, destination = red border.
          </div>
        </>
      )}
    </div>
  )
}
