import { describe, expect, it } from 'vitest'
import { makeTimeline, makeTimelineEntry } from '../test/fixtures'
import { historyUrl, participantsOf, participantStyle, PARTICIPANT_STYLES, resolveHistoryUrl, timelineOf } from './wiki'

describe('historyUrl', () => {
  it('builds the history page from an article URL', () => {
    expect(historyUrl('https://en.wikipedia.org/wiki/Kubernetes')).toBe(
      'https://en.wikipedia.org/w/index.php?title=Kubernetes&action=history',
    )
  })

  it('keeps encoded titles and spaces as underscores', () => {
    expect(historyUrl('https://es.wikipedia.org/wiki/Guerra_de_edici%C3%B3n')).toBe(
      'https://es.wikipedia.org/w/index.php?title=Guerra_de_edici%C3%B3n&action=history',
    )
    expect(historyUrl('https://en.wikipedia.org/wiki/Docker (software)')).toBe(
      'https://en.wikipedia.org/w/index.php?title=Docker_%28software%29&action=history',
    )
    expect(historyUrl('https://en.wikipedia.org/wiki/AC%2FDC')).toBe(
      'https://en.wikipedia.org/w/index.php?title=AC%2FDC&action=history',
    )
  })

  it('keeps a title that is not valid percent encoding', () => {
    expect(historyUrl('https://en.wikipedia.org/wiki/100%25_Bad%')).toBe(
      'https://en.wikipedia.org/w/index.php?title=100%2525_Bad%25&action=history',
    )
  })

  it('returns null for URLs that are not article pages', () => {
    expect(historyUrl(undefined)).toBeNull()
    expect(historyUrl('')).toBeNull()
    expect(historyUrl('not a url')).toBeNull()
    expect(historyUrl('https://en.wikipedia.org/')).toBeNull()
    expect(historyUrl('https://en.wikipedia.org/wiki/*')).toBeNull()
  })
})

describe('resolveHistoryUrl', () => {
  it('prefers the history_url from the api', () => {
    expect(resolveHistoryUrl({ history_url: 'https://h', page_url: 'https://en.wikipedia.org/wiki/X' })).toBe(
      'https://h',
    )
  })

  it('falls back to page_url when history_url is missing or empty', () => {
    const expected = 'https://en.wikipedia.org/w/index.php?title=X&action=history'
    expect(resolveHistoryUrl({ page_url: 'https://en.wikipedia.org/wiki/X' })).toBe(expected)
    expect(resolveHistoryUrl({ history_url: '', page_url: 'https://en.wikipedia.org/wiki/X' })).toBe(expected)
  })

  it('has no history for wiki-wide alerts', () => {
    expect(resolveHistoryUrl({ title: '*', page_url: 'https://en.wikipedia.org/wiki/X' })).toBeNull()
    expect(resolveHistoryUrl({ history_url: null, page_url: 'https://en.wikipedia.org/wiki/X' })).toBeNull()
  })
})

describe('timelineOf', () => {
  it('returns null without a timeline', () => {
    expect(timelineOf(undefined)).toBeNull()
    expect(timelineOf({ reverts: 3 })).toBeNull()
    expect(timelineOf({ timeline: 'x' })).toBeNull()
    expect(timelineOf({ timeline: [] })).toBeNull()
    expect(timelineOf({ timeline: [null, { user: 3 }] })).toBeNull()
  })

  it('fills missing fields with safe defaults', () => {
    const [entry] = timelineOf({
      timeline: [{ user: 'A', old_len: 10, new_len: 4, revert_reason: 'other', reverted_user: '' }],
    })!
    expect(entry).toMatchObject({
      event_id: '0',
      user: 'A',
      is_bot: false,
      comment: '',
      rev_id: 0,
      size_delta: -6,
      is_revert: false,
      revert_reason: null,
      reverted_user: null,
      diff_url: '',
    })
  })

  it('sorts oldest first and keeps the order of equal or bad times', () => {
    const timeline = makeTimeline()
    const shuffled = [timeline[2], timeline[0], timeline[3], timeline[1]]
    expect(timelineOf({ timeline: shuffled })!.map((entry) => entry.event_id)).toEqual(['t1', 't2', 't3', 't4'])
    const bad = [
      makeTimelineEntry({ event_id: 'x', timestamp: '?' }),
      makeTimelineEntry({ event_id: 'y', timestamp: '?' }),
    ]
    expect(timelineOf({ timeline: bad })!.map((entry) => entry.event_id)).toEqual(['x', 'y'])
  })
})

describe('participantsOf', () => {
  it('counts edits, reverts made and times reverted per user', () => {
    expect(participantsOf(makeTimeline())).toEqual([
      { user: 'Editor_B', is_bot: false, edits: 2, revertsMade: 1, revertedBy: 1, index: 0 },
      { user: 'Editor_C', is_bot: false, edits: 1, revertsMade: 1, revertedBy: 1, index: 1 },
      { user: 'TidyBot', is_bot: true, edits: 1, revertsMade: 0, revertedBy: 0, index: 2 },
    ])
  })

  it('ignores self reverts and users outside the timeline', () => {
    const timeline = [
      makeTimelineEntry({ user: 'A', is_revert: true, reverted_user: 'A' }),
      makeTimelineEntry({ user: 'A', is_revert: true, reverted_user: 'Ghost' }),
    ]
    expect(participantsOf(timeline)).toEqual([
      { user: 'A', is_bot: false, edits: 2, revertsMade: 2, revertedBy: 0, index: 0 },
    ])
  })

  it('gives each position a color and marker, wrapping around', () => {
    expect(participantStyle(0)).toBe(PARTICIPANT_STYLES[0])
    expect(participantStyle(PARTICIPANT_STYLES.length + 1)).toBe(PARTICIPANT_STYLES[1])
  })
})
