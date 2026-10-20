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

// USD per 1M tokens (input, output). Indicative list prices; check the Azure pricing page for current rates.
const PRICES = {
  decision1: [0.042, 0],
  luna: [0.2, 1.2],
  terra: [2, 12],
  sol: [4, 20],
} as const
const usd = (n: number) => (n < 0.0001 ? '<$0.0001' : n < 0.01 ? '$' + n.toFixed(5) : '$' + n.toFixed(4))
const cost = (p: readonly [number, number], i: number, o: number) => (i * p[0] + o * p[1]) / 1e6

function downloadJson(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function Results({ data, elapsedMs, provider }: { data: AnalyzeResponse; elapsedMs?: number | null; provider?: string }) {
  const [tab, setTab] = useState<'results' | 'request' | 'response' | 'usage'>('results')
  const inTok = data.usage?.input_tokens
  const outTok = data.usage?.output_tokens
  const i = inTok ?? 0, o = outTok ?? 0
  const total = inTok != null || outTok != null ? (inTok ?? 0) + (outTok ?? 0) : null
  return (
    <div className="stack">
      <div className="metrics">
        <span>⏱ <strong>{elapsedMs != null ? (elapsedMs / 1000).toFixed(1) + ' s' : '–'}</strong> <span className="muted">time taken</span></span>
        <span>🔢 <strong>{total ?? '–'}</strong> <span className="muted">tokens ({inTok ?? '–'} in / {outTok ?? '–'} out)</span></span>
          {total != null && provider === 'microsoft' && <span title="$0.042 per 1M input tokens, output free">💲 <strong>{usd(cost(PRICES.decision1, i, o))}</strong> <span className="muted">est. cost (Decision-1)</span></span>}
          {total != null && <span className="muted" title="Same token counts at GPT-5.6 short-context global list rates per 1M tokens (in/out): Luna $0.20/$1.20, Terra $2/$12, Sol $4/$20. A generative model would usually emit more output tokens, so treat this as indicative.">If GPT-5.6: Luna <strong>{usd(cost(PRICES.luna, i, o))}</strong> · Terra <strong>{usd(cost(PRICES.terra, i, o))}</strong> · Sol <strong>{usd(cost(PRICES.sol, i, o))}</strong> <em>(tentative)</em></span>}
      </div>
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
          {data.structured_output && <div className="card">
            <strong>Extracted JSON</strong>
            <p className="muted">Missing values are empty strings. Candidate matching can miss unfamiliar wording; review the field results before using this output.</p>
            <pre>{JSON.stringify(data.structured_output, null, 2)}</pre>
            <button className="small" onClick={() => downloadJson(data.structured_output, 'extracted-entities.json')}>Download extracted JSON</button>
          </div>}
          {data.results.map((r) => <ResultCard key={r.id} r={r} />)}
        </>
      )}
      {tab === 'request' && <pre>{JSON.stringify(data.raw_request, null, 2)}</pre>}
      {tab === 'response' && <pre>{JSON.stringify(data.raw_response, null, 2)}</pre>}
      {tab === 'usage' && (
        <div className="card">
          <div>Input tokens: <strong>{data.usage?.input_tokens ?? '–'}</strong></div>
          <div>Output tokens: <strong>{data.usage?.output_tokens ?? '–'}</strong></div>
          <div>Time taken: <strong>{elapsedMs != null ? (elapsedMs / 1000).toFixed(2) + ' s' : '–'}</strong></div>
          <button className="small" onClick={() => downloadJson(data.results, 'analytics.json')}>Download results JSON</button>
        </div>
      )}
    </div>
  )
}
