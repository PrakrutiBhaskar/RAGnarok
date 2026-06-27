/**
 * ArcGauge — the signature radial arc for failure distribution.
 * Each arc segment represents a failure type, sized by query count.
 */
export function FailureArc({ distribution, total }) {
  if (!distribution || total === 0) return null

  const COLORS = {
    retrieval_failure:     '#FFB547',
    generation_failure:    '#A855F7',
    compound_failure:      '#FF4D6D',
    data_quality_failure:  '#4D9FFF',
    no_failure_detected:   '#00E5A0',
    insufficient_evidence: '#4A5066',
  }
  const LABELS = {
    retrieval_failure:     'Retrieval',
    generation_failure:    'Generation',
    compound_failure:      'Compound',
    data_quality_failure:  'Data Quality',
    no_failure_detected:   'No Failure',
    insufficient_evidence: 'Unknown',
  }

  const entries = Object.entries(distribution).filter(([, v]) => v > 0)
  const cx = 80, cy = 80, r = 60, stroke = 14
  const circumference = 2 * Math.PI * r
  const gap = 4

  // Build arc segments
  let offset = 0
  const segments = entries.map(([key, count]) => {
    const fraction = count / total
    const arcLen = fraction * circumference - gap
    const seg = { key, count, fraction, arcLen, offset, color: COLORS[key] || '#4A5066' }
    offset += fraction * circumference
    return seg
  })

  // Dominant failure
  const dominant = entries.sort((a, b) => b[1] - a[1])[0]

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
      {/* SVG Arc */}
      <div style={{ position: 'relative', width: 160, height: 160, flexShrink: 0 }}>
        <svg width="160" height="160" viewBox="0 0 160 160">
          {/* Background ring */}
          <circle
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke="var(--bg-card)"
            strokeWidth={stroke}
          />
          {/* Segments */}
          {segments.map(seg => (
            <circle
              key={seg.key}
              cx={cx} cy={cy} r={r}
              fill="none"
              stroke={seg.color}
              strokeWidth={stroke}
              strokeDasharray={`${Math.max(0, seg.arcLen)} ${circumference}`}
              strokeDashoffset={-seg.offset}
              strokeLinecap="round"
              style={{ transform: 'rotate(-90deg)', transformOrigin: `${cx}px ${cy}px` }}
            />
          ))}
          {/* Center label */}
          <text x={cx} y={cy - 8} textAnchor="middle" fill="var(--text-primary)"
            fontFamily="var(--font-mono)" fontSize="22" fontWeight="700">
            {total}
          </text>
          <text x={cx} y={cy + 10} textAnchor="middle" fill="var(--text-muted)"
            fontFamily="var(--font-ui)" fontSize="11">
            queries
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {segments.map(seg => (
          <div key={seg.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 10, height: 10,
              borderRadius: '50%',
              background: seg.color,
              flexShrink: 0,
            }} />
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              {LABELS[seg.key] || seg.key}
            </span>
            <span style={{
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              color: seg.color,
              fontWeight: 600,
              marginLeft: 'auto',
              paddingLeft: 12,
            }}>
              {seg.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ConfidenceBar({ score }) {
  const color = score >= 0.75 ? '#00E5A0' : score >= 0.5 ? '#FFB547' : '#FF4D6D'
  const label = score >= 0.75 ? 'High' : score >= 0.5 ? 'Medium' : 'Low'

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Overall Confidence</span>
        <span style={{ fontSize: 13, fontFamily: 'var(--font-mono)', fontWeight: 600, color }}>
          {Math.round(score * 100)}% <span style={{ fontWeight: 400, fontSize: 11 }}>{label}</span>
        </span>
      </div>
      <div style={{
        height: 6,
        background: 'var(--bg-card)',
        borderRadius: 3,
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${score * 100}%`,
          background: `linear-gradient(90deg, ${color}88, ${color})`,
          borderRadius: 3,
          transition: 'width 1s ease',
        }} />
      </div>
    </div>
  )
}
