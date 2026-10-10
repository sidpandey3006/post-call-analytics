import type { AnalyzeResponse, FieldDef } from './types'

const BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + url, init)
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const d = data?.detail
    throw new Error(typeof d === 'string' ? d : d ? JSON.stringify(d) : `Request failed (${r.status})`)
  }
  return data as T
}

const post = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const previewTranscript = (transcript: unknown) =>
  request<{ state: unknown; warnings: string[]; turns: number; approx_tokens: number }>(
    '/api/normalize-preview',
    post({ transcript }),
  )

export const analyze = (p: {
  api_key: string
  transcript: unknown
  fields: FieldDef[]
  model: string
  provider?: 'jev' | 'microsoft'
  endpoint?: string
}) => request<AnalyzeResponse>('/api/analyze', post(p))

export const fetchTemplate = (name: 'loan' | 'sales') => request<FieldDef[]>(`/api/templates/${name}`)

export type Scenario = {
  name: string
  title: string
  publisher: string
  tags: string[]
  description: string
  notice?: string
  fields: FieldDef[]
  sample: unknown
}
export const fetchScenarios = () => request<Scenario[]>('/api/scenarios')

export type Suggestion = { name: string; title: string; description: string; notice?: string | null; fields: FieldDef[] }
export type GenerateResult =
  | { mode: 'suggestions'; matches: Suggestion[] }
  | { mode: 'generated'; fields: FieldDef[]; rejected: { id: string; reason: string }[]; warnings: string[] }

export const generateFields = (p: {
  description: string
  endpoint?: string
  api_key?: string
  chat_deployment?: string
  max_fields?: number
}) => request<GenerateResult>('/api/generate-fields', post(p))
