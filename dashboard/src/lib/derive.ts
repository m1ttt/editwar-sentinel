// Values that the dashboard derives from data it already has (stats and the
// live feed). Nothing here calls the api. Every function is pure, so the tests
// call it directly.
import type { FeedEdit } from '../hooks/liveFeedReducer'
import type { Alert, Severity, Stats } from '../types'

// ---- Revert rate ----

// Reverts per edit since the api started, as a fraction (0.0057 = 0.57 %).
export function revertRate(stats: Pick<Stats, 'total_edits' | 'total_reverts'>): number {
  return stats.total_edits > 0 ? stats.total_reverts / stats.total_edits : 0
}

// "0.57 %". Two decimals, because a normal revert rate is below 1 %.
export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(2)} %`
}

// ---- Threat level ----

export type ThreatBand = 'low' | 'guarded' | 'high' | 'critical'

export interface ThreatLevel {
  // 0 to 100.
  score: number
  band: ThreatBand
  label: string
  // The two parts of the score, so the panel can show where it comes from.
  alertPoints: number
  ratePoints: number
}

// Open alerts give up to 60 points (6 per alert, 10 alerts or more is the maximum).
export const ALERT_POINTS = 6
export const MAX_ALERT_POINTS = 60
// The revert rate gives up to 40 points. A rate of 2 % or more is the maximum.
export const RATE_CEILING = 0.02
export const MAX_RATE_POINTS = 40

export const THREAT_LABELS: Record<ThreatBand, string> = {
  low: 'Bajo',
  guarded: 'Moderado',
  high: 'Alto',
  critical: 'Crítico',
}

export function threatBand(score: number): ThreatBand {
  if (score >= 75) return 'critical'
  if (score >= 50) return 'high'
  if (score >= 25) return 'guarded'
  return 'low'
}

// The score uses only /api/stats: the open alert count and the revert rate.
export function threatLevel(stats: Pick<Stats, 'open_alerts' | 'total_edits' | 'total_reverts'>): ThreatLevel {
  const alertPoints = Math.min(Math.max(stats.open_alerts, 0) * ALERT_POINTS, MAX_ALERT_POINTS)
  const ratePoints = Math.min(revertRate(stats) / RATE_CEILING, 1) * MAX_RATE_POINTS
  const score = Math.round(alertPoints + ratePoints)
  const band = threatBand(score)
  return { score, band, label: THREAT_LABELS[band], alertPoints, ratePoints }
}

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

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

// "04:05:06" or "3 d 04:05:06". A negative or invalid duration shows as "--:--:--".
export function formatUptime(milliseconds: number): string {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) {
    return '--:--:--'
  }
  const totalSeconds = Math.floor(milliseconds / 1000)
  const days = Math.floor(totalSeconds / 86_400)
  const hours = Math.floor((totalSeconds % 86_400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const clock = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
  return days > 0 ? `${days} d ${clock}` : clock
}

// Time since the api started, from stats.started_at.
export function uptimeSince(startedAt: string, now: number): string {
  return formatUptime(now - new Date(startedAt).getTime())
}
