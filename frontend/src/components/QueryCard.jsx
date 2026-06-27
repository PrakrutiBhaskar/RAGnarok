import { useState } from 'react'
import { diagMeta, confColor, VERDICT_META } from '../utils/diagnosis'

export default function QueryCard({ query, index }) {
  const [expanded, setExpanded] = useState(false)
  const meta = diagMeta(query.final_diagnosis)
  const conf = query.confidence_score

  return (
    <div style={{
      border: `1px solid var(--border)`,
      borderRadius: 'var(--radius)',
      overflow: 'hidden',
      transition: 'border-color var(--transition)',
    }}
      onMouseOver={e => e.currentTarget.style.borderColor = meta.color + '60'}
      onMouseOut={e => e.currentTarget.style.borderColor = 'var(--border)'}
    >
      {/* Header row */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          padding: '12px 16px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          background: 'var(--bg-card)',
        }}
      >
        {/* Index */}
        <span style={{
          width: 24, height: 24,
          background: meta.color + '20',
          border: `1px solid ${meta.color}`,
          borderRadius: 'var(--radius-sm)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 700,
          color: meta.color,
          flexShrink: 0,
        }}>
          {index + 1}
        </span>

        {/* Query text */}
        <span style={{
          flex: 1,
          fontSize: 13,
          color: 'var(--text-primary)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {query.query_text}
        </span>

        {/* Verdict pills */}
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <VerdictPill label={query.retrieval_verdict} />
          <VerdictPill label={query.generation_verdict} />
        </div>

        {/* Diagnosis */}
        <span style={{
          fontSize: 11, fontWeight: 700,
          color: meta.color,
          fontFamily: 'var(--font-mono)',
          letterSpacing: '0.3px',
          flexShrink: 0,
          minWidth: 60,
          textAlign: 'right',
        }}>
          {meta.short}
        </span>

        {/* Confidence */}
        <span style={{
          fontSize: 11, fontFamily: 'var(--font-mono)',
          color: confColor(conf),
          flexShrink: 0,
          minWidth: 36,
          textAlign: 'right',
        }}>
          {Math.round(conf * 100)}%
        </span>

        {/* Expand arrow */}
        <span style={{
          color: 'var(--text-muted)',
          fontSize: 12,
          transition: 'transform var(--transition)',
          transform: expanded ? 'rotate(180deg)' : 'none',
          flexShrink: 0,
        }}>▾</span>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div style={{
          padding: '16px',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          background: 'var(--bg-surface)',
        }}>
          {/* Diagnosis badge */}
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 12px',
            background: meta.color + '15',
            border: `1px solid ${meta.color}`,
            borderRadius: 'var(--radius)',
            width: 'fit-content',
          }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: meta.color }}>{meta.label}</span>
            <span style={{ fontSize: 11, color: confColor(conf), fontFamily: 'var(--font-mono)' }}>
              {Math.round(conf * 100)}% confidence
            </span>
          </div>

          {/* Q&A comparison */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {query.expected_answer && (
              <TextBox label="Expected Answer" text={query.expected_answer} accent="var(--green)" />
            )}
            {query.actual_answer && (
              <TextBox label="Actual Answer" text={query.actual_answer} accent="var(--red)" />
            )}
          </div>

          {/* Metrics row */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
            gap: 10,
          }}>
            {query.max_cosine_similarity != null && (
              <Metric label="Max Cosine Sim" value={query.max_cosine_similarity.toFixed(4)} />
            )}
            {query.avg_cosine_similarity != null && (
              <Metric label="Avg Cosine Sim" value={query.avg_cosine_similarity.toFixed(4)} />
            )}
            {query.bm25_score != null && (
              <Metric label="BM25 Oracle Score" value={query.bm25_score.toFixed(4)} />
            )}
            {query.expected_answer_in_corpus != null && (
              <Metric
                label="Answer in Corpus"
                value={query.expected_answer_in_corpus ? 'Yes' : 'No'}
                valueColor={query.expected_answer_in_corpus ? 'var(--green)' : 'var(--red)'}
              />
            )}
          </div>

          {/* Retrieved chunks */}
          {query.retrieved_chunks?.length > 0 && (
            <ChunkList label="Retrieved Chunks" chunks={query.retrieved_chunks} accent="var(--blue)" />
          )}

          {/* Oracle chunks */}
          {query.oracle_chunks?.length > 0 && (
            <ChunkList label="BM25 Oracle Chunks" chunks={query.oracle_chunks} accent="var(--green)" />
          )}
        </div>
      )}
    </div>
  )
}

function VerdictPill({ label }) {
  const meta = VERDICT_META[label] || { color: '#4A5066' }
  const short = label?.replace('RETRIEVAL_', 'R:').replace('GENERATION_', 'G:') || '?'
  return (
    <span style={{
      fontSize: 10,
      fontFamily: 'var(--font-mono)',
      fontWeight: 600,
      color: meta.color,
      background: meta.color + '15',
      padding: '2px 6px',
      borderRadius: 'var(--radius-sm)',
      border: `1px solid ${meta.color}30`,
    }}>
      {short}
    </span>
  )
}

function TextBox({ label, text, accent }) {
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: `1px solid ${accent}30`,
      borderRadius: 'var(--radius)',
      padding: '10px 12px',
    }}>
      <div style={{ fontSize: 10, fontWeight: 600, color: accent, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
        {text.slice(0, 300)}{text.length > 300 ? '…' : ''}
      </div>
    </div>
  )
}

function Metric({ label, value, valueColor }) {
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '8px 12px',
    }}>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      <div style={{
        fontSize: 14,
        fontFamily: 'var(--font-mono)',
        fontWeight: 600,
        color: valueColor || 'var(--text-primary)',
      }}>
        {value}
      </div>
    </div>
  )
}

function ChunkList({ label, chunks, accent }) {
  const [show, setShow] = useState(false)
  return (
    <div>
      <button onClick={() => setShow(v => !v)} style={{
        fontSize: 11, color: accent, fontFamily: 'var(--font-mono)',
        marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <span style={{ transform: show ? 'rotate(90deg)' : 'none', display: 'inline-block', transition: 'transform var(--transition)' }}>▶</span>
        {label} ({chunks.length})
      </button>
      {show && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {chunks.slice(0, 5).map((c, i) => (
            <div key={i} style={{
              background: 'var(--bg-card)',
              border: `1px solid ${accent}20`,
              borderRadius: 'var(--radius-sm)',
              padding: '8px 12px',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                  {c.chunk_id?.slice(0, 20) || `chunk_${i}`}
                </span>
                {(c.cosine_similarity != null || c.bm25_score != null) && (
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: accent }}>
                    {c.cosine_similarity != null ? `cos: ${c.cosine_similarity.toFixed(3)}` : `bm25: ${c.bm25_score?.toFixed(3)}`}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {c.text?.slice(0, 200)}{c.text?.length > 200 ? '…' : ''}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
