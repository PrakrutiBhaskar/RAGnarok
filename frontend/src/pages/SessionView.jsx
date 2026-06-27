import { useState, useEffect, useRef } from 'react'
import { api } from '../api/client'
import { diagMeta, STATUS_META, confColor } from '../utils/diagnosis'
import SignalTrace from '../components/SignalTrace'
import { FailureArc, ConfidenceBar } from '../components/ArcGauge'
import QueryCard from '../components/QueryCard'
import RecommendationPanel from '../components/RecommendationPanel'

export default function SessionView({ sessionId }) {
  const [report, setReport] = useState(null)
  const [status, setStatus] = useState(null)
  const [liveEvents, setLiveEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showRecs, setShowRecs] = useState(true)
  const [tab, setTab] = useState('trace')
  const esRef = useRef(null)
  const pollRef = useRef(null)

  useEffect(() => {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    setLiveEvents([])
    setReport(null)
    setStatus(null)
    loadSession()
    return () => {
      esRef.current?.close()
      clearInterval(pollRef.current)
    }
  }, [sessionId])

  async function loadSession() {
    try {
      const s = await api.getSession(sessionId)
      setStatus(s)
      if (s.status === 'complete' || s.status === 'partial') {
        await loadReport()
      } else {
        setLoading(false)
        startStream()
        startPolling()
      }
    } catch (e) {
      setError(e.message)
      setLoading(false)
    }
  }

  async function loadReport() {
    try {
      const r = await api.getReport(sessionId)
      setReport(r)
      setStatus(prev => ({ ...prev, status: r.status }))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
      clearInterval(pollRef.current)
    }
  }

  function startStream() {
    esRef.current?.close()
    esRef.current = api.streamSession(sessionId, {
      onQuery: (data) => setLiveEvents(prev => [...prev, data]),
      onComplete: async () => {
        esRef.current?.close()
        clearInterval(pollRef.current)
        await loadReport()
      },
      onError: () => { /* polling will catch it */ },
    })
  }

  function startPolling() {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getSession(sessionId)
        setStatus(s)
        if (s.status === 'complete' || s.status === 'partial') {
          clearInterval(pollRef.current)
          esRef.current?.close()
          await loadReport()
        }
      } catch { /* ignore poll errors */ }
    }, 2000)
  }

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={loadSession} />

  const isRunning = status?.status === 'running' || status?.status === 'pending'
  const queries = report?.query_diagnoses || []
  const recs = report?.recommendations || []
  const summary = report?.summary
  const statusMeta = STATUS_META[status?.status] || STATUS_META.pending

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Top bar */}
        <div style={{
          padding: '16px 24px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 16,
          background: 'var(--bg-surface)', flexShrink: 0,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 3 }}>
              <span style={{
                fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 700,
                color: statusMeta.color, textTransform: 'uppercase', letterSpacing: '0.8px',
                padding: '2px 8px', background: statusMeta.color + '15', borderRadius: 'var(--radius-sm)',
              }}>
                {isRunning && <span style={{ marginRight: 4 }}>◉</span>}
                {statusMeta.label}
              </span>
              <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                {sessionId.slice(0, 8)}…
              </span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              {report?.pipeline_name || 'Diagnosing…'}
              <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>
                {status?.query_count}q · {status?.mode}
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {status?.db_type && <ConfigPill label={status.db_type} />}
            {status?.embedding_provider && <ConfigPill label={status.embedding_provider} />}
            {status?.llm_provider && <ConfigPill label={status.llm_provider} />}
          </div>
          <button onClick={() => setShowRecs(v => !v)} style={{
            padding: '6px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
            fontSize: 12, color: showRecs ? 'var(--text-primary)' : 'var(--text-muted)',
            background: showRecs ? 'var(--bg-hover)' : 'transparent', transition: 'all var(--transition)',
          }}>
            Fixes {recs.length > 0 ? `(${recs.length})` : ''}
          </button>
        </div>

        {/* Summary */}
        {(summary || isRunning) && (
          <div style={{
            padding: '20px 24px', borderBottom: '1px solid var(--border)',
            background: 'var(--bg-surface)', display: 'flex', gap: 32,
            alignItems: 'flex-start', flexShrink: 0,
          }}>
            {summary && (
              <FailureArc distribution={summary.failure_distribution} total={summary.total_queries} />
            )}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
              {summary?.overall_confidence != null && (
                <ConfidenceBar score={summary.overall_confidence} />
              )}
              {summary?.dominant_failure && (
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>Dominant Failure</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    {(() => {
                      const meta = diagMeta(summary.dominant_failure)
                      return (
                        <>
                          <div style={{ width: 10, height: 10, borderRadius: '50%', background: meta.color }} />
                          <span style={{ fontSize: 14, fontWeight: 600, color: meta.color }}>{meta.label}</span>
                        </>
                      )
                    })()}
                  </div>
                </div>
              )}
              {isRunning && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{
                    width: 8, height: 8, borderRadius: '50%', background: 'var(--yellow)',
                    animation: 'pulse 1s ease-in-out infinite',
                  }} />
                  <span style={{ fontSize: 12, color: 'var(--yellow)', fontFamily: 'var(--font-mono)' }}>
                    Diagnosing {liveEvents.length}/{status?.query_count} queries…
                  </span>
                  <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div style={{
          display: 'flex', borderBottom: '1px solid var(--border)',
          padding: '0 24px', background: 'var(--bg-surface)', flexShrink: 0,
        }}>
          {['trace', 'queries'].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: '10px 16px', fontSize: 13, fontWeight: 500,
              color: tab === t ? 'var(--text-primary)' : 'var(--text-muted)',
              borderBottom: `2px solid ${tab === t ? 'var(--red)' : 'transparent'}`,
              marginBottom: -1, textTransform: 'capitalize', transition: 'color var(--transition)',
            }}>
              {t === 'trace' ? '⚡ Signal Trace' : `📋 Query Details (${queries.length})`}
            </button>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {tab === 'trace' ? (
            <SignalTrace queries={queries} liveEvents={liveEvents} total={status?.query_count} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {queries.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', marginTop: 40 }}>
                  {isRunning ? 'Diagnosis in progress…' : 'No queries diagnosed yet.'}
                </div>
              ) : (
                queries.map((q, i) => <QueryCard key={q.id || i} query={q} index={i} />)
              )}
            </div>
          )}
        </div>
      </div>

      {showRecs && (
        <RecommendationPanel recommendations={recs} onClose={() => setShowRecs(false)} />
      )}
    </div>
  )
}

function ConfigPill({ label }) {
  return (
    <span style={{
      fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)',
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-sm)', padding: '3px 8px',
    }}>{label}</span>
  )
}

function LoadingState() {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
        <div style={{ fontSize: 24, marginBottom: 12, animation: 'spin 1s linear infinite' }}>⟳</div>
        <div style={{ fontSize: 13 }}>Loading session…</div>
        <style>{`@keyframes spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }`}</style>
      </div>
    </div>
  )
}

function ErrorState({ message, onRetry }) {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', maxWidth: 360 }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>⚠</div>
        <div style={{ fontSize: 14, color: 'var(--red)', marginBottom: 8 }}>Failed to load session</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>{message}</div>
        <button onClick={onRetry} style={{
          padding: '8px 16px', background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', fontSize: 13, color: 'var(--text-primary)',
        }}>Retry</button>
      </div>
    </div>
  )
}