import { useState } from 'react'
import { generateFields } from './api'
import type { GenerateResult } from './api'
import { normalizeFields } from './types'
import type { FieldDef } from './types'

type Props = {
  endpoint: string
  apiKey: string
  canGenerate: boolean
  onApply: (fields: FieldDef[], mode: 'replace' | 'append') => void
}

export function GeneratePanel({ endpoint, apiKey, canGenerate, onApply }: Props) {
  const [desc, setDesc] = useState('')
  const [chat, setChat] = useState(() => localStorage.getItem('pca.chatDeployment') ?? '')
  const [max, setMax] = useState(10)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [res, setRes] = useState<GenerateResult | null>(null)
  const [picked, setPicked] = useState<Record<string, boolean>>({})

  const go = async () => {
    setErr(''); setRes(null); setBusy(true)
    localStorage.setItem('pca.chatDeployment', chat)
    try {
      const useModel = canGenerate && chat.trim()
      const r = await generateFields({
        description: desc, max_fields: max,
        ...(useModel ? { endpoint, api_key: apiKey, chat_deployment: chat.trim() } : {}),
      })
      setRes(r)
      if (r.mode === 'generated') setPicked(Object.fromEntries(r.fields.map((f) => [f.id, true])))
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }

  const chosen = res?.mode === 'generated' ? normalizeFields(res.fields.filter((f) => picked[f.id])) : []

  return (
    <div className="gen tile-gen">
      <div className="tile-title">✨ Generate fields with AI <span className="tag">New</span></div>
      <p className="muted">Describe your use case to get a starting set of fields, loaded into the Fields panel.</p>
      <textarea rows={3} maxLength={2000} placeholder="e.g. Inbound insurance renewal calls: was the premium and renewal date explained, did the customer agree to renew, and any objections." value={desc} onChange={(e) => setDesc(e.target.value)} />
      <div className="row wrap">
        <input placeholder="Chat deployment (e.g. gpt-4o) — optional" value={chat} onChange={(e) => setChat(e.target.value)} />
        <label className="muted">Max fields <input className="narrow" type="number" min={3} max={15} value={max} onChange={(e) => setMax(Number(e.target.value))} /></label>
        <button className="primary" disabled={busy || desc.trim().length < 20} onClick={go}>{busy ? 'Working…' : 'Generate'}</button>
      </div>
      <p className="muted">With a Foundry chat deployment (same endpoint and key) the model generates fields; otherwise the closest starter templates are suggested. Review before applying. Decision support only.</p>
      {err && <div className="flag">{err}</div>}
      {res?.mode === 'suggestions' && res.matches.map((m) => (
        <div key={m.name} className="card">
          <strong>{m.title}</strong> <span className="muted">{m.fields.length} fields</span>
          <div className="muted">{m.description}</div>
          {m.notice && <div className="muted">⚠ {m.notice}</div>}
          <div className="row">
            <button className="small" onClick={() => onApply(normalizeFields(m.fields), 'replace')}>Replace fields</button>
            <button className="small" onClick={() => onApply(normalizeFields(m.fields), 'append')}>Append</button>
          </div>
        </div>
      ))}
      {res?.mode === 'generated' && (
        <div>
          {res.warnings.map((w) => <div key={w} className="muted">⚠ {w}</div>)}
          {res.rejected.length > 0 && <div className="flag">Skipped: {res.rejected.map((r) => `${r.id} (${r.reason})`).join('; ')}</div>}
          {res.fields.map((f) => (
            <label key={f.id} className="card" style={{ display: 'block' }}>
              <input type="checkbox" checked={!!picked[f.id]} onChange={(e) => setPicked({ ...picked, [f.id]: e.target.checked })} />{' '}
              <strong>{f.id}</strong> <span className="muted">{f.kind}</span>
              <div className="muted">{f.instructions}</div>
            </label>
          ))}
          <div className="row">
            <button className="primary small" disabled={!chosen.length} onClick={() => onApply(chosen, 'replace')}>Replace fields ({chosen.length})</button>
            <button className="small" disabled={!chosen.length} onClick={() => onApply(chosen, 'append')}>Append</button>
          </div>
        </div>
      )}
    </div>
  )
}
