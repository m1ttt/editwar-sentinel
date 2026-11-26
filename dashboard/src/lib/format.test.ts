import { describe, expect, it } from 'vitest'
import { alertTitle, articleUrl, formatDelta, formatNumber, formatTime, summarizeEvidence } from './format'

describe('format helpers', () => {
  it('formats numbers and deltas', () => {
    expect(formatNumber(12345)).toBe('12,345')
    expect(formatDelta(212)).toBe('+212')
    expect(formatDelta(-1840)).toBe('-1,840')
    expect(formatDelta(0)).toBe('0')
  })

  it('formats a time and rejects bad input', () => {
    expect(formatTime('2026-11-25T21:04:12+00:00')).toMatch(/^\d{2}:\d{2}:\d{2}$/)
    expect(formatTime('not a date')).toBe('--:--:--')
  })

  it('builds article URLs', () => {
    expect(articleUrl('https://es.wikipedia.org', 'Guerra de edición')).toBe(
      'https://es.wikipedia.org/wiki/Guerra_de_edici%C3%B3n',
    )
  })

  it('names wiki-wide alerts', () => {
    expect(alertTitle('*', 'enwiki')).toBe('Toda la wiki (enwiki)')
    expect(alertTitle('Kubernetes', 'enwiki')).toBe('Kubernetes')
  })

  it('summarizes evidence of any shape', () => {
    expect(
      summarizeEvidence({
        reverts: 4,
        users: ['a', 'b'],
        event_ids: ['1', '2', '3', '4'],
        wiki_wide: true,
        nested: { skip: 1 },
      }),
    ).toBe('reverts: 4 · users: a, b · event_ids: 4 · wiki_wide: true')
    expect(summarizeEvidence(null)).toBe('')
    expect(summarizeEvidence({ reverts: 2, timeline: [{ user: 'a' }], timeline_truncated: false })).toBe('reverts: 2')
  })
})
