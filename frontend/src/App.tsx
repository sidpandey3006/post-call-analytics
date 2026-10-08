import { useEffect, useState } from 'react'
import './App.css'
import { analyze, fetchSalesTemplate, previewTranscript } from './api'
import { FieldBuilder } from './FieldBuilder'
import { Results } from './Results'
import { normalizeFields } from './types'
import type { AnalyzeResponse, FieldDef } from './types'

const SAMPLE = JSON.stringify({
  call_id: 'demo-1',
  turns: [
    { speaker: 'agent', start: 0, text: 'Hi Dana, this is Sam from Acme. This call is recorded. Are you the one who signs off on tools?' },
    { speaker: 'customer', start: 8, text: "Yes, I am. We're looking for something under 5k a year." },
    { speaker: 'agent', start: 15, text: 'Our Pro plan is $4,800 per year and fits that. Can we book a demo?' },
    { speaker: 'customer', start: 24, text: "Sounds good, let's do 12 October. Email me at dana.whit@acme-corp.com or call (415) 555-0177." },
  ],
}, null, 2)

const PRESETS_KEY = 'pca.presets'
type Presets = Record<string, FieldDef[]>
const loadPresets = (): Presets => { try { return JSON.parse(localStorage.getItem(PRESETS_KEY) ?? '{}') } catch { return {} } }

export default function App() {
  const [transcript, setTranscript] = useState(SAMPLE)
  const [fields, setFields] = useState<FieldDef[]>(() => { try { return normalizeFields(JSON.parse(localStorage.getItem('pca.fields') ?? '[]')) } catch { return [] } })
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('jev-latest')
  const [presets, setPresets] = useState<Presets>(loadPresets)
  const [preview, setPreview] = useState<string>('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AnalyzeResponse | null>(null)

  useEffect(() => { localStorage.setItem('pca.fields', JSON.stringify(fields)) }, [fields])

  const parsed = (): unknown => JSON.parse(transcript)

  const doPreview = async () => {
    setError('')
    try {
      const p = await previewTranscript(parsed())
      setPreview(`${p.turns} turns · ~${p.approx_tokens} tokens${p.warnings.length ? ' · ' + p.warnings.join(' ') : ''}`)
    } catch (e) { setPreview(''); setError(e instanceof Error ? e.message : String(e)) }
  }

  const run = async () => {
    setError(''); setLoading(true)
    try {
      setResult(await analyze({ api_key: apiKey, transcript: parsed(), fields, model }))
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setLoading(false) }
  }

  const savePreset = () => {
    const name = prompt('Preset name?')
    if (!name) return
    const next = { ...presets, [name]: fields }
    setPresets(next); localStorage.setItem(PRESETS_KEY, JSON.stringify(next))
  }

  const importFields = () => {
    const txt = prompt('Paste fields JSON array')
    if (!txt) return
    try { setFields(normalizeFields(JSON.parse(txt))) } catch { setError('Invalid fields JSON') }
  }

  const canRun = apiKey && fields.length > 0 && !loading

  return (
    <div className="app">
      <header>
        <h1>Post-call analytics <span className="muted">powered by Jev</span></h1>
        <div className="row">
          <input type="password" placeholder="TypeSafe API key (kept in memory only)" value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" />
          <input className="narrow" value={model} onChange={(e) => setModel(e.target.value)} title="model" />
          <button className="primary" disabled={!canRun} onClick={run}>{loading ? 'Running…' : 'Run analysis'}</button>
        </div>
      </header>
      {error && <div className="flag banner">{error}</div>}
      <main>
        <section>
          <h2>1. Transcript JSON</h2>
          <textarea className="mono big" value={transcript} onChange={(e) => setTranscript(e.target.value)} spellCheck={false} />
          <div className="row"><button className="small" onClick={doPreview}>Validate / preview</button><span className="muted">{preview}</span></div>
        </section>
        <section>
          <h2>2. Fields</h2>
          <div className="row wrap">
            <button className="small" onClick={async () => { try { setFields(normalizeFields(await fetchSalesTemplate())) } catch (e) { setError(String(e)) } }}>Load sales template</button>
            <button className="small" onClick={savePreset} disabled={!fields.length}>Save preset</button>
            <select value="" onChange={(e) => e.target.value && setFields(normalizeFields(presets[e.target.value]))}>
              <option value="">Load preset…</option>
              {Object.keys(presets).map((n) => <option key={n}>{n}</option>)}
            </select>
            <button className="small" onClick={importFields}>Import JSON</button>
            <button className="small" disabled={!fields.length} onClick={() => navigator.clipboard.writeText(JSON.stringify(fields, null, 2))}>Copy JSON</button>
            <button className="small" disabled={!fields.length} onClick={() => setFields([])}>Clear</button>
          </div>
          <FieldBuilder fields={fields} setFields={setFields} />
        </section>
        <section>
          <h2>3. Results</h2>
          {result ? <Results data={result} /> : <p className="muted">Run an analysis to see structured results.</p>}
        </section>
      </main>
    </div>
  )
}
