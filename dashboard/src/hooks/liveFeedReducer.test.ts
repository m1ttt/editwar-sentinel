import { describe, expect, it } from 'vitest'
import { makeAlert, makeEdit, makeStats } from '../test/fixtures'
import type { LiveMessage } from '../types'
import { initialFeedState, liveFeedReducer, MAX_EDITS, MAX_POINTS, parseMessage, type FeedState } from './liveFeedReducer'

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

describe('parseMessage', () => {
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
