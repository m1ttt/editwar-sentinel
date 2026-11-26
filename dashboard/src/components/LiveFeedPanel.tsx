import type { FeedEdit } from '../hooks/liveFeedReducer'
import { articleUrl, formatDelta, formatTime } from '../lib/format'
import { Panel } from './Panel'

interface LiveFeedPanelProps {
  edits: FeedEdit[]
}

function deltaClass(delta: number | null): string {
  if (delta === null || delta === 0) return ''
  return delta > 0 ? 'delta-up' : 'delta-down'
}

// Short uppercase tag for the event type: EDIT, NEW, REVERT, LOG...
export function eventTag(edit: Pick<FeedEdit, 'change_type'>): string {
  return (edit.change_type || 'edit').toUpperCase()
}

// A terminal-style stream of the raw events, newest first.
export function LiveFeedPanel({ edits }: LiveFeedPanelProps) {
  return (
    <Panel title="Flujo en vivo" aside="/ws/live · wiki.edits" className="area-stream">
      <div className="term">
        <p className="term-prompt mono" aria-hidden="true">
          <span className="term-ps">sentinel@soc:~$</span> tail -f /ws/live
          <span className="cursor" />
        </p>
        {edits.length === 0 ? (
          <p className="empty">Esperando ediciones…</p>
        ) : (
          <ol className="term-lines">
            {edits.map((edit) => (
              <li key={edit.event_id} className={edit.reverted ? 'term-line is-revert' : 'term-line'}>
                <span className="t-time">{formatTime(edit.timestamp)}</span>
                <span className={`t-type t-${edit.change_type}`}>{eventTag(edit)}</span>
                <span className="t-wiki">{edit.wiki}</span>
                <span className={`t-delta num ${deltaClass(edit.delta)}`}>
                  {edit.delta === null ? '–' : formatDelta(edit.delta)}
                </span>
                <span className="tags">
                  {edit.reverted && <span className="pill hi">revert</span>}
                  {edit.is_bot && <span className="pill lo">bot</span>}
                  {edit.change_type === 'new' && <span className="pill ok">nuevo</span>}
                </span>
                <span className="t-body">
                  <a href={articleUrl(edit.server_url, edit.title)} target="_blank" rel="noreferrer">
                    {edit.title}
                  </a>
                  <span className="t-user">{edit.user}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Panel>
  )
}
