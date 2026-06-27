export const DIAGNOSIS_META = {
  retrieval_failure:     { label: 'Retrieval Failure',     color: '#FFB547', short: 'RETR' },
  generation_failure:    { label: 'Generation Failure',    color: '#A855F7', short: 'GEN'  },
  compound_failure:      { label: 'Compound Failure',      color: '#FF4D6D', short: 'COMP' },
  data_quality_failure:  { label: 'Data Quality Failure',  color: '#4D9FFF', short: 'DATA' },
  no_failure_detected:   { label: 'No Failure Detected',   color: '#00E5A0', short: 'OK'   },
  insufficient_evidence: { label: 'Insufficient Evidence', color: '#4A5066', short: '???'  },
}

export const VERDICT_META = {
  RETRIEVAL_OK:      { color: '#00E5A0' },
  RETRIEVAL_FAIL:    { color: '#FF4D6D' },
  RETRIEVAL_PARTIAL: { color: '#FFB547' },
  DATA_MISSING:      { color: '#4D9FFF' },
  GENERATION_OK:     { color: '#00E5A0' },
  GENERATION_FAIL:   { color: '#FF4D6D' },
  GENERATION_PARTIAL:{ color: '#FFB547' },
  SKIPPED:           { color: '#4A5066' },
  UNKNOWN:           { color: '#4A5066' },
}

export function diagMeta(key) {
  return DIAGNOSIS_META[key] || { label: key, color: '#4A5066', short: '?' }
}

export function confColor(score) {
  if (score >= 0.75) return '#00E5A0'
  if (score >= 0.5)  return '#FFB547'
  return '#FF4D6D'
}

export function effortColor(effort) {
  return { low: '#00E5A0', medium: '#FFB547', high: '#FF4D6D' }[effort] || '#4A5066'
}

export function impactColor(impact) {
  return { high: '#00E5A0', medium: '#FFB547', low: '#4A5066' }[impact] || '#4A5066'
}

export const STATUS_META = {
  pending:  { label: 'Pending',  color: '#4A5066' },
  running:  { label: 'Running',  color: '#FFB547' },
  complete: { label: 'Complete', color: '#00E5A0' },
  partial:  { label: 'Partial',  color: '#FFB547' },
  failed:   { label: 'Failed',   color: '#FF4D6D' },
}

export const SAMPLE_CONFIG = `name: "My RAG Pipeline"

vector_db:
  provider: chroma
  collection_name: my_docs
  host: localhost
  port: 8000

embedding:
  provider: openai
  model_id: text-embedding-3-small

llm:
  provider: openai
  model_id: gpt-4o-mini
  temperature: 0.0

retrieval:
  top_k: 5

prompt:
  template: |
    Answer using only the context below.
    If the answer isn't in the context, say "I cannot find this."

    Context: {context}

    Question: {question}

    Answer:`

export const SAMPLE_QUERIES = `[
  {
    "query": "How do I reset my password?",
    "expected_answer": "Go to Settings > Security > Reset Password.",
    "actual_answer": "I don't have information about this."
  },
  {
    "query": "What is the refund policy?",
    "expected_answer": "Full refund within 30 days of purchase.",
    "actual_answer": "Refund policies vary by product."
  }
]`
