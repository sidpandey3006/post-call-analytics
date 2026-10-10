import { useState } from 'react'
import { generateFields } from './api'
import type { GenerateResult } from './api'
import { normalizeFields } from './types'
import type { FieldDef } from './types'

type Props = {
  endpoint: string
  apiKey: string
  canGenerate: boolean
  onActive?: (active: boolean) => void
  onApply: (fields: FieldDef[], mode: 'replace' | 'append', sample?: unknown) => void
}

export function GeneratePanel({ endpoint, apiKey, canGenerate, onApply, onActive }: Props) {
  const [desc, setDesc] = useState('')
  const [chat, setChat] = useState(() => localStorage.getItem('pca.chatDeployment') ?? '')
  const [max, setMax] = useState(10)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState('')
  const [res, setRes] = useState<GenerateResult | null>(null)

  const go = async () => {
    setErr(''); setRes(null); setDone(''); setBusy(true)
    localStorage.setItem('pca.chatDeployment', chat)
    try {
      const useModel = canGenerate && chat.trim()
      const r = await generateFields({
        description: desc, max_fields: max,
        ...(useModel ? { endpoint, api_key: apiKey, chat_deployment: chat.trim() } : {}),
      })
      setRes(r)
      if (r.mode === 'suggestions' && r.matches.length) {
        const m = r.matches[0]
        onApply(normalizeFields(m.fields), 'replace', m.sample)
        setDone('Loaded ' + m.fields.length + ' fields' + (m.sample ? ' and a sample transcript' : '') + ' (closest starter: ' + m.title + '). Review them in section 2, then click Run analysis.')
      }
      if (r.mode === 'generated') {
        const fs = normalizeFields(r.fields)
        if (fs.length) { onApply(fs, 'replace', r.sample); setDone('Generated ' + fs.length + ' fields' + (r.sample ? ' and a sample transcript' : '') + ' and loaded them. Review them in section 2, then click Run analysis.') }
      }
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }

  return (
    <div className="gen">
      <div className="tile-title">✨ Generate fields with AI <span className="tag">New</span></div>
      <p className="muted">Describe your use case to get a starting set of fields, loaded into the Fields panel.</p>
      <textarea rows={3} maxLength={2000} placeholder="e.g. Inbound insurance renewal calls: was the premium and renewal date explained, did the customer agree to renew, and any objections." value={desc} onChange={(e) => { setDesc(e.target.value); if (e.target.value) onActive?.(true) }} />
      <div className="row wrap">
        <input placeholder="Chat deployment (e.g. gpt-4o) — optional" value={chat} onChange={(e) => setChat(e.target.value)} />
        <label className="muted">Max fields <input className="narrow" type="number" min={3} max={15} value={max} onChange={(e) => setMax(Number(e.target.value))} /></label>
        <button className="primary" disabled={busy || desc.trim().length < 20} onClick={go}>{busy ? 'Working…' : 'Generate'}</button>
      </div>
      <p className="muted">With a Foundry chat deployment (same endpoint and key) the model generates fields; otherwise the closest starter templates are suggested. Review before applying. Decision support only.</p>
      {busy && <div className="muted">Generating… this can take 10–30 seconds.</div>}
      {done && <div className="ok">✓ {done}</div>}
      {!canGenerate && !busy && !res && <div className="muted">Tip: choose provider Microsoft and enter endpoint + key + chat deployment to have AI generate fields; otherwise starter templates are suggested.</div>}
      {res?.mode === 'suggestions' && !res.matches.length && <div className="flag">No starter template matched your description, and AI generation wasn't used{canGenerate ? ' (enter a chat deployment name such as gpt-4o)' : ' (needs Microsoft provider, endpoint, key and chat deployment)'}. Nothing was loaded.</div>}
      {err && <div className="flag">{err}</div>}
      {res?.mode === 'generated' && res.warnings.map((w) => <div key={w} className="muted">⚠ {w}</div>)}
      {res?.mode === 'generated' && res.rejected.length > 0 && <div className="muted">Skipped {res.rejected.length} invalid field(s).</div>}
    </div>
  )
}
