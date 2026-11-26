// Small display helpers shared by the panels.
import type { Severity } from '../types'

const numberFormat = new Intl.NumberFormat('es-MX')
const deltaFormat = new Intl.NumberFormat('es-MX', { signDisplay: 'exceptZero' })

export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

// "+212", "-1,840" or "0".
export function formatDelta(value: number): string {
  return deltaFormat.format(value)
}

// "21:04:12" in the local time of the browser.
export function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return '--:--:--'
  }
  return date.toLocaleTimeString('es-MX', { hour12: false })
}

export function articleUrl(serverUrl: string, title: string): string {
  return `${serverUrl}/wiki/${encodeURIComponent(title.replace(/ /g, '_'))}`
}

// A title of "*" means the alert covers the whole wiki (for example bot_spike).
export function alertTitle(title: string, wiki: string): string {
  return title === '*' ? `Toda la wiki (${wiki})` : title
}

export const SEVERITY_LABELS: Record<Severity, string> = {
  high: 'alta',
  medium: 'media',
  low: 'baja',
}

// The evidence keys are not fixed, so show numbers and strings as they are,
// short string lists joined, and longer lists as a count. The timeline is left out.
export function summarizeEvidence(evidence: Record<string, unknown> | null | undefined): string {
  const parts: string[] = []
  for (const [key, value] of Object.entries(evidence ?? {})) {
    // The edit war timeline has its own view (EditWarTimeline).
    if (key === 'timeline' || key === 'timeline_truncated') {
      continue
    }
    if (typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean') {
      parts.push(`${key}: ${value}`)
    } else if (Array.isArray(value)) {
      const shortList = value.length <= 3 && value.every((item) => typeof item === 'string')
      parts.push(shortList ? `${key}: ${value.join(', ')}` : `${key}: ${value.length}`)
    }
  }
  return parts.join(' · ')
}
