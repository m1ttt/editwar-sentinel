import type { FeedEdit } from '../hooks/liveFeedReducer'
import { articleUrl, formatDelta, formatTime } from '../lib/format'
import { Panel } from './Panel'
import { Sparkline } from './Sparkline'

interface LiveFeedPanelProps {
  edits: FeedEdit[]
  throughput: number[]
}

function deltaClass(delta: number | null): string {
  if (delta === null || delta === 0) return ''
  return delta > 0 ? 'delta-up' : 'delta-down'
}

export function LiveFeedPanel({ edits, throughput }: LiveFeedPanelProps) {
  return (
    <Panel title="Flujo en vivo" aside="wiki.edits">
      <Sparkline values={throughput} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Hora</th>
              <th>Wiki</th>
              <th>Artículo</th>
              <th>Usuario</th>
              <th className="num">Δ bytes</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {edits.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  Esperando ediciones…
                </td>
              </tr>
            )}
            {edits.map((edit) => (
              <tr key={edit.event_id}>
                <td className="mono">{formatTime(edit.timestamp)}</td>
                <td>{edit.wiki}</td>
                <td>
                  <a href={articleUrl(edit.server_url, edit.title)} target="_blank" rel="noreferrer">
                    {edit.title}
                  </a>
                </td>
                <td>{edit.user}</td>
                <td className={`num ${deltaClass(edit.delta)}`}>{edit.delta === null ? '–' : formatDelta(edit.delta)}</td>
                <td className="tags">
                  {edit.reverted && <span className="pill hi">revert</span>}
                  {edit.is_bot && <span className="pill lo">bot</span>}
                  {edit.change_type === 'new' && <span className="pill ok">nuevo</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
