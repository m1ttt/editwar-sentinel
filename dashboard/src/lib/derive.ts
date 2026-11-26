// Values that the dashboard derives from data it already has (alerts and the
// live feed). Nothing here calls the api. Every function is pure, so the tests
// call it directly.
import type { FeedEdit } from '../hooks/liveFeedReducer'
import type { Alert, Severity } from '../types'

// ---- Severity breakdown ----

export type SeverityCounts = Record<Severity, number>

// Counts the alerts by severity. Unknown severities are not counted.
export function severityCounts(alerts: Pick<Alert, 'severity'>[]): SeverityCounts {
  const counts: SeverityCounts = { high: 0, medium: 0, low: 0 }
  for (const alert of alerts) {
    if (alert.severity in counts) {
      counts[alert.severity] += 1
    }
  }
  return counts
}

// ---- Activity per wiki ----

export interface WikiActivity {
  wiki: string
  events: number
  reverts: number
}

// Groups the rows of the live feed by wiki, most active first.
export function wikiActivity(edits: Pick<FeedEdit, 'wiki' | 'reverted'>[], limit = 6): WikiActivity[] {
  const byWiki = new Map<string, WikiActivity>()
  for (const edit of edits) {
    const row = byWiki.get(edit.wiki) ?? { wiki: edit.wiki, events: 0, reverts: 0 }
    row.events += 1
    if (edit.reverted) {
      row.reverts += 1
    }
    byWiki.set(edit.wiki, row)
  }
  return [...byWiki.values()]
    .sort((a, b) => b.events - a.events || b.reverts - a.reverts || a.wiki.localeCompare(b.wiki))
    .slice(0, limit)
}

// ---- Throughput ----

export interface ThroughputSummary {
  current: number
  peak: number
  average: number
}

export function throughputSummary(values: number[]): ThroughputSummary | null {
  if (values.length === 0) {
    return null
  }
  const total = values.reduce((sum, value) => sum + value, 0)
  return { current: values[values.length - 1], peak: Math.max(...values), average: total / values.length }
}

// A round number at or above the highest value, so the y axis has clean labels.
export function niceCeiling(value: number): number {
  if (value <= 0) {
    return 1
  }
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const step = [1, 2, 2.5, 5, 10].find((factor) => factor * magnitude >= value) as number
  return step * magnitude
}

export interface ChartGeometry {
  line: string
  area: string
  max: number
  // Position of the last point, for the marker.
  last: { x: number; y: number }
}

// Space above the peak, so a flat line does not touch the top of the chart.
export const CHART_HEADROOM = 1.2

// SVG paths for the area chart. Zero is at the bottom and "max" at the top.
export function chartGeometry(values: number[], width: number, height: number): ChartGeometry | null {
  if (values.length < 2) {
    return null
  }
  const max = niceCeiling(Math.max(...values) * CHART_HEADROOM)
  const step = width / (values.length - 1)
  const points = values.map((value, index) => ({
    x: index * step,
    y: height - (Math.max(value, 0) / max) * height,
  }))
  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
  const area = `${line} L${width.toFixed(1)},${height.toFixed(1)} L0.0,${height.toFixed(1)} Z`
  return { line, area, max, last: points[points.length - 1] }
}

// ---- Time ----

// Length of the chart window: "45 s" or "2 min 58 s".
export function formatSpan(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return minutes > 0 ? `${minutes} min ${String(rest).padStart(2, '0')} s` : `${rest} s`
}
