/**
 * TreasureMap — API client
 * All calls go through Vite's /api proxy → http://localhost:8000
 */

const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${options.method || 'GET'} ${path} → ${res.status}: ${text}`)
  }
  return res.json()
}

export const api = {
  health:        ()          => request('/health'),
  topology:      ()          => request('/topology'),
  topologySummary: ()        => request('/topology/summary'),
  devices:       (params)    => request('/devices?' + new URLSearchParams(params || {})),
  device:        (name)      => request(`/devices/${encodeURIComponent(name)}`),
  deviceIfaces:  (name)      => request(`/devices/${encodeURIComponent(name)}/interfaces`),
  deviceAcls:    (name)      => request(`/devices/${encodeURIComponent(name)}/acls`),
  deviceConns:   (name)      => request(`/devices/${encodeURIComponent(name)}/connections`),
  pathfind:      (req)       => request('/pathfind', { method: 'POST', body: JSON.stringify(req) }),
  searchNodes:   (q)         => request(`/pathfind/search?q=${encodeURIComponent(q)}`),
}
