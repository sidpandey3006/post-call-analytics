export type Kind = 'noul' | 'choice' | 'score' | 'entity'
export type EntityType = 'email' | 'phone' | 'amount' | 'date' | 'id' | 'name'

export interface FieldDef {
  id: string
  kind: Kind
  instructions: string
  criteria?: Record<string, string | null> | null
  levels?: string[] | null
  entity_type?: EntityType | null
  pattern?: string | null
  min_confidence: number
  uncertain_band: [number, number]
}

export interface FieldResult {
  id: string
  kind: Kind
  value: unknown
  probability: number | null
  confidence: number | null
  probabilities: Record<string, number> | null
  legend: Record<string, string> | null
  entity_candidates: string[] | null
  normalized: unknown
  needs_review: boolean
  review_reason: string | null
}

export interface AnalyzeResponse {
  results: FieldResult[]
  flags: string[]
  state: unknown
  warnings: string[]
  raw_request: unknown
  raw_response: unknown
  usage: { input_tokens?: number; output_tokens?: number } | null
}

// Fill defaults so templates, presets and imports can omit optional keys
export const normalizeFields = (input: unknown): FieldDef[] =>
  (Array.isArray(input) ? input : []).map((raw) => {
    const f = (raw ?? {}) as Partial<FieldDef>
    const kind: Kind = (['noul', 'choice', 'score', 'entity'] as const).includes(f.kind as Kind) ? (f.kind as Kind) : 'noul'
    const base = newField(kind)
    const band = Array.isArray(f.uncertain_band) && f.uncertain_band.length === 2 ? f.uncertain_band : base.uncertain_band
    return {
      ...base,
      ...f,
      kind,
      id: f.id ?? '',
      instructions: f.instructions ?? '',
      criteria: f.criteria ?? base.criteria,
      levels: f.levels ?? base.levels,
      entity_type: f.entity_type ?? base.entity_type,
      min_confidence: typeof f.min_confidence === 'number' ? f.min_confidence : base.min_confidence,
      uncertain_band: [band[0], band[1]],
    }
  })

export const newField = (kind: Kind = 'noul'): FieldDef => ({
  id: '',
  kind,
  instructions: '',
  criteria: kind === 'choice' ? { option_a: '', option_b: '' } : null,
  levels: kind === 'score' ? ['Low', 'High'] : null,
  entity_type: kind === 'entity' ? 'email' : null,
  min_confidence: 0.7,
  uncertain_band: [0.3, 0.7],
})
