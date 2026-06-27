import { useState, useEffect, useCallback } from 'react'
import Sidebar from './components/Sidebar'
import SessionView from './pages/SessionView'
import EmptyState from './pages/EmptyState'
import NewSessionModal from './components/NewSessionModal'
import { api } from './api/client'

export default function App() {
  const [sessions, setSessions] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [showNew, setShowNew] = useState(false)
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [apiOnline, setApiOnline] = useState(null)

  // Check API health
  useEffect(() => {
    api.health()
      .then(() => setApiOnline(true))
      .catch(() => setApiOnline(false))
  }, [])

  // Load sessions
  const loadSessions = useCallback(async () => {
    try {
      const list = await api.listSessions()
      setSessions(list)
      setLoadingSessions(false)
    } catch {
      setLoadingSessions(false)
    }
  }, [])

  useEffect(() => {
    loadSessions()
    // Poll for running sessions every 3s
    const interval = setInterval(() => {
      const hasRunning = sessions.some(s => s.status === 'running' || s.status === 'pending')
      if (hasRunning) loadSessions()
    }, 3000)
    return () => clearInterval(interval)
  }, [loadSessions, sessions])

  function handleSessionCreated(id) {
    setActiveId(id)
    loadSessions()
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* API offline banner */}
      {apiOnline === false && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0,
          background: 'var(--red)',
          color: '#fff',
          fontSize: 12,
          textAlign: 'center',
          padding: '6px',
          zIndex: 200,
          fontFamily: 'var(--font-mono)',
        }}>
          ⚠ API server offline — run{' '}
          <code style={{ background: 'rgba(0,0,0,0.3)', padding: '1px 6px', borderRadius: 3 }}>
            rag-debug serve
          </code>
          {' '}to connect
        </div>
      )}

      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={() => setShowNew(true)}
        loading={loadingSessions}
      />

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {activeId ? (
          <SessionView key={activeId} sessionId={activeId} />
        ) : (
          <EmptyState onNew={() => setShowNew(true)} />
        )}
      </main>

      {showNew && (
        <NewSessionModal
          onClose={() => setShowNew(false)}
          onCreated={handleSessionCreated}
        />
      )}
    </div>
  )
}
