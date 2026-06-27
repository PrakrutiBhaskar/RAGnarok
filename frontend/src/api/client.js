const BASE = '/v1'

async function req(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail?.message || err.detail || res.statusText)
  }
  return res.json()
}

export const api = {
  // Sessions
  createSession: (body) => req('POST', '/sessions', body),
  listSessions:  ()     => req('GET',  '/sessions'),
  getSession:    (id)   => req('GET',  `/sessions/${id}`),
  deleteSession: (id)   => req('DELETE', `/sessions/${id}`),

  // Reports
  getReport:     (id)   => req('GET', `/sessions/${id}/report`),
  getReportMd:   async (id) => {
    const res = await fetch(`${BASE}/sessions/${id}/report.md`)
    if (!res.ok) throw new Error(res.statusText)
    return res.text()
  },

  // Validate
  validatePipeline: (cfg) => req('POST', '/validate/pipeline', cfg),

  // Health
  health: () => fetch('/health').then(r => r.json()),

  // SSE stream — returns EventSource
  streamSession: (id, { onQuery, onComplete, onError }) => {
    const es = new EventSource(`${BASE}/sessions/${id}/stream`)
    es.addEventListener('query_complete', e => onQuery?.(JSON.parse(e.data)))
    es.addEventListener('session_complete', e => { onComplete?.(JSON.parse(e.data)); es.close() })
    es.addEventListener('error', e => { onError?.(e); es.close() })
    es.onerror = () => { onError?.({ message: 'Stream disconnected' }); es.close() }
    return es
  },
}
