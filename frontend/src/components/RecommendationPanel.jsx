import { useState } from 'react'
import { effortColor, impactColor, diagMeta } from '../utils/diagnosis'

export default function RecommendationPanel({ recommendations, onClose }) {
  const [expanded, setExpanded] = useState(null)

  if (!recommendations?.length) {
    return (
      <aside style={panelStyle}>
        <PanelHeader onClose={onClose} />
        <div style={{ padding: 24, color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', marginTop: 40 }}>
          No recommendations yet.<br />
          <span style={{ fontSize: 11, marginTop: 8, display: 'block' }}>
            Complete a diagnosis session to see ranked fixes.
          </span>
        </div>
      </aside>
    )
  }

  return (
    <aside style={panelStyle}>
      <PanelHeader onClose={onClose} count={recommendations.length} />

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {recommendations.map((rec, i) => (
          <RecCard
            key={rec.id || i}
            rec={rec}
            expanded={expanded === i}
            onToggle={() => setExpanded(expanded === i ? null : i)}
          />
        ))}
      </div>
    </aside>
  )
}

function PanelHeader({ onClose, count }) {
  return (
    <div style={{
      padding: '20px 16px 16px',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
    }}>
      <div>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>Recommendations</div>
        {count != null && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {count} ranked fix{count !== 1 ? 'es' : ''}
          </div>
        )}
      </div>
      <button onClick={onClose} style={{ color: 'var(--text-muted)', fontSize: 18, lineHeight: 1 }}>×</button>
    </div>
  )
}

function RecCard({ rec, expanded, onToggle }) {
  const effortC = effortColor(rec.effort)
  const impactC = impactColor(rec.impact)

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      overflow: 'hidden',
      background: 'var(--bg-card)',
    }}>
      {/* Header */}
      <div onClick={onToggle} style={{
        padding: '12px 14px',
        cursor: 'pointer',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 8 }}>
          <span style={{
            fontSize: 11, fontWeight: 700,
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
            flexShrink: 0,
            marginTop: 1,
          }}>
            #{rec.rank}
          </span>
          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', lineHeight: 1.4 }}>
            {rec.title}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 8, marginLeft: 22 }}>
          <Badge label={`⚡ ${rec.effort}`} color={effortC} />
          <Badge label={`↑ ${rec.impact}`} color={impactC} />
          <div style={{ marginLeft: 'auto' }}>
            <span style={{
              fontSize: 10,
              color: 'var(--text-muted)',
              transition: 'transform var(--transition)',
              display: 'inline-block',
              transform: expanded ? 'rotate(180deg)' : 'none',
            }}>▾</span>
          </div>
        </div>
      </div>

      {/* Body */}
      {expanded && (
        <div style={{
          padding: '0 14px 14px 14px',
          borderTop: '1px solid var(--border)',
          paddingTop: 12,
        }}>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 12 }}>
            {rec.description}
          </p>

          {rec.code_snippet && (
            <div style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 12px',
              position: 'relative',
            }}>
              <CopyButton text={rec.code_snippet} />
              <pre style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--text-secondary)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                lineHeight: 1.7,
                margin: 0,
              }}>
                {rec.code_snippet}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Badge({ label, color }) {
  return (
    <span style={{
      fontSize: 10,
      fontWeight: 600,
      color,
      background: color + '15',
      border: `1px solid ${color}30`,
      borderRadius: 'var(--radius-sm)',
      padding: '2px 7px',
      textTransform: 'capitalize',
    }}>
      {label}
    </span>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <button onClick={handleCopy} style={{
      position: 'absolute',
      top: 8, right: 8,
      fontSize: 10,
      color: copied ? 'var(--green)' : 'var(--text-muted)',
      padding: '2px 7px',
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-sm)',
      transition: 'color var(--transition)',
    }}>
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  )
}

const panelStyle = {
  width: 320,
  minWidth: 320,
  background: 'var(--bg-surface)',
  borderLeft: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
}
