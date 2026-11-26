// Sample objects with the same shape as the api JSON.
import { vi } from 'vitest'
import type { Alert, DiffResult, EditEvent, GeoEvent, Rule, Stats, TimelineEntry } from '../types'

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

// One edit of an edit war timeline (alert.evidence.timeline).
export function makeTimelineEntry(overrides: Partial<TimelineEntry> = {}): TimelineEntry {
  return {
    event_id: 't1',
    user: 'Editor_B',
    is_bot: false,
    timestamp: '2026-11-25T21:00:00+00:00',
    comment: 'add section',
    rev_id: 101,
    old_rev_id: 100,
    old_len: 1000,
    new_len: 1300,
    size_delta: 300,
    is_revert: false,
    revert_reason: null,
    reverted_user: null,
    diff_url: 'https://en.wikipedia.org/w/index.php?diff=101&oldid=100',
    ...overrides,
  }
}

// B adds text, C reverts B, B reverts C, a bot tidies up. Oldest first.
export function makeTimeline(): TimelineEntry[] {
  return [
    makeTimelineEntry(),
    makeTimelineEntry({
      event_id: 't2',
      user: 'Editor_C',
      timestamp: '2026-11-25T21:01:00+00:00',
      comment: 'Undid revision 101 by Editor_B',
      rev_id: 102,
      old_rev_id: 101,
      old_len: 1300,
      new_len: 1000,
      size_delta: -300,
      is_revert: true,
      revert_reason: 'comment',
      reverted_user: 'Editor_B',
      diff_url: 'https://en.wikipedia.org/w/index.php?diff=102&oldid=101',
    }),
    makeTimelineEntry({
      event_id: 't3',
      user: 'Editor_B',
      timestamp: '2026-11-25T21:02:00+00:00',
      comment: '',
      rev_id: 103,
      old_rev_id: 102,
      old_len: 1000,
      new_len: 1300,
      size_delta: 300,
      is_revert: true,
      revert_reason: 'size_restore',
      reverted_user: 'Editor_C',
      diff_url: 'https://en.wikipedia.org/w/index.php?diff=103&oldid=102',
    }),
    makeTimelineEntry({
      event_id: 't4',
      user: 'TidyBot',
      is_bot: true,
      timestamp: '2026-11-25T21:03:00+00:00',
      comment: 'Bot: fixing links',
      rev_id: 104,
      old_rev_id: 103,
      old_len: 1300,
      new_len: 1300,
      size_delta: 0,
      diff_url: 'https://en.wikipedia.org/w/index.php?diff=104&oldid=103',
    }),
  ]
}

export function makeDiff(overrides: Partial<DiffResult> = {}): DiffResult {
  return {
    server_url: 'https://en.wikipedia.org',
    rev_id: 102,
    old_rev_id: 101,
    html:
      '<tr><td colspan="2" class="diff-lineno">Line 1:</td><td colspan="2" class="diff-lineno">Line 1:</td></tr>' +
      '<tr><td class="diff-marker" data-marker="−"></td><td class="diff-deletedline"><div>Old <del class="diffchange diffchange-inline">text</del></div></td>' +
      '<td class="diff-marker" data-marker="+"></td><td class="diff-addedline"><div>Old <ins class="diffchange diffchange-inline">words</ins></div></td></tr>',
    from_user: 'Editor_B',
    to_user: 'Editor_C',
    comment: 'Undid revision 101 by Editor_B',
    diff_url: 'https://en.wikipedia.org/w/index.php?diff=102&oldid=101',
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
