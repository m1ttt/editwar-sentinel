import type { FeedEdit } from '../hooks/liveFeedReducer'
import { wikiActivity } from '../lib/derive'
import { Panel } from './Panel'

interface WikiActivityPanelProps {
  // The rows of the live feed (the last MAX_EDITS events).
  edits: FeedEdit[]
}

export function WikiActivityPanel({ edits }: WikiActivityPanelProps) {
  const rows = wikiActivity(edits)
  // The busiest wiki has a full bar. The other bars are relative to it.
  const max = Math.max(1, ...rows.map((row) => row.events))

  return (
    <Panel title="Actividad por wiki" aside={`últimos ${edits.length}`} className="area-wikis">
      {rows.length === 0 ? (
        <p className="empty">Sin eventos todavía.</p>
      ) : (
        <ol className="barlist">
          {rows.map((row) => (
            <li key={row.wiki}>
              <span className="barlist-name mono">{row.wiki}</span>
              <span className="bar" aria-hidden="true">
                <i style={{ width: `${(row.events / max) * 100}%` }} />
                {row.reverts > 0 && <b style={{ width: `${(row.reverts / max) * 100}%` }} />}
              </span>
              <span className="barlist-count mono">
                {row.events}
                {row.reverts > 0 && <span className="revert-count">{` · ${row.reverts} rev.`}</span>}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}
