import { useState } from 'react'
import { api } from '../api/client'
import { SAMPLE_CONFIG, SAMPLE_QUERIES } from '../utils/diagnosis'

export default function NewSessionModal({ onClose, onCreated }) {
  const [tab, setTab] = useState('config') // 'config' | 'queries'
  const [configText, setConfigText] = useState(SAMPLE_CONFIG)
  const [queriesText, setQueriesText] = useState(SAMPLE_QUERIES)
  const [redactPii, setRedactPii] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [validating, setValidating] = useState(false)
  const [validMsg, setValidMsg] = useState(null)

  async function handleValidate() {
    setValidating(true)
    setValidMsg(null)
    try {
      const yaml = await import('https://esm.sh/js-yaml@4')
      const cfg = yaml.load(configText)
      const result = await api.validatePipeline(cfg)
      setValidMsg({ ok: true, text: `✓ Valid — ${result.pipeline_name}`, warnings: result.warnings })
    } catch (e) {
      setValidMsg({ ok: false, text: e.message })
    } finally {
      setValidating(false)
    }
  }

  async function handleSubmit() {
    setLoading(true)
    setError(null)
    try {
      const yaml = await import('https://esm.sh/js-yaml@4')
      const pipeline_config = yaml.load(configText)
      const queries = JSON.parse(queriesText)
      const session = await api.createSession({ pipeline_config, queries, redact_pii: redactPii })
      onCreated(session.session_id)
      onClose()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      backdropFilter: 'blur(4px)',
    }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        width: 720,
        maxWidth: '95vw',
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>
        {/* Header */}
        <div style={{
          padding: '20px 24px 16px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 16 }}>New Diagnosis Session</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
              Paste your pipeline config and failing queries to begin
            </div>
          </div>
          <button onClick={onClose} style={{ color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>×</button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', padding: '0 24px' }}>
          {['config', 'queries'].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: '12px 16px',
              fontSize: 13,
              fontWeight: 500,
              color: tab === t ? 'var(--text-primary)' : 'var(--text-muted)',
              borderBottom: `2px solid ${tab === t ? 'var(--red)' : 'transparent'}`,
              marginBottom: -1,
              transition: 'color var(--transition)',
              textTransform: 'capitalize',
            }}>
              {t === 'config' ? '① Pipeline Config' : '② Failing Queries'}
            </button>
          ))}
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: 'hidden', padding: '16px 24px' }}>
          {tab === 'config' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                  pipeline.yaml
                </label>
                <button onClick={handleValidate} disabled={validating} style={{
                  fontSize: 12,
                  color: 'var(--blue)',
                  padding: '4px 10px',
                  border: '1px solid var(--blue)',
                  borderRadius: 'var(--radius-sm)',
                  opacity: validating ? 0.6 : 1,
                }}>
                  {validating ? 'Validating…' : 'Validate'}
                </button>
              </div>

              {validMsg && (
                <div style={{
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 12,
                  fontFamily: 'var(--font-mono)',
                  background: validMsg.ok ? 'var(--green-dim)' : 'var(--red-dim)',
                  color: validMsg.ok ? 'var(--green)' : 'var(--red)',
                  border: `1px solid ${validMsg.ok ? 'var(--green)' : 'var(--red)'}`,
                }}>
                  {validMsg.text}
                  {validMsg.warnings?.length > 0 && (
                    <div style={{ marginTop: 4, color: 'var(--yellow)' }}>
                      {validMsg.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
                    </div>
                  )}
                </div>
              )}

              <textarea
                value={configText}
                onChange={e => setConfigText(e.target.value)}
                spellCheck={false}
                style={{
                  flex: 1,
                  minHeight: 320,
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  padding: '12px 14px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  lineHeight: 1.7,
                  color: 'var(--text-primary)',
                  resize: 'none',
                  outline: 'none',
                }}
              />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                  queries.json — array of &#123; query, expected_answer?, actual_answer? &#125;
                </label>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {(() => { try { return JSON.parse(queriesText).length + ' queries' } catch { return 'invalid json' } })()}
                </span>
              </div>
              <textarea
                value={queriesText}
                onChange={e => setQueriesText(e.target.value)}
                spellCheck={false}
                style={{
                  flex: 1,
                  minHeight: 320,
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  padding: '12px 14px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  lineHeight: 1.7,
                  color: 'var(--text-primary)',
                  resize: 'none',
                  outline: 'none',
                }}
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '16px 24px',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <input type="checkbox" checked={redactPii} onChange={e => setRedactPii(e.target.checked)}
              style={{ accentColor: 'var(--red)' }} />
            Redact PII before external API calls
          </label>

          <div style={{ display: 'flex', gap: 10 }}>
            <button onClick={onClose} style={{
              padding: '8px 16px',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              fontSize: 13,
              color: 'var(--text-secondary)',
            }}>
              Cancel
            </button>
            <button onClick={handleSubmit} disabled={loading} style={{
              padding: '8px 20px',
              background: 'var(--red)',
              color: '#fff',
              borderRadius: 'var(--radius)',
              fontSize: 13,
              fontWeight: 600,
              opacity: loading ? 0.7 : 1,
              transition: 'opacity var(--transition)',
            }}>
              {loading ? 'Starting…' : 'Run Diagnosis →'}
            </button>
          </div>
        </div>

        {error && (
          <div style={{
            margin: '0 24px 16px',
            padding: '10px 14px',
            background: 'var(--red-dim)',
            border: '1px solid var(--red)',
            borderRadius: 'var(--radius)',
            fontSize: 12,
            color: 'var(--red)',
            fontFamily: 'var(--font-mono)',
          }}>
            {error}
          </div>
        )}
      </div>
    </div>
  )
}
