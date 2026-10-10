import { useEffect, useState } from 'react'
import './App.css'
import { analyze, fetchTemplate, previewTranscript } from './api'
import { FieldBuilder } from './FieldBuilder'
import { Results } from './Results'
import { normalizeFields } from './types'
import type { AnalyzeResponse, FieldDef } from './types'

const SAMPLE = JSON.stringify({
  call_id: 'loan-demo-1',
  turns: [
    { speaker: 'agent', start: 0, text: 'Hello, this is Sam calling from Acme Finance. This call may be recorded. Am I speaking with Dana?' },
    { speaker: 'customer', start: 7, text: 'Yes, speaking.' },
    { speaker: 'agent', start: 10, text: 'Thanks Dana. You have a pre-approved personal loan of up to Rs 5,00,000 at rates starting from 11% per annum. Would you like to hear how it could work for you?' },
    { speaker: 'customer', start: 22, text: 'Sure, tell me.' },
    { speaker: 'agent', start: 25, text: 'How much would you like, and for how many months?' },
    { speaker: 'customer', start: 31, text: 'About Rs 2,00,000 for 24 months.' },
    { speaker: 'agent', start: 36, text: 'That comes to an EMI of about Rs 9,300 per month, with a processing fee of 1%. Is that EMI comfortable for you?' },
    { speaker: 'customer', start: 46, text: 'Yes, that works.' },
    { speaker: 'agent', start: 49, text: 'Are you salaried or self-employed, and what is your net monthly income?' },
    { speaker: 'customer', start: 55, text: 'Salaried, around Rs 85,000 a month.' },
    { speaker: 'agent', start: 60, text: 'To check eligibility we need to run a credit bureau check. Do you consent to this? Please say yes or no.' },
    { speaker: 'customer', start: 70, text: 'Yes, I consent.' },
    { speaker: 'agent', start: 73, text: 'Thank you. We can arrange a document pickup. Would 12 October work? I will send a link to (415) 555-0177.' },
    { speaker: 'customer', start: 84, text: 'Yes, 12 October is fine. You can also email me at dana.whit@acme-corp.com.' },
  ],
}, null, 2)

const PRESETS_KEY = 'pca.presets'
type Presets = Record<string, FieldDef[]>
const loadPresets = (): Presets => { try { return JSON.parse(localStorage.getItem(PRESETS_KEY) ?? '{}') } catch { return {} } }

export default function App() {
  const [transcript, setTranscript] = useState(SAMPLE)
  const [fields, setFields] = useState<FieldDef[]>(() => { try { return normalizeFields(JSON.parse(localStorage.getItem('pca.fields') ?? '[]')) } catch { return [] } })
  const [apiKey, setApiKey] = useState('')
  const [provider, setProvider] = useState<'jev' | 'microsoft'>(() => (localStorage.getItem('pca.provider') as 'jev' | 'microsoft') || 'microsoft')
  const [endpoint, setEndpoint] = useState(() => localStorage.getItem('pca.endpoint') ?? '')
  const [model, setModel] = useState(() => localStorage.getItem('pca.deployment') ?? 'Microsoft-Decision-1')
  useEffect(() => { localStorage.setItem('pca.provider', provider); localStorage.setItem('pca.endpoint', endpoint); localStorage.setItem('pca.deployment', model) }, [provider, endpoint, model])
  const changeProvider = (p: 'jev' | 'microsoft') => { setProvider(p); setModel(p === 'jev' ? 'jev-latest' : 'Microsoft-Decision-1') }
  const [presets, setPresets] = useState<Presets>(loadPresets)
  const [preview, setPreview] = useState<string>('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AnalyzeResponse | null>(null)

  useEffect(() => { localStorage.setItem('pca.fields', JSON.stringify(fields)) }, [fields])

  // Start with the loan template until the user has had it applied once and chosen otherwise
  useEffect(() => {
    if (!localStorage.getItem('pca.defaultApplied') && fields.length === 0) {
      fetchTemplate('loan').then((t) => setFields(normalizeFields(t))).catch(() => {})
    }
    localStorage.setItem('pca.defaultApplied', '1')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadTemplate = async (name: 'loan' | 'sales') => {
    try { setFields(normalizeFields(await fetchTemplate(name))) } catch (e) { setError(String(e)) }
  }

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
      setResult(await analyze({ api_key: apiKey, transcript: parsed(), fields, model, provider, endpoint: provider === 'microsoft' ? endpoint : undefined }))
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

  const canRun = apiKey && fields.length > 0 && !loading && (provider === 'jev' || (endpoint && model))

  return (
    <div className="app">
      <header>
        <h1>Post-call analytics <span className="muted">{provider === 'microsoft' ? 'v2 · Microsoft Decision-1' : 'v1 · Jev'}</span></h1>
        <div className="row wrap">
          <select value={provider} onChange={(e) => changeProvider(e.target.value as 'jev' | 'microsoft')}>
            <option value="microsoft">Microsoft Decision-1</option>
            <option value="jev">Jev</option>
          </select>
          {provider === 'microsoft' && <input placeholder="Foundry endpoint https://<resource>.services.ai.azure.com" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} />}
          <input type="password" placeholder={provider === 'microsoft' ? 'Foundry API key (kept in memory only)' : 'TypeSafe API key (kept in memory only)'} value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" />
          <input className="narrow" value={model} onChange={(e) => setModel(e.target.value)} title={provider === 'microsoft' ? 'Foundry deployment name' : 'model'} />
          <button className="primary" disabled={!canRun} onClick={run}>{loading ? 'Running…' : 'Run analysis'}</button>
        </div>
      </header>
      {provider === 'microsoft' && fields.some((f) => /loan|bureau/i.test(f.id)) && <div className="muted banner">Decision support only: Microsoft-Decision-1 must not be the sole basis for credit or other consequential decisions about people. Keep human review.</div>}
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
            <button className="small" onClick={() => loadTemplate('loan')}>Load loan sales template</button>
            <button className="small" onClick={() => loadTemplate('sales')}>Load sales template</button>
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
      <footer>Built by Siddhartha Pandey · Powered by {provider === 'microsoft' ? <a href="https://ai.azure.com/catalog/models/Microsoft-Decision-1" target="_blank" rel="noreferrer">Microsoft Decision-1</a> : <a href="https://docs.typesafe.ai" target="_blank" rel="noreferrer">Jev</a>}</footer>
    </div>
  )
}
