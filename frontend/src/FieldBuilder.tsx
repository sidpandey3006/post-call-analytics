import type { EntityType, FieldDef, Kind } from './types'
import { newField } from './types'

const KINDS: Kind[] = ['noul', 'choice', 'score', 'entity']
const ENTITIES: EntityType[] = ['email', 'phone', 'amount', 'date', 'id', 'name']

function PairsEditor({ value, onChange }: { value: Record<string, string | null>; onChange: (v: Record<string, string | null>) => void }) {
  const rows = Object.entries(value)
  const set = (next: [string, string | null][]) => onChange(Object.fromEntries(next))
  return (
    <div className="stack">
      {rows.map(([k, v], i) => (
        <div className="row" key={i}>
          <input placeholder="option" value={k} onChange={(e) => set(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} />
          <input placeholder="description (optional)" value={v ?? ''} onChange={(e) => set(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} />
          <button className="icon" onClick={() => set(rows.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <button className="small" onClick={() => set([...rows, [`option_${rows.length + 1}`, '']])}>+ option</button>
    </div>
  )
}

function ListEditor({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="stack">
      {value.map((v, i) => (
        <div className="row" key={i}>
          <span className="muted">{i}</span>
          <input value={v} onChange={(e) => onChange(value.map((x, j) => (j === i ? e.target.value : x)))} />
          <button className="icon" onClick={() => onChange(value.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <button className="small" onClick={() => onChange([...value, ''])}>+ level (ordered low → high)</button>
    </div>
  )
}

function FieldCard({ f, onChange, onRemove }: { f: FieldDef; onChange: (f: FieldDef) => void; onRemove: () => void }) {
  const patch = (p: Partial<FieldDef>) => onChange({ ...f, ...p })
  const changeKind = (kind: Kind) => {
    const base = newField(kind)
    onChange({ ...base, id: f.id, instructions: f.instructions })
  }
  return (
    <div className="card">
      <div className="row">
        <input className="mono" placeholder="field_id" value={f.id} onChange={(e) => patch({ id: e.target.value })} />
        <select value={f.kind} onChange={(e) => changeKind(e.target.value as Kind)}>
          {KINDS.map((k) => <option key={k}>{k}</option>)}
        </select>
        <button className="icon" onClick={onRemove}>✕</button>
      </div>
      <textarea rows={2} placeholder="Instructions (one specific question)" value={f.instructions} onChange={(e) => patch({ instructions: e.target.value })} />
      {f.kind === 'noul' && (
        <div className="row">
          <input placeholder="true means… (optional)" value={f.criteria?.true ?? ''} onChange={(e) => patch({ criteria: { ...(f.criteria ?? {}), true: e.target.value } })} />
          <input placeholder="false means… (optional)" value={f.criteria?.false ?? ''} onChange={(e) => patch({ criteria: { ...(f.criteria ?? {}), false: e.target.value } })} />
        </div>
      )}
      {f.kind === 'choice' && <PairsEditor value={f.criteria ?? {}} onChange={(criteria) => patch({ criteria })} />}
      {f.kind === 'score' && <ListEditor value={f.levels ?? []} onChange={(levels) => patch({ levels })} />}
      {f.kind === 'entity' && (
        <label className="row">Entity type
          <select value={f.entity_type ?? 'email'} onChange={(e) => patch({ entity_type: e.target.value as EntityType })}>
            {ENTITIES.map((k) => <option key={k}>{k}</option>)}
          </select>
          {f.entity_type === 'id' && <input placeholder='ID regex, e.g. [A-Z]{2}\d{6} (optional)' value={f.pattern ?? ''} onChange={(e) => patch({ pattern: e.target.value })} />}
          {f.entity_type === 'name' && <span className="muted">Finds names after cues like 'my name is' or 'speaking with'</span>}
        </label>
      )}
      <div className="row muted">
        {f.kind === 'noul' ? (
          <>
            review if probability in
            <input type="number" step="0.05" min={0} max={1} value={f.uncertain_band[0]} onChange={(e) => patch({ uncertain_band: [+e.target.value, f.uncertain_band[1]] })} />–
            <input type="number" step="0.05" min={0} max={1} value={f.uncertain_band[1]} onChange={(e) => patch({ uncertain_band: [f.uncertain_band[0], +e.target.value] })} />
          </>
        ) : (
          <>
            review if confidence &lt;
            <input type="number" step="0.05" min={0} max={1} value={f.min_confidence} onChange={(e) => patch({ min_confidence: +e.target.value })} />
          </>
        )}
      </div>
    </div>
  )
}

export function FieldBuilder({ fields, setFields }: { fields: FieldDef[]; setFields: (f: FieldDef[]) => void }) {
  return (
    <div className="stack">
      {fields.map((f, i) => (
        <FieldCard key={i} f={f} onChange={(nf) => setFields(fields.map((x, j) => (j === i ? nf : x)))} onRemove={() => setFields(fields.filter((_, j) => j !== i))} />
      ))}
      <div className="row">
        {KINDS.map((k) => (
          <button key={k} className="small" onClick={() => setFields([...fields, newField(k)])}>+ {k}</button>
        ))}
      </div>
    </div>
  )
}
