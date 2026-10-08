import { useState } from 'react'
import type { AnalyzeResponse, FieldResult } from './types'

const pct = (n: number | null | undefined) => (n == null ? '–' : n.toFixed(2))

function Probs({ p }: { p: Record<string, number> | null }) {
  if (!p) return null
  return (
    <div className="probs">
      {Object.entries(p).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
        <div key={k} className="prob">
          <span className="plabel" title={k}>{k}</span>
          <span className="bar"><span style={{ width: `${v * 100}%` }} /></span>
          <span className="pval">{pct(v)}</span>
        </div>
      ))}
    </div>
  )
}

function ResultCard({ r }: { r: FieldResult }) {
  const display =
    r.kind === 'noul' ? pct(r.probability)
      : r.kind === 'entity' ? (r.value == null ? 'not found' : String(r.value))
        : String(r.value ?? '–')
  return (
    <div className={`card ${r.needs_review ? 'review' : ''}`}>
      <div className="row between">
        <strong className="mono">{r.id}</strong>
        <span className="badge">{r.kind}</span>
      </div>
      <div className="value">{display}</div>
      {r.kind === 'noul' && <div className="bar big"><span style={{ width: `${(r.probability ?? 0) * 100}%` }} /></div>}
      {r.kind === 'entity' && r.normalized != null && <div className="muted">normalized: <code>{JSON.stringify(r.normalized)}</code></div>}
      {r.kind === 'entity' && r.entity_candidates && <div className="muted">candidates: {r.entity_candidates.join(' · ') || 'none'}</div>}
      {r.confidence != null && <div className="muted">confidence {pct(r.confidence)}</div>}
      {r.kind === 'score' && r.legend && typeof r.value === 'number' && (
        <div className="muted">≈ {r.legend[String(Math.round(r.value))] ?? ''}</div>
      )}
      {r.kind !== 'noul' && <Probs p={r.probabilities} />}
      {r.needs_review && <div className="flag">⚠ Review: {r.review_reason}</div>}
      {!r.needs_review && r.review_reason && <div className="muted">{r.review_reason}</div>}
    </div>
  )
}

export function Results({ data }: { data: AnalyzeResponse }) {
  const [tab, setTab] = useState<'results' | 'request' | 'response' | 'usage'>('results')
  return (
    <div className="stack">
      <div className="tabs">
        {(['results', 'request', 'response', 'usage'] as const).map((t) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {tab === 'results' && (
        <>
          {data.warnings.map((w, i) => <div key={i} className="flag">⚠ {w}</div>)}
          <div className={data.flags.length ? 'flag' : 'ok'}>
            {data.flags.length ? `${data.flags.length} field(s) need review` : 'No review flags'}
          </div>
          {data.results.map((r) => <ResultCard key={r.id} r={r} />)}
        </>
      )}
      {tab === 'request' && <pre>{JSON.stringify(data.raw_request, null, 2)}</pre>}
      {tab === 'response' && <pre>{JSON.stringify(data.raw_response, null, 2)}</pre>}
      {tab === 'usage' && (
        <div className="card">
          <div>Input tokens: <strong>{data.usage?.input_tokens ?? '–'}</strong></div>
          <div>Output tokens: <strong>{data.usage?.output_tokens ?? '–'}</strong></div>
          <button className="small" onClick={() => {
            const blob = new Blob([JSON.stringify(data.results, null, 2)], { type: 'application/json' })
            const a = document.createElement('a')
            a.href = URL.createObjectURL(blob)
            a.download = 'analytics.json'
            a.click()
          }}>Download results JSON</button>
        </div>
      )}
    </div>
  )
}
