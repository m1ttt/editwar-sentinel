// Wikipedia links and the edit war timeline that comes in alert.evidence.
import type { TimelineEntry } from '../types'

// Builds ".../w/index.php?title=Kubernetes&action=history" from an article URL
// like "https://en.wikipedia.org/wiki/Kubernetes". Returns null when the URL is
// not a "/wiki/<title>" page.
export function historyUrl(pageUrl: string | null | undefined): string | null {
  if (!pageUrl) {
    return null
  }
  let url: URL
  try {
    url = new URL(pageUrl)
  } catch {
    return null
  }
  const match = /^\/wiki\/(.+)$/.exec(url.pathname)
  if (!match) {
    return null
  }
  let title: string
  try {
    title = decodeURIComponent(match[1])
  } catch {
    title = match[1]
  }
  if (title === '' || title === '*') {
    return null
  }
  const params = new URLSearchParams({ title: title.replace(/ /g, '_'), action: 'history' })
  return `${url.origin}/w/index.php?${params.toString()}`
}

interface HasHistory {
  history_url?: string | null
  page_url?: string
  title?: string
}

// The history link of an article: the one from the api, or one built from page_url
// for older alerts and messages. null for wiki-wide alerts (title "*").
export function resolveHistoryUrl(item: HasHistory): string | null {
  if (item.title === '*') {
    return null
  }
  if (typeof item.history_url === 'string' && item.history_url !== '') {
    return item.history_url
  }
  if (item.history_url === null) {
    return null
  }
  return historyUrl(item.page_url)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function num(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

// Reads evidence.timeline. Returns null when the alert has no timeline (bot_spike
// alerts and alerts stored before the feature). Entries without a user are dropped,
// missing fields get safe defaults, and the result is sorted oldest first.
export function timelineOf(evidence: Record<string, unknown> | null | undefined): TimelineEntry[] | null {
  const raw = evidence?.timeline
  if (!Array.isArray(raw)) {
    return null
  }
  const entries: TimelineEntry[] = []
  for (const item of raw) {
    if (!isRecord(item) || typeof item.user !== 'string') {
      continue
    }
    const oldLen = num(item.old_len)
    const newLen = num(item.new_len)
    const reason = item.revert_reason
    entries.push({
      event_id: str(item.event_id) || `${entries.length}`,
      user: item.user,
      is_bot: item.is_bot === true,
      timestamp: str(item.timestamp),
      comment: str(item.comment),
      rev_id: num(item.rev_id),
      old_rev_id: num(item.old_rev_id),
      old_len: oldLen,
      new_len: newLen,
      size_delta: typeof item.size_delta === 'number' ? item.size_delta : newLen - oldLen,
      is_revert: item.is_revert === true,
      revert_reason: reason === 'comment' || reason === 'size_restore' ? reason : null,
      reverted_user: typeof item.reverted_user === 'string' && item.reverted_user !== '' ? item.reverted_user : null,
      diff_url: str(item.diff_url),
    })
  }
  if (entries.length === 0) {
    return null
  }
  // Stable sort: entries with a bad timestamp keep their place relative to each other.
  const time = (entry: TimelineEntry) => {
    const value = new Date(entry.timestamp).getTime()
    return Number.isNaN(value) ? 0 : value
  }
  return entries
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => time(a.entry) - time(b.entry) || a.index - b.index)
    .map(({ entry }) => entry)
}

export interface Participant {
  user: string
  is_bot: boolean
  edits: number
  // Reverts this user made.
  revertsMade: number
  // Times another user reverted this user.
  revertedBy: number
  // Position in the order of first appearance. It picks the color and marker.
  index: number
}

// One summary per user, in the order they first appear in the timeline.
export function participantsOf(timeline: TimelineEntry[]): Participant[] {
  const byUser = new Map<string, Participant>()
  const get = (user: string) => {
    let participant = byUser.get(user)
    if (!participant) {
      participant = { user, is_bot: false, edits: 0, revertsMade: 0, revertedBy: 0, index: byUser.size }
      byUser.set(user, participant)
    }
    return participant
  }
  for (const entry of timeline) {
    const participant = get(entry.user)
    participant.edits += 1
    participant.is_bot ||= entry.is_bot
    if (entry.is_revert) {
      participant.revertsMade += 1
    }
  }
  for (const entry of timeline) {
    if (
      entry.is_revert &&
      entry.reverted_user &&
      entry.reverted_user !== entry.user &&
      byUser.has(entry.reverted_user)
    ) {
      get(entry.reverted_user).revertedBy += 1
    }
  }
  return [...byUser.values()]
}

// Colors and shapes for the participants. The shape keeps users apart for
// readers who do not see the color difference.
export const PARTICIPANT_STYLES = [
  { color: '#3cc8ff', marker: '●' },
  { color: '#ffc233', marker: '▲' },
  { color: '#c58cff', marker: '■' },
  { color: '#3ddc84', marker: '◆' },
  { color: '#ff8591', marker: '★' },
  { color: '#ff9440', marker: '⬟' },
  { color: '#7ee0d2', marker: '✚' },
  { color: '#e3e8ef', marker: '⬢' },
] as const

export function participantStyle(index: number): (typeof PARTICIPANT_STYLES)[number] {
  return PARTICIPANT_STYLES[Math.abs(index) % PARTICIPANT_STYLES.length]
}
