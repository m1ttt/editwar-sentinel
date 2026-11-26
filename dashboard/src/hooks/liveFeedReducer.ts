// Pure state logic for the live feed. It has no WebSocket code, so the tests
// call it directly with plain objects.
import type { Alert, EditEvent, LiveMessage, RevertEvent, Stats } from '../types'

export const MAX_EDITS = 50
export const MAX_POINTS = 60

// A row of the live list. "reverted" becomes true when a revert message names it.
// "delta" is the size change in bytes, or null when the size is not known.
export interface FeedEdit extends EditEvent {
  reverted: boolean
  delta: number | null
}

export interface FeedState {
  edits: FeedEdit[]
  throughput: number[]
  stats: Stats | null
  lastAlert: Alert | null
}

export const initialFeedState: FeedState = {
  edits: [],
  throughput: [],
  stats: null,
  lastAlert: null,
}

const MESSAGE_TYPES = ['edit', 'revert', 'alert', 'stats']

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

// Turns raw WebSocket text into a message, or null if the text is not valid.
export function parseMessage(raw: unknown): LiveMessage | null {
  if (typeof raw !== 'string') {
    return null
  }
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return null
  }
  if (!isRecord(value) || !isRecord(value.data) || !MESSAGE_TYPES.includes(String(value.type))) {
    return null
  }
  return value as LiveMessage
}

// The api samples edits (about 15 per second), so the edit that a revert names
// is often not in the list. Then the revert becomes its own row, with no size.
function revertRow(revert: RevertEvent): FeedEdit {
  return {
    event_id: revert.event_id,
    wiki: revert.wiki,
    title: revert.title,
    user: revert.user,
    is_bot: false,
    timestamp: revert.timestamp,
    comment: revert.reason,
    old_len: 0,
    new_len: 0,
    rev_id: 0,
    old_rev_id: 0,
    server_url: revert.server_url,
    namespace: 0,
    change_type: 'revert',
    reverted: true,
    delta: null,
  }
}

// Newest first, and never more than MAX_EDITS rows.
function prepend(edits: FeedEdit[], row: FeedEdit): FeedEdit[] {
  return [row, ...edits].slice(0, MAX_EDITS)
}

export function liveFeedReducer(state: FeedState, message: LiveMessage): FeedState {
  switch (message.type) {
    case 'edit': {
      const edit = message.data
      const row: FeedEdit = { ...edit, reverted: false, delta: edit.new_len - edit.old_len }
      // The revert can arrive first. Then the edit fills in that row and keeps the flag.
      const existing = state.edits.find((item) => item.event_id === edit.event_id)
      if (existing) {
        return {
          ...state,
          edits: state.edits.map((item) => (item === existing ? { ...row, reverted: existing.reverted } : item)),
        }
      }
      return { ...state, edits: prepend(state.edits, row) }
    }
    case 'revert': {
      // A revert has the event_id of the edit that the detector classified.
      const id = message.data.event_id
      if (!state.edits.some((edit) => edit.event_id === id)) {
        return { ...state, edits: prepend(state.edits, revertRow(message.data)) }
      }
      return {
        ...state,
        edits: state.edits.map((edit) => (edit.event_id === id ? { ...edit, reverted: true } : edit)),
      }
    }
    case 'alert':
      return { ...state, lastAlert: message.data }
    case 'stats':
      return {
        ...state,
        stats: message.data,
        throughput: [...state.throughput, message.data.edits_per_second].slice(-MAX_POINTS),
      }
    default:
      // Unknown message types do not change the state.
      return state
  }
}
