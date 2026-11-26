import { useId, useState } from 'react'
import { formatDelta, formatTime } from '../lib/format'
import { participantsOf, participantStyle } from '../lib/wiki'
import type { TimelineEntry } from '../types'
import { DiffView } from './DiffView'

interface EditWarTimelineProps {
  timeline: TimelineEntry[]
  // Server of the wiki, for GET /api/diff (alert.server_url).
  serverUrl: string
  // True when the api left older edits out (evidence.timeline_truncated).
  truncated?: boolean
}

export const COMMENT_MAX = 90

// Long comments are cut. The full text stays in the title attribute.
export function shortComment(comment: string, max: number = COMMENT_MAX): string {
  const text = comment.trim()
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text
}

const REVERT_REASONS = {
  comment: 'detectado por el comentario de la edición',
  size_restore: 'la edición restauró un tamaño anterior del artículo',
} as const

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

function UserTag({ user, index }: { user: string; index: number }) {
  const style = participantStyle(index)
  return (
    <span className="ew-user" style={{ color: style.color }}>
      <span className="ew-marker" aria-hidden="true">
        {style.marker}
      </span>
      {user}
    </span>
  )
}

function deltaClass(delta: number): string {
  if (delta === 0) return ''
  return delta > 0 ? 'delta-up' : 'delta-down'
}

// Who fought, in what order, and who reverted whom, for one alert.
export function EditWarTimeline({ timeline, serverUrl, truncated = false }: EditWarTimelineProps) {
  const participants = participantsOf(timeline)
  const indexOf = new Map(participants.map((participant) => [participant.user, participant.index]))
  // Keys of the rows whose diff is open.
  const [open, setOpen] = useState<Set<string>>(() => new Set())
  const baseId = useId()

  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div className="ew">
      <ul className="ew-participants" aria-label="Participantes">
        {participants.map((participant) => (
          <li key={participant.user}>
            <UserTag user={participant.user} index={participant.index} />
            {participant.is_bot && <span className="pill lo">bot</span>}
            <span className="ew-counts mono">
              {plural(participant.edits, 'edición', 'ediciones')} ·{' '}
              {plural(participant.revertsMade, 'reversión', 'reversiones')} · revertido{' '}
              {plural(participant.revertedBy, 'vez', 'veces')}
            </span>
          </li>
        ))}
      </ul>
      {truncated && (
        <p className="ew-note mono">
          Solo se muestran las ediciones más recientes; las anteriores están en el historial.
        </p>
      )}
      <ol className="ew-timeline" aria-label="Ediciones en orden cronológico">
        {timeline.map((entry, position) => {
          const diffId = `${baseId}-diff-${position}`
          const rowKey = `${entry.event_id}-${position}`
          const isOpen = open.has(rowKey)
          const index = indexOf.get(entry.user) ?? 0
          return (
            <li key={rowKey} className={entry.is_revert ? 'ew-entry is-revert' : 'ew-entry'}>
              <div className="ew-line">
                <span className="ew-time mono">{formatTime(entry.timestamp)}</span>
                <UserTag user={entry.user} index={index} />
                <span className="ew-tags">
                  {entry.is_bot && <span className="pill lo">bot</span>}
                  {entry.is_revert && (
                    <span
                      className="pill hi"
                      title={entry.revert_reason ? REVERT_REASONS[entry.revert_reason] : undefined}
                    >
                      {entry.reverted_user ? `revierte a ${entry.reverted_user}` : 'revert'}
                    </span>
                  )}
                </span>
                <span className={`ew-delta num ${deltaClass(entry.size_delta)}`}>{formatDelta(entry.size_delta)}</span>
              </div>
              <div className="ew-line ew-sub">
                <span className="ew-comment" title={entry.comment || undefined}>
                  {entry.comment.trim() ? shortComment(entry.comment) : <span className="muted">(sin comentario)</span>}
                </span>
                <span className="ew-actions">
                  {entry.diff_url && (
                    <a className="ext-link" href={entry.diff_url} target="_blank" rel="noreferrer">
                      diff ↗
                    </a>
                  )}
                  {entry.rev_id > 0 && (
                    <button
                      type="button"
                      className="btn ghost"
                      aria-expanded={isOpen}
                      aria-controls={isOpen ? diffId : undefined}
                      onClick={() => toggle(rowKey)}
                    >
                      {isOpen ? 'Ocultar cambio' : 'Ver cambio'}
                    </button>
                  )}
                </span>
              </div>
              {isOpen && (
                <div id={diffId} className="ew-diff">
                  <DiffView
                    key={`${serverUrl}|${entry.rev_id}|${entry.old_rev_id}`}
                    serverUrl={serverUrl}
                    revId={entry.rev_id}
                    oldRevId={entry.old_rev_id}
                    diffUrl={entry.diff_url}
                  />
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
