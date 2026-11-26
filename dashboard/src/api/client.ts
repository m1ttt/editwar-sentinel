// All HTTP calls to the api. URLs are relative, so the same build works behind
// the Vite dev proxy, behind nginx in Docker, and behind the Kubernetes ingress.
import type { Alert, AlertStatus, GeoEvent, Rule, RuleInput, RuleKind, Stats, VersionInfo } from '../types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface ValidationIssue {
  loc?: unknown[]
  msg?: string
}

// FastAPI sends "detail" as a string, or as a list of {loc, msg} for a 422.
export function formatDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail
      .map((issue: ValidationIssue) => {
        const field = Array.isArray(issue.loc) ? issue.loc.filter((part) => part !== 'body').join('.') : ''
        const message = issue.msg ?? ''
        return field ? `${field}: ${message}` : message
      })
      .join('; ')
  }
  return null
}

async function readError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (body !== null && typeof body === 'object' && 'detail' in body) {
      const text = formatDetail(body.detail)
      if (text) {
        return text
      }
    }
  } catch {
    // The body is not JSON (for example a 502 page from nginx).
  }
  return `HTTP ${response.status}`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (init.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response))
  }
  // A 204 (for example after DELETE) has an empty body.
  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function getVersion(): Promise<VersionInfo> {
  return request<VersionInfo>('/api/version')
}

export function getStats(): Promise<Stats> {
  return request<Stats>('/api/stats')
}

// ---- Rules ----

export function listRules(): Promise<Rule[]> {
  return request<Rule[]>('/api/rules')
}

export function getRule(id: string): Promise<Rule> {
  return request<Rule>(`/api/rules/${encodeURIComponent(id)}`)
}

export function createRule(input: RuleInput): Promise<Rule> {
  return request<Rule>('/api/rules', { method: 'POST', body: JSON.stringify(input) })
}

export function updateRule(id: string, input: RuleInput): Promise<Rule> {
  return request<Rule>(`/api/rules/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(input) })
}

export function deleteRule(id: string): Promise<void> {
  return request<void>(`/api/rules/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// ---- Alerts ----

export interface AlertFilters {
  status?: AlertStatus
  kind?: RuleKind
  wiki?: string
  limit?: number
  offset?: number
}

// Builds "?status=open&limit=50". Empty filters stay out of the URL.
export function alertsQuery(filters: AlertFilters): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') {
      params.set(key, String(value))
    }
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

export async function listAlerts(filters: AlertFilters = {}): Promise<Alert[]> {
  // Accept a plain list or a paginated object {items: [...]}.
  const data = await request<Alert[] | { items: Alert[] }>(`/api/alerts${alertsQuery(filters)}`)
  return Array.isArray(data) ? data : data.items
}

export function acknowledgeAlert(id: string, user: string): Promise<Alert> {
  return request<Alert>(`/api/alerts/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status: 'acknowledged', user }),
  })
}

export function dismissAlert(id: string): Promise<Alert> {
  return request<Alert>(`/api/alerts/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status: 'dismissed' }),
  })
}

export function deleteAlert(id: string): Promise<void> {
  return request<void>(`/api/alerts/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// ---- Map ----

export const GEO_LIMIT = 200

// Recent reverts and alerts with coordinates, newest first. The api keeps them in
// memory. An api without this endpoint answers 404, which means "no points yet".
export async function listRecentGeo(limit: number = GEO_LIMIT): Promise<GeoEvent[]> {
  try {
    return await request<GeoEvent[]>(`/api/geo/recent?limit=${limit}`)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return []
    }
    throw error
  }
}
