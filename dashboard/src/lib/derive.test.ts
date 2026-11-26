import { describe, expect, it } from 'vitest'
import { chartGeometry, formatSpan, niceCeiling, severityCounts, throughputSummary, wikiActivity } from './derive'

describe('severityCounts', () => {
  it('counts each severity and skips unknown values', () => {
    const alerts = [{ severity: 'high' }, { severity: 'high' }, { severity: 'low' }, { severity: 'other' }] as {
      severity: 'high' | 'medium' | 'low'
    }[]
    expect(severityCounts(alerts)).toEqual({ high: 2, medium: 0, low: 1 })
  })
})

describe('wikiActivity', () => {
  it('groups rows by wiki, most active first, with reverts', () => {
    const rows = [
      { wiki: 'eswiki', reverted: false },
      { wiki: 'enwiki', reverted: true },
      { wiki: 'enwiki', reverted: false },
      { wiki: 'dewiki', reverted: false },
      { wiki: 'frwiki', reverted: true },
    ]
    expect(wikiActivity(rows)).toEqual([
      { wiki: 'enwiki', events: 2, reverts: 1 },
      { wiki: 'frwiki', events: 1, reverts: 1 },
      { wiki: 'dewiki', events: 1, reverts: 0 },
      { wiki: 'eswiki', events: 1, reverts: 0 },
    ])
  })

  it('keeps only the first rows', () => {
    const rows = ['a', 'b', 'c'].map((wiki) => ({ wiki, reverted: false }))
    expect(wikiActivity(rows, 2).map((row) => row.wiki)).toEqual(['a', 'b'])
  })
})

describe('throughputSummary', () => {
  it('is null without values', () => {
    expect(throughputSummary([])).toBeNull()
  })

  it('gives the last, highest and average value', () => {
    expect(throughputSummary([2, 8, 5])).toEqual({ current: 5, peak: 8, average: 5 })
  })
})

describe('niceCeiling', () => {
  it.each([
    [0, 1],
    [0.7, 1],
    [9.12, 10],
    [12, 20],
    [21, 25],
    [41.7, 50],
    [60, 100],
    [100, 100],
  ])('rounds %d up to %d', (value, expected) => {
    expect(niceCeiling(value)).toBe(expected)
  })
})

describe('chartGeometry', () => {
  it('needs at least two values', () => {
    expect(chartGeometry([4], 100, 50)).toBeNull()
  })

  it('scales the values to the box, with zero at the bottom and room above the peak', () => {
    // The peak is 10, so the top of the axis is niceCeiling(12) = 20.
    const geometry = chartGeometry([0, 5, 10], 100, 50)
    expect(geometry).toEqual({
      line: 'M0.0,50.0 L50.0,37.5 L100.0,25.0',
      area: 'M0.0,50.0 L50.0,37.5 L100.0,25.0 L100.0,50.0 L0.0,50.0 Z',
      max: 20,
      last: { x: 100, y: 25 },
    })
  })

  it('draws a negative value at zero', () => {
    expect(chartGeometry([-1, 1], 10, 10)?.line).toBe('M0.0,10.0 L10.0,5.0')
  })
})

describe('formatSpan', () => {
  it('shows seconds, then minutes and seconds', () => {
    expect(formatSpan(45.4)).toBe('45 s')
    expect(formatSpan(178)).toBe('2 min 58 s')
    expect(formatSpan(120)).toBe('2 min 00 s')
    expect(formatSpan(-3)).toBe('0 s')
  })
})
