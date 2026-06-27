import { useState } from 'react'
import { STATUS_META, diagMeta } from '../utils/diagnosis'

export default function Sidebar({ sessions, activeId, onSelect, onNew, loading }) {
  const [filter, setFilter] = useState('')

  const filtered = sessions.filter(s =>
    !filter ||
    s.db_type?.includes(filter) ||
    s.embedding_provider?.includes(filter) ||
    s.id.includes(filter)
  )

  return (
    <aside style={{
      width: 260,
      minWidth: 260,
      background: 'var(--bg-surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
    }}>
      {/* Header */}
      <div style={{ padding: '20px 16px 16px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Logo />
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 15, letterSpacing: '-0.3px' }}>
              RAGnarok
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              v1.0 · debugger
            </div>
          </div>
        </div>

        <button onClick={onNew} style={{
          width: '100%',
          padding: '8px 12px',
          background: 'var(--red)',
          color: '#fff',
          borderRadius: 'var(--radius)',
          fontWeight: 600,
          fontSize: 13,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          transition: 'opacity var(--transition)',
        }}
          onMouseOver={e => e.currentTarget.style.opacity = '0.85'}
          onMouseOut={e => e.currentTarget.style.opacity = '1'}
        >
          <span style={{ fontSize: 16 }}>+</span> New Diagnosis
        </button>
      </div>

      {/* Search */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
        <input
          placeholder="Filter sessions…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{
            width: '100%',
            background: 'var(--bg-input)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '6px 10px',
            fontSize: 12,
            color: 'var(--text-primary)',
            outline: 'none',
          }}
        />
      </div>

      {/* Session list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {loading && (
          <div style={{ padding: '24px 16px', color: 'var(--text-muted)', fontSize: 12, textAlign: 'center' }}>
            Loading…
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div style={{ padding: '24px 16px', color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', lineHeight: 1.7 }}>
            No sessions yet.<br />
            Click <strong>New Diagnosis</strong> to start.
          </div>
        )}
        {filtered.map(s => (
          <SessionItem
            key={s.id}
            session={s}
            active={s.id === activeId}
            onClick={() => onSelect(s.id)}
          />
        ))}
      </div>

      {/* Footer */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid var(--border)',
        fontSize: 11,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
      }}>
        {sessions.length} session{sessions.length !== 1 ? 's' : ''}
      </div>
    </aside>
  )
}

function SessionItem({ session, active, onClick }) {
  const status = STATUS_META[session.status] || STATUS_META.pending
  const dominant = session.dominant_failure
  const meta = dominant ? diagMeta(dominant) : null

  return (
    <div
      onClick={onClick}
      style={{
        padding: '10px 16px',
        cursor: 'pointer',
        background: active ? 'var(--bg-hover)' : 'transparent',
        borderLeft: `2px solid ${active ? 'var(--red)' : 'transparent'}`,
        transition: 'background var(--transition)',
      }}
      onMouseOver={e => { if (!active) e.currentTarget.style.background = 'var(--bg-card)' }}
      onMouseOut={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
          {session.id.slice(0, 8)}
        </span>
        <span style={{
          fontSize: 10,
          fontWeight: 600,
          color: status.color,
          fontFamily: 'var(--font-mono)',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}>
          {status.label}
        </span>
      </div>

      <div style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 4, fontWeight: 500 }}>
        {session.db_type || '—'} / {session.embedding_provider || '—'}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        {meta ? (
          <span style={{ fontSize: 11, color: meta.color, fontFamily: 'var(--font-mono)' }}>
            {meta.short}
          </span>
        ) : (
          <span />
        )}
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          {session.query_count}q
        </span>
      </div>
    </div>
  )
}

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
      <rect width="28" height="28" rx="6" fill="var(--red-dim)" />
      <path d="M7 14 L11 8 L15 17 L19 11 L21 14" stroke="var(--red)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
      <circle cx="21" cy="14" r="2" fill="var(--red)" />
    </svg>
  )
}
