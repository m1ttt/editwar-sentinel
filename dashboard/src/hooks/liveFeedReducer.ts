// Pure state logic for the live feed. It has no WebSocket code, so the tests
// call it directly with plain objects.
import type { Alert, EditEvent, GeoEvent, LiveMessage, RevertEvent, Stats } from '../types'

export const MAX_EDITS = 50
export const MAX_POINTS = 60
export const MAX_GEO = 200
// About 3 minutes of instantaneous rate samples, one per stats message (every ~2 s).
export const MAX_RATE_SAMPLES = 90
// Two stats closer than this (for example the REST answer and the first WebSocket
// message) give a noisy rate, so the second one does not make a sample.
export const MIN_RATE_INTERVAL_MS = 500

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
  // Points of the map, newest first.
  geo: GeoEvent[]
  // Edits per second between two consecutive stats messages, oldest first.
  rates: RatePoint[]
  // The last counter reading that the rates start from.
  lastCount: CounterReading | null
}

export interface RatePoint {
  // Time of the sample, in milliseconds since the epoch.
  at: number
  value: number
}

export interface CounterReading {
  total: number
  at: number
}

// A stats message with the time the browser received it. The api's
// edits_per_second is a 60 s average, so the dashboard computes its own
// instantaneous rate from total_edits and this time.
export interface TimedStatsAction {
  type: 'stats'
  data: Stats
  at?: number
}

// The list from GET /api/geo/recent. It is not a WebSocket message: App dispatches it.
export interface GeoSnapshotAction {
  type: 'geo_snapshot'
  data: GeoEvent[]
}

export type FeedAction = Exclude<LiveMessage, { type: 'stats' }> | TimedStatsAction | GeoSnapshotAction

export const initialFeedState: FeedState = {
  edits: [],
  throughput: [],
  stats: null,
  lastAlert: null,
  geo: [],
  rates: [],
  lastCount: null,
}

const MESSAGE_TYPES = ['edit', 'revert', 'alert', 'stats', 'geo']

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

// The same point can come from the snapshot and from the WebSocket.
export function geoKey(point: GeoEvent): string {
  return `${point.kind}|${point.wiki}|${point.title}|${point.timestamp}`
}

function timeOf(point: GeoEvent): number {
  const time = new Date(point.timestamp).getTime()
  return Number.isNaN(time) ? 0 : time
}

// Joins two lists of points without duplicates, newest first, at most MAX_GEO.
export function mergeGeo(current: GeoEvent[], incoming: GeoEvent[]): GeoEvent[] {
  const byKey = new Map<string, GeoEvent>()
  for (const point of [...incoming, ...current]) {
    if (Number.isFinite(point.lat) && Number.isFinite(point.lon) && !byKey.has(geoKey(point))) {
      byKey.set(geoKey(point), point)
    }
  }
  return [...byKey.values()].sort((a, b) => timeOf(b) - timeOf(a)).slice(0, MAX_GEO)
}

// Adds one instantaneous rate sample from a new counter reading.
// - The first reading only becomes the start point.
// - A lower total means the api restarted: the reading becomes the new start point.
// - A time difference below MIN_RATE_INTERVAL_MS (or zero) gives no sample.
export function addRateSample(
  state: Pick<FeedState, 'rates' | 'lastCount'>,
  reading: CounterReading,
): Pick<FeedState, 'rates' | 'lastCount'> {
  const last = state.lastCount
  if (last === null || reading.total < last.total) {
    return { rates: state.rates, lastCount: reading }
  }
  const elapsed = reading.at - last.at
  if (elapsed < MIN_RATE_INTERVAL_MS) {
    return state
  }
  const value = ((reading.total - last.total) * 1000) / elapsed
  return { rates: [...state.rates, { at: reading.at, value }].slice(-MAX_RATE_SAMPLES), lastCount: reading }
}

export function liveFeedReducer(state: FeedState, message: FeedAction): FeedState {
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
    case 'stats': {
      const next = {
        ...state,
        stats: message.data,
        throughput: [...state.throughput, message.data.edits_per_second].slice(-MAX_POINTS),
      }
      // Without a receive time there is no rate sample (for example in old tests).
      if (message.at === undefined) {
        return next
      }
      return { ...next, ...addRateSample(state, { total: message.data.total_edits, at: message.at }) }
    }
    case 'geo':
      return { ...state, geo: mergeGeo(state.geo, [message.data]) }
    case 'geo_snapshot':
      return { ...state, geo: mergeGeo(state.geo, message.data) }
    default:
      // Unknown message types do not change the state.
      return state
  }
}
