import type { ReactNode } from 'react'
import type { Scenario } from './api'

type Props = { scenarios: Scenario[]; selected: string; onPick: (s: Scenario) => void; extra?: ReactNode }

export function ScenarioGallery({ scenarios, selected, onPick, extra }: Props) {
  if (!scenarios.length) return null
  return (
    <details className="gallery" open>
      <summary>Example scenarios <span className="muted">· click one to load its fields and a sample call, then edit</span></summary>
      <div className="tiles">
        {scenarios.map((s) => (
          <button key={s.name} className={`tile${selected === s.name ? ' on' : ''}`} onClick={() => onPick(s)} title={s.description}>
            <span className="tile-title">{s.title}</span>
            <span className="tile-pub">{s.publisher}</span>
            <span className="tile-tags">{s.tags.map((t) => <span key={t} className="tag">{t}</span>)}</span>
          </button>
        ))}
        {extra}
      </div>
      {scenarios.find((s) => s.name === selected) && (
        <div className="muted gallery-note">
          {scenarios.find((s) => s.name === selected)!.description}
          {scenarios.find((s) => s.name === selected)!.notice && <> ⚠ {scenarios.find((s) => s.name === selected)!.notice}</>}
        </div>
      )}
    </details>
  )
}
