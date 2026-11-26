import { describe, expect, it } from 'vitest'
import { makeAlert, makeEdit, makeGeo, makeStats } from '../test/fixtures'
import type { LiveMessage } from '../types'
import {
  initialFeedState,
  liveFeedReducer,
  MAX_EDITS,
  addRateSample,
  MAX_GEO,
  MAX_POINTS,
  MAX_RATE_SAMPLES,
  mergeGeo,
  MIN_RATE_INTERVAL_MS,
  parseMessage,
  type FeedState,
} from './liveFeedReducer'

function applyAll(messages: LiveMessage[], state: FeedState = initialFeedState): FeedState {
  return messages.reduce(liveFeedReducer, state)
}

describe('liveFeedReducer', () => {
  it('puts the newest edit first', () => {
    const state = applyAll([
      { type: 'edit', data: makeEdit({ event_id: 'a' }) },
      { type: 'edit', data: makeEdit({ event_id: 'b' }) },
    ])
    expect(state.edits.map((edit) => edit.event_id)).toEqual(['b', 'a'])
    expect(state.edits[0].reverted).toBe(false)
  })

  it(`keeps at most ${MAX_EDITS} edits`, () => {
    const messages: LiveMessage[] = Array.from({ length: MAX_EDITS + 10 }, (_, index) => ({
      type: 'edit',
      data: makeEdit({ event_id: `e${index}` }),
    }))
    const state = applyAll(messages)
    expect(state.edits).toHaveLength(MAX_EDITS)
    expect(state.edits[0].event_id).toBe(`e${MAX_EDITS + 9}`)
  })

  it('flags the edit that a revert names', () => {
    const state = applyAll([
      { type: 'edit', data: makeEdit({ event_id: 'a' }) },
      { type: 'edit', data: makeEdit({ event_id: 'b' }) },
      {
        type: 'revert',
        data: {
          event_id: 'a',
          wiki: 'enwiki',
          title: 'Apache Kafka',
          user: 'Editor_A',
          timestamp: '2026-11-25T21:04:13+00:00',
          reason: 'comment',
          server_url: 'https://en.wikipedia.org',
        },
      },
    ])
    expect(state.edits.find((edit) => edit.event_id === 'a')?.reverted).toBe(true)
    expect(state.edits.find((edit) => edit.event_id === 'b')?.reverted).toBe(false)
  })

  it('stores the size change of an edit', () => {
    const state = applyAll([{ type: 'edit', data: makeEdit({ old_len: 2000, new_len: 160 }) }])
    expect(state.edits[0].delta).toBe(-1840)
  })

  it('adds a revert row when the edit is not in the list', () => {
    const before = applyAll([{ type: 'edit', data: makeEdit({ event_id: 'a' }) }])
    const after = liveFeedReducer(before, {
      type: 'revert',
      data: {
        event_id: 'zzz',
        wiki: 'eswiki',
        title: 'Kubernetes',
        user: 'Editor_B',
        timestamp: '2026-11-25T21:04:13+00:00',
        reason: 'size_restore',
        server_url: 'https://es.wikipedia.org',
      },
    })
    expect(after.edits.map((edit) => edit.event_id)).toEqual(['zzz', 'a'])
    expect(after.edits[0]).toMatchObject({
      wiki: 'eswiki',
      title: 'Kubernetes',
      user: 'Editor_B',
      reverted: true,
      delta: null,
      change_type: 'revert',
    })
  })

  it('fills in a revert row when its edit arrives later', () => {
    const state = applyAll([
      {
        type: 'revert',
        data: {
          event_id: 'a',
          wiki: 'enwiki',
          title: 'Apache Kafka',
          user: 'Editor_A',
          timestamp: '2026-11-25T21:04:13+00:00',
          reason: 'comment',
          server_url: 'https://en.wikipedia.org',
        },
      },
      { type: 'edit', data: makeEdit({ event_id: 'b' }) },
      { type: 'edit', data: makeEdit({ event_id: 'a', old_len: 500, new_len: 300 }) },
    ])
    expect(state.edits.map((edit) => edit.event_id)).toEqual(['b', 'a'])
    expect(state.edits[1]).toMatchObject({ reverted: true, delta: -200, change_type: 'edit' })
  })

  it('stores the last alert', () => {
    const alert = makeAlert()
    expect(liveFeedReducer(initialFeedState, { type: 'alert', data: alert }).lastAlert).toBe(alert)
  })

  it('stores stats and adds a throughput point', () => {
    const state = applyAll([
      { type: 'stats', data: makeStats({ edits_per_second: 10 }) },
      { type: 'stats', data: makeStats({ edits_per_second: 20 }) },
    ])
    expect(state.stats?.edits_per_second).toBe(20)
    expect(state.throughput).toEqual([10, 20])
  })

  it(`keeps at most ${MAX_POINTS} throughput points`, () => {
    const messages: LiveMessage[] = Array.from({ length: MAX_POINTS + 5 }, (_, index) => ({
      type: 'stats',
      data: makeStats({ edits_per_second: index }),
    }))
    const state = applyAll(messages)
    expect(state.throughput).toHaveLength(MAX_POINTS)
    expect(state.throughput.at(-1)).toBe(MAX_POINTS + 4)
  })

  it('returns the same state for an unknown message type', () => {
    const unknown = { type: 'other', data: {} } as unknown as LiveMessage
    expect(liveFeedReducer(initialFeedState, unknown)).toBe(initialFeedState)
  })
})

describe('instantaneous rate', () => {
  const T0 = Date.UTC(2026, 10, 25, 21, 0, 0)

  function stats(total: number, seconds: number) {
    return { type: 'stats' as const, data: makeStats({ total_edits: total }), at: T0 + seconds * 1000 }
  }

  it('uses the first reading only as the start point', () => {
    const state = liveFeedReducer(initialFeedState, stats(1000, 0))
    expect(state.rates).toEqual([])
    expect(state.lastCount).toEqual({ total: 1000, at: T0 })
  })

  it('divides the new edits by the time between two readings', () => {
    const state = [stats(1000, 0), stats(1030, 2), stats(1040, 4)].reduce(liveFeedReducer, initialFeedState)
    expect(state.rates).toEqual([
      { at: T0 + 2000, value: 15 },
      { at: T0 + 4000, value: 5 },
    ])
  })

  it('starts again after a counter reset (api restart)', () => {
    const state = [stats(5000, 0), stats(5020, 2), stats(10, 4), stats(30, 6)].reduce(liveFeedReducer, initialFeedState)
    expect(state.rates.map((point) => point.value)).toEqual([10, 10])
    expect(state.lastCount).toEqual({ total: 30, at: T0 + 6000 })
  })

  it('skips a reading with no time difference or one that is too close', () => {
    const first = liveFeedReducer(initialFeedState, stats(1000, 0))
    expect(liveFeedReducer(first, stats(1010, 0)).rates).toEqual([])
    const close = addRateSample(first, { total: 1010, at: T0 + MIN_RATE_INTERVAL_MS - 1 })
    expect(close).toBe(first)
    // The skipped reading does not move the start point, so the next rate covers both.
    const next = liveFeedReducer(liveFeedReducer(first, stats(1010, 0.2)), stats(1040, 2))
    expect(next.rates).toEqual([{ at: T0 + 2000, value: 20 }])
  })

  it('gives no sample for stats without a receive time', () => {
    const state = applyAll([
      { type: 'stats', data: makeStats({ total_edits: 1 }) },
      { type: 'stats', data: makeStats({ total_edits: 2 }) },
    ])
    expect(state.rates).toEqual([])
    expect(state.lastCount).toBeNull()
  })

  it(`keeps at most ${MAX_RATE_SAMPLES} samples`, () => {
    const readings = Array.from({ length: MAX_RATE_SAMPLES + 11 }, (_, index) => stats(index * 10, index * 2))
    const state = readings.reduce(liveFeedReducer, initialFeedState)
    expect(state.rates).toHaveLength(MAX_RATE_SAMPLES)
    expect(state.rates.at(-1)).toEqual({ at: T0 + (MAX_RATE_SAMPLES + 10) * 2000, value: 5 })
  })
})

describe('geo points', () => {
  it('puts the newest geo message first', () => {
    const state = applyAll([
      { type: 'geo', data: makeGeo({ title: 'A', timestamp: '2026-11-25T21:00:00Z' }) },
      { type: 'geo', data: makeGeo({ title: 'B', timestamp: '2026-11-25T21:00:05Z' }) },
    ])
    expect(state.geo.map((point) => point.title)).toEqual(['B', 'A'])
  })

  it('merges the snapshot from the api with the live points, without duplicates', () => {
    const live = makeGeo({ title: 'Live', timestamp: '2026-11-25T21:00:10Z' })
    const old = makeGeo({ title: 'Old', timestamp: '2026-11-25T20:59:00Z' })
    const before = applyAll([{ type: 'geo', data: live }])
    const state = liveFeedReducer(before, { type: 'geo_snapshot', data: [live, old] })
    expect(state.geo.map((point) => point.title)).toEqual(['Live', 'Old'])
  })

  it('keeps a revert and an alert on the same article as two points', () => {
    const revert = makeGeo()
    const alert = makeGeo({ kind: 'alert', severity: 'high', alert_kind: 'revert_war' })
    expect(applyAll([{ type: 'geo', data: revert }, { type: 'geo', data: alert }]).geo).toHaveLength(2)
  })

  it(`keeps at most ${MAX_GEO} points, the newest ones`, () => {
    const points = Array.from({ length: MAX_GEO + 20 }, (_, index) =>
      makeGeo({ title: `p${index}`, timestamp: new Date(Date.UTC(2026, 10, 25, 20, 0, index)).toISOString() }),
    )
    const state = liveFeedReducer(initialFeedState, { type: 'geo_snapshot', data: points })
    expect(state.geo).toHaveLength(MAX_GEO)
    expect(state.geo[0].title).toBe(`p${MAX_GEO + 19}`)
  })

  it('drops points without valid coordinates and sorts a bad timestamp last', () => {
    const merged = mergeGeo(
      [],
      [
        makeGeo({ title: 'no-time', timestamp: 'later' }),
        makeGeo({ title: 'bad', lat: Number.NaN }),
        makeGeo({ title: 'ok' }),
      ],
    )
    expect(merged.map((point) => point.title)).toEqual(['ok', 'no-time'])
  })
})

describe('parseMessage', () => {
  it('parses a geo message', () => {
    const geo = makeGeo()
    expect(parseMessage(JSON.stringify({ type: 'geo', data: geo }))).toEqual({ type: 'geo', data: geo })
  })

  it('does not accept a snapshot from the WebSocket', () => {
    expect(parseMessage(JSON.stringify({ type: 'geo_snapshot', data: {} }))).toBeNull()
  })

  it('parses a valid message', () => {
    const edit = makeEdit()
    expect(parseMessage(JSON.stringify({ type: 'edit', data: edit }))).toEqual({ type: 'edit', data: edit })
  })

  it.each([
    ['not JSON', '{oops'],
    ['an unknown type', JSON.stringify({ type: 'other', data: {} })],
    ['missing data', JSON.stringify({ type: 'edit' })],
    ['a JSON array', '[]'],
    ['a JSON null', 'null'],
  ])('returns null for %s', (_label, raw) => {
    expect(parseMessage(raw)).toBeNull()
  })

  it('returns null for binary data', () => {
    expect(parseMessage(new ArrayBuffer(4))).toBeNull()
  })
})
