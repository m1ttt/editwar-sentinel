import { describe, expect, it } from 'vitest'
import {
  chartGeometry,
  formatPercent,
  formatUptime,
  niceCeiling,
  revertRate,
  severityCounts,
  threatBand,
  threatLevel,
  throughputSummary,
  uptimeSince,
  wikiActivity,
} from './derive'

describe('revertRate', () => {
  it('divides reverts by edits', () => {
    expect(revertRate({ total_edits: 200, total_reverts: 3 })).toBe(0.015)
  })

  it('is zero before the first edit', () => {
    expect(revertRate({ total_edits: 0, total_reverts: 0 })).toBe(0)
  })

  it('formats as a percent with two decimals', () => {
    expect(formatPercent(0.00568)).toBe('0.57 %')
  })
})

describe('threatLevel', () => {
  it.each([
    [0, 'low'],
    [24, 'low'],
    [25, 'guarded'],
    [49, 'guarded'],
    [50, 'high'],
    [74, 'high'],
    [75, 'critical'],
    [100, 'critical'],
  ] as const)('puts score %i in band %s', (score, band) => {
    expect(threatBand(score)).toBe(band)
  })

  it('is low with no alerts and no reverts', () => {
    expect(threatLevel({ open_alerts: 0, total_edits: 1000, total_reverts: 0 })).toEqual({
      score: 0,
      band: 'low',
      label: 'Bajo',
      alertPoints: 0,
      ratePoints: 0,
    })
  })

  it('adds 6 points per open alert and 20 points for a 1 % revert rate', () => {
    const level = threatLevel({ open_alerts: 3, total_edits: 1000, total_reverts: 10 })
    expect(level.alertPoints).toBe(18)
    expect(level.ratePoints).toBe(20)
    expect(level.score).toBe(38)
    expect(level.label).toBe('Moderado')
  })

  it('caps both parts, so the score never passes 100', () => {
    const level = threatLevel({ open_alerts: 40, total_edits: 100, total_reverts: 50 })
    expect(level).toMatchObject({ score: 100, band: 'critical', label: 'Crítico', alertPoints: 60, ratePoints: 40 })
  })

  it('ignores a negative alert count', () => {
    expect(threatLevel({ open_alerts: -2, total_edits: 0, total_reverts: 0 }).score).toBe(0)
  })

  it('uses the high band between 50 and 74', () => {
    expect(threatLevel({ open_alerts: 9, total_edits: 0, total_reverts: 0 })).toMatchObject({ score: 54, label: 'Alto' })
  })
})

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

describe('formatUptime', () => {
  it('shows hours, minutes and seconds', () => {
    expect(formatUptime(3_723_000)).toBe('01:02:03')
  })

  it('adds days after 24 hours', () => {
    expect(formatUptime(2 * 86_400_000 + 5_000)).toBe('2 d 00:00:05')
  })

  it('shows dashes for an invalid duration', () => {
    expect(formatUptime(-1)).toBe('--:--:--')
    expect(formatUptime(Number.NaN)).toBe('--:--:--')
  })

  it('counts from stats.started_at', () => {
    const now = new Date('2026-11-25T21:00:00Z').getTime()
    expect(uptimeSince('2026-11-25T20:00:00+00:00', now)).toBe('01:00:00')
    expect(uptimeSince('not a date', now)).toBe('--:--:--')
  })
})
