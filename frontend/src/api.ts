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
}) => request<AnalyzeResponse>('/api/analyze', post(p))

export const fetchTemplate = (name: 'loan' | 'sales') => request<FieldDef[]>(`/api/templates/${name}`)
