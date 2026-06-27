import { diagMeta, confColor } from '../utils/diagnosis'

/**
 * SignalTrace — the signature visual element.
 * Each query appears as a horizontal bar that fills with color as it's diagnosed.
 * Looks like an EKG trace for your RAG pipeline.
 */
export default function SignalTrace({ queries, liveEvents, total }) {
  const allItems = buildItems(queries, liveEvents, total)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {allItems.map((item, i) => (
        <TraceBar key={i} item={item} index={i} />
      ))}
    </div>
  )
}

function TraceBar({ item, index }) {
  const meta = item.diagnosis ? diagMeta(item.diagnosis) : null
  const isLive = item.state === 'live'
  const isPending = item.state === 'pending'

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      {/* Index */}
      <div style={{
        width: 24,
        textAlign: 'right',
        fontSize: 10,
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-muted)',
        flexShrink: 0,
      }}>
        {index + 1}
      </div>

      {/* Bar */}
      <div style={{
        flex: 1,
        height: 28,
        background: 'var(--bg-card)',
        borderRadius: 'var(--radius-sm)',
        overflow: 'hidden',
        position: 'relative',
        border: `1px solid ${meta ? meta.color + '40' : 'var(--border)'}`,
      }}>
        {/* Fill */}
        {!isPending && (
          <div style={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: '100%',
            width: isLive ? '60%' : '100%',
            background: meta ? `${meta.color}20` : 'var(--bg-hover)',
            transition: 'width 0.8s ease',
            animation: isLive ? 'pulse 1.5s ease-in-out infinite' : 'none',
          }} />
        )}

        {/* Query text */}
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          padding: '0 10px',
          gap: 8,
        }}>
          {isLive && <LiveDot />}
          <span style={{
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            color: isPending ? 'var(--text-muted)' : 'var(--text-secondary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
          }}>
            {item.query || `Query ${index + 1}`}
          </span>

          {meta && !isLive && (
            <span style={{
              fontSize: 10,
              fontWeight: 700,
              color: meta.color,
              fontFamily: 'var(--font-mono)',
              letterSpacing: '0.5px',
              flexShrink: 0,
            }}>
              {meta.short}
            </span>
          )}

          {item.confidence != null && !isLive && (
            <span style={{
              fontSize: 10,
              fontFamily: 'var(--font-mono)',
              color: confColor(item.confidence),
              flexShrink: 0,
            }}>
              {Math.round(item.confidence * 100)}%
            </span>
          )}

          {isPending && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              waiting
            </span>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.5; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}

function LiveDot() {
  return (
    <div style={{ position: 'relative', width: 8, height: 8, flexShrink: 0 }}>
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'var(--yellow)',
        borderRadius: '50%',
        animation: 'livePulse 1s ease-in-out infinite',
      }} />
      <style>{`
        @keyframes livePulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.5); opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}

function buildItems(queries, liveEvents, total) {
  const items = []
  const diagnosed = new Set()

  // Fill from completed query diagnoses
  if (queries?.length) {
    for (const q of queries) {
      items.push({
        state: 'done',
        query: q.query_text,
        diagnosis: q.final_diagnosis,
        confidence: q.confidence_score,
      })
      diagnosed.add(items.length - 1)
    }
  }

  // Add live event if currently diagnosing
  if (liveEvents?.length) {
    const latest = liveEvents[liveEvents.length - 1]
    if (!diagnosed.has(latest.query_index)) {
      items.push({
        state: 'live',
        query: latest.query_text,
        diagnosis: null,
        confidence: null,
      })
    }
  }

  // Pad with pending slots
  const current = items.length
  const needed = total || current
  for (let i = current; i < needed; i++) {
    items.push({ state: 'pending', query: null, diagnosis: null, confidence: null })
  }

  return items
}
