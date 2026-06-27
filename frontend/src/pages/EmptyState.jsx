export default function EmptyState({ onNew }) {
  return (
    <div style={{
      flex: 1,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexDirection: 'column',
      gap: 0,
      padding: 40,
    }}>
      {/* Signal trace illustration */}
      <svg width="280" height="80" viewBox="0 0 280 80" style={{ marginBottom: 32, opacity: 0.4 }}>
        <polyline
          points="0,40 30,40 45,15 60,60 75,25 90,55 105,35 120,40 150,40 165,20 180,55 195,30 210,45 240,40 280,40"
          fill="none"
          stroke="#FF4D6D"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="210" cy="45" r="4" fill="#FF4D6D" opacity="0.8" />
      </svg>

      <h2 style={{
        fontSize: 22,
        fontWeight: 700,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '-0.5px',
        marginBottom: 10,
        color: 'var(--text-primary)',
      }}>
        RAGnarok
      </h2>

      <p style={{
        fontSize: 14,
        color: 'var(--text-secondary)',
        textAlign: 'center',
        maxWidth: 360,
        lineHeight: 1.7,
        marginBottom: 8,
      }}>
        Automated failure attribution for RAG pipelines.
        Diagnoses whether failures are caused by retrieval, generation,
        or data quality — using oracle injection testing.
      </p>

      <p style={{
        fontSize: 12,
        color: 'var(--text-muted)',
        textAlign: 'center',
        maxWidth: 320,
        lineHeight: 1.7,
        marginBottom: 32,
      }}>
        Paste your pipeline config + failing queries.<br />
        Get ranked, actionable fixes in seconds.
      </p>

      <button onClick={onNew} style={{
        padding: '10px 24px',
        background: 'var(--red)',
        color: '#fff',
        borderRadius: 'var(--radius)',
        fontSize: 14,
        fontWeight: 600,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        transition: 'opacity 150ms ease',
        boxShadow: '0 0 24px var(--red-glow)',
      }}
        onMouseOver={e => e.currentTarget.style.opacity = '0.85'}
        onMouseOut={e => e.currentTarget.style.opacity = '1'}
      >
        + Start First Diagnosis
      </button>

      {/* How it works */}
      <div style={{
        marginTop: 56,
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 20,
        maxWidth: 600,
        width: '100%',
      }}>
        {[
          { icon: '🔍', title: 'Retrieval Layer', desc: 'Cosine similarity scoring with per-model thresholds' },
          { icon: '⚗️', title: 'Oracle Injection', desc: 'BM25 oracle proves if retrieval or generation is at fault' },
          { icon: '🎯', title: 'Ranked Fixes', desc: 'Actionable recommendations sorted by impact/effort ratio' },
        ].map(card => (
          <div key={card.title} style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: '16px',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 22, marginBottom: 8 }}>{card.icon}</div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>{card.title}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6 }}>{card.desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
