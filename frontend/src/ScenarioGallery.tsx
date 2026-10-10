import type { ReactNode } from 'react'
import type { Scenario } from './api'

type Props = { scenarios: Scenario[]; selected: string; onPick: (s: Scenario) => void; extra?: ReactNode; focusGen?: boolean; onShowExamples?: () => void }

export function ScenarioGallery({ scenarios, selected, onPick, extra, focusGen, onShowExamples }: Props) {
  if (!scenarios.length) return null
  const current = scenarios.find((s) => s.name === selected)
  return (
    <details className="gallery" open>
      <summary>Start from an example <span className="muted">· pick a scenario to load its fields and a sample call, or generate your own</span></summary>
      <div className={"gallery-body" + (focusGen ? " focus" : "")}>
        {focusGen ? (
          <div className="examples-collapsed">
            <span className="muted">Example scenarios are minimised while you generate fields.</span>
            <button className="small" onClick={onShowExamples}>Show example scenarios</button>
          </div>
        ) : (
        <div>
          <div className="tiles">
            {scenarios.map((s) => (
              <button key={s.name} className={`tile${selected === s.name ? ' on' : ''}`} aria-pressed={selected === s.name} onClick={() => onPick(s)} title={s.description}>
                <span className="tile-title">{selected === s.name && <span className="check">✓ </span>}{s.title}</span>
                <span className="tile-desc">{s.description}</span>
              </button>
            ))}
          </div>
          {current && (
            <div className="muted gallery-note">
              <strong>{current.title}:</strong> {current.description}
              {current.notice && <> ⚠ {current.notice}</>}
            </div>
          )}
        </div>
        )}
        <aside className="gen-side">{extra}</aside>
      </div>
    </details>
  )
}
