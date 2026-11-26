// JSON shapes produced by the api. They mirror the to_dict() methods in
// libs/domain/src/editwar_domain (events.py, alerts.py, rules.py).

export interface VersionInfo {
  service: string
  version: string
  environment: string
}

export interface DisputedArticle {
  wiki: string
  title: string
  reverts: number
  page_url: string
  // Added with the edit war timeline. Older apis do not send it.
  history_url?: string
}

export interface Stats {
  edits_per_second: number
  total_edits: number
  total_reverts: number
  open_alerts: number
  top_disputed: DisputedArticle[]
  started_at: string
}

export interface EditEvent {
  event_id: string
  wiki: string
  title: string
  user: string
  is_bot: boolean
  timestamp: string
  comment: string
  old_len: number
  new_len: number
  rev_id: number
  old_rev_id: number
  server_url: string
  namespace: number
  change_type: string
  // Link to the change on Wikipedia. Optional: older messages do not have them.
  diff_url?: string
  history_url?: string
}

export interface RevertEvent {
  event_id: string
  wiki: string
  title: string
  user: string
  timestamp: string
  reason: string
  server_url: string
  history_url?: string
  // The user whose edit was undone, when the detector knows it.
  reverted_user?: string | null
}

export type RuleKind = 'revert_war' | 'burst' | 'bot_spike'
export type AlertStatus = 'open' | 'acknowledged' | 'dismissed'
export type Severity = 'low' | 'medium' | 'high'

export interface Alert {
  id: string
  rule_id: string
  kind: RuleKind
  severity: Severity
  wiki: string
  title: string
  server_url: string
  evidence: Record<string, unknown>
  status: AlertStatus
  acknowledged_by: string | null
  created_at: string
  page_url: string
  // History page of the article. null for wiki-wide alerts (title "*").
  // Missing in alerts stored before the edit war timeline.
  history_url?: string | null
}

// One edit of an edit war, from alert.evidence.timeline (oldest first, at most 25).
// revert_war and burst alerts have it; evidence.timeline_truncated says whether
// older edits were left out.
export interface TimelineEntry {
  event_id: string
  user: string
  is_bot: boolean
  timestamp: string
  comment: string
  rev_id: number
  old_rev_id: number
  old_len: number
  new_len: number
  size_delta: number
  is_revert: boolean
  revert_reason: 'comment' | 'size_restore' | null
  reverted_user: string | null
  diff_url: string
}

// Answer of GET /api/diff. "html" is the <tr> rows of a MediaWiki diff table.
export interface DiffResult {
  server_url: string
  rev_id: number
  old_rev_id: number
  html: string
  from_user: string
  to_user: string
  comment: string
  diff_url: string
}

export interface Rule {
  id: string
  name: string
  kind: RuleKind
  window_seconds: number
  threshold: number
  min_users: number
  enabled: boolean
}

// Body of POST /api/rules and PUT /api/rules/{id}: a rule without its id.
export type RuleInput = Omit<Rule, 'id'>

// A revert or an alert on an article that has coordinates on Wikipedia.
// lat/lon are the location of the article topic, not of the editor.
// From the "geo" WebSocket message and from GET /api/geo/recent.
export interface GeoEvent {
  kind: 'revert' | 'alert'
  wiki: string
  title: string
  lat: number
  lon: number
  page_url: string
  timestamp: string
  severity: Severity | null
  alert_kind: RuleKind | null
}

// One message from the WebSocket at /ws/live.
export type LiveMessage =
  | { type: 'edit'; data: EditEvent }
  | { type: 'revert'; data: RevertEvent }
  | { type: 'alert'; data: Alert }
  | { type: 'stats'; data: Stats }
  | { type: 'geo'; data: GeoEvent }
