// Sample objects with the same shape as the api JSON.
import { vi } from 'vitest'
import type { Alert, EditEvent, GeoEvent, Rule, Stats } from '../types'

export function makeEdit(overrides: Partial<EditEvent> = {}): EditEvent {
  return {
    event_id: 'e1',
    wiki: 'enwiki',
    title: 'Apache Kafka',
    user: 'Editor_A',
    is_bot: false,
    timestamp: '2026-11-25T21:04:12+00:00',
    comment: 'copyedit',
    old_len: 1000,
    new_len: 1212,
    rev_id: 2,
    old_rev_id: 1,
    server_url: 'https://en.wikipedia.org',
    namespace: 0,
    change_type: 'edit',
    ...overrides,
  }
}

export function makeAlert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: 'a1',
    rule_id: '00000000-0000-0000-0000-000000000001',
    kind: 'revert_war',
    severity: 'high',
    wiki: 'enwiki',
    title: 'Kubernetes',
    server_url: 'https://en.wikipedia.org',
    evidence: { reverts: 4, users: ['Editor_B', 'Editor_C'] },
    status: 'open',
    acknowledged_by: null,
    created_at: '2026-11-25T21:03:58+00:00',
    page_url: 'https://en.wikipedia.org/wiki/Kubernetes',
    ...overrides,
  }
}

export function makeRule(overrides: Partial<Rule> = {}): Rule {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    name: 'Guerra de edición',
    kind: 'revert_war',
    window_seconds: 3600,
    threshold: 3,
    min_users: 2,
    enabled: true,
    ...overrides,
  }
}

export function makeStats(overrides: Partial<Stats> = {}): Stats {
  return {
    edits_per_second: 41.7,
    total_edits: 12345,
    total_reverts: 67,
    open_alerts: 12,
    top_disputed: [
      { wiki: 'enwiki', title: 'Kubernetes', reverts: 14, page_url: 'https://en.wikipedia.org/wiki/Kubernetes' },
      { wiki: 'eswiki', title: 'Contenedor', reverts: 7, page_url: 'https://es.wikipedia.org/wiki/Contenedor' },
    ],
    started_at: '2026-11-25T20:00:00+00:00',
    ...overrides,
  }
}

export function makeGeo(overrides: Partial<GeoEvent> = {}): GeoEvent {
  return {
    kind: 'revert',
    wiki: 'enwiki',
    title: 'Guadalajara',
    lat: 20.67,
    lon: -103.35,
    page_url: 'https://en.wikipedia.org/wiki/Guadalajara',
    timestamp: '2026-11-25T21:04:12+00:00',
    severity: null,
    alert_kind: null,
    ...overrides,
  }
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export function emptyResponse(status = 204): Response {
  return new Response(null, { status })
}

// Replaces global fetch. The handler receives the method and the URL and returns a Response.
export function mockFetch(handler: (method: string, url: string, body: unknown) => Response) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
    return handler(method, String(input), body)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

// Returns [method, url, body] for every fetch call, for easy assertions.
export function fetchCalls(fetchMock: ReturnType<typeof mockFetch>): [string, string, unknown][] {
  return fetchMock.mock.calls.map(([input, init]) => [
    init?.method ?? 'GET',
    String(input),
    typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
  ])
}
