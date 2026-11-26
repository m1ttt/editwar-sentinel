import { useEffect, useState } from 'react'
import { ApiError, errorMessage, fetchDiff } from '../api/client'
import type { DiffResult } from '../types'

interface DiffViewProps {
  serverUrl: string
  revId: number
  oldRevId: number
  // Link to the same diff on Wikipedia, shown when the api cannot load it.
  diffUrl?: string
}

// Diffs never change, so one fetch per revision pair is enough for the whole session.
const cache = new Map<string, DiffResult>()

export function diffKey(serverUrl: string, revId: number, oldRevId: number): string {
  return `${serverUrl}|${revId}|${oldRevId}`
}

// For tests.
export function clearDiffCache(): void {
  cache.clear()
}

const NEW_PAGE_MESSAGE = 'Página nueva: esta edición creó el artículo, no hay una versión anterior para comparar.'

// Text for a failed request. A 422 means the edit created the page.
export function diffErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) return NEW_PAGE_MESSAGE
    if (error.status === 404) return 'Wikipedia ya no tiene esta revisión (pudo ser borrada u ocultada).'
    if (error.status === 502) return 'Wikipedia no respondió. Intenta de nuevo en unos segundos.'
  }
  return `No se pudo cargar el cambio: ${errorMessage(error)}`
}

// Theme colors of the console. The iframe has no access to the page CSS, so the
// current values of the CSS variables are copied into it. This keeps the diff
// readable if the console theme changes (dark today, light later).
const THEME_FALLBACK = {
  '--panel': '#0a0e13',
  '--panel-head': '#0d1219',
  '--line': '#1b2430',
  '--text': '#dbe3ec',
  '--text-faint': '#8593a4',
  '--high-text': '#ff8591',
  '--ok': '#3ddc84',
  '--font-mono': "ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
}

type ThemeVar = keyof typeof THEME_FALLBACK

function themeValues(): Record<ThemeVar, string> {
  const values = { ...THEME_FALLBACK }
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return values
  }
  const style = window.getComputedStyle(document.documentElement)
  for (const name of Object.keys(values) as ThemeVar[]) {
    const value = style.getPropertyValue(name).trim()
    // Only plain values: no "<" or ";" can break out of the style element.
    if (value && !/[<>;{}]/.test(value)) {
      values[name] = value
    }
  }
  return values
}

// A complete HTML page for the iframe: a CSP that blocks every network request
// and script, the theme, styles for the MediaWiki diff classes and the table.
export function diffDocument(html: string, theme: Record<ThemeVar, string> = THEME_FALLBACK): string {
  const vars = (Object.keys(theme) as ThemeVar[]).map((name) => `${name}:${theme[name]};`).join('')
  return `<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<style>
:root{${vars}color-scheme:light dark}
html,body{margin:0;background:var(--panel);color:var(--text);font:12px/1.45 var(--font-mono)}
table.diff{width:100%;border-collapse:separate;border-spacing:2px 1px;table-layout:fixed}
col.diff-marker{width:1.6em}
col.diff-content{width:50%}
td{padding:1px 4px;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}
td div{min-height:1.45em}
td.diff-lineno{padding-top:6px;font-weight:700;color:var(--text-faint);background:var(--panel-head);border-bottom:1px solid var(--line)}
td.diff-marker{text-align:right;font-weight:700;user-select:none}
td.diff-marker[data-marker]::before{content:attr(data-marker)}
td.diff-addedline{border-left:3px solid var(--ok);background:color-mix(in srgb,var(--ok) 12%,transparent)}
td.diff-deletedline{border-left:3px solid var(--high-text);background:color-mix(in srgb,var(--high-text) 12%,transparent)}
td.diff-context{border-left:3px solid var(--line);color:var(--text-faint)}
td.diff-empty{background:transparent}
ins.diffchange,ins.diffchange-inline,.diff-addedline .diffchange-inline{text-decoration:none;font-weight:700;border-radius:2px;padding:0 1px;background:color-mix(in srgb,var(--ok) 38%,transparent)}
del.diffchange,del.diffchange-inline,.diff-deletedline .diffchange-inline{text-decoration:none;font-weight:700;border-radius:2px;padding:0 1px;background:color-mix(in srgb,var(--high-text) 38%,transparent)}
a{color:inherit}
</style></head>
<body><table class="diff"><colgroup><col class="diff-marker"><col class="diff-content"><col class="diff-marker"><col class="diff-content"></colgroup><tbody>${html}</tbody></table></body></html>`
}

// The iframe cannot be measured (no same-origin), so the height is estimated
// from the number of rows and the length of the text. Longer diffs scroll.
export function diffHeight(html: string): number {
  const rows = (html.match(/<tr[\s>]/gi) ?? []).length
  const text = html.replace(/<[^>]*>/g, '').length
  const estimate = 16 + rows * 22 + Math.floor(text / 90) * 9
  return Math.max(80, Math.min(420, estimate))
}

type DiffState =
  { status: 'loading' } | { status: 'ready'; diff: DiffResult } | { status: 'error'; message: string; retry: boolean }

function initialState(key: string, oldRevId: number): DiffState {
  if (oldRevId <= 0) {
    return { status: 'error', message: NEW_PAGE_MESSAGE, retry: false }
  }
  const cached = cache.get(key)
  return cached ? { status: 'ready', diff: cached } : { status: 'loading' }
}

// The text change of one edit, loaded from GET /api/diff. The html comes from
// Wikipedia, so it is shown inside a sandboxed iframe (no scripts, no same-origin).
// The parent gives each revision pair its own React key, so the props of one
// DiffView never change.
export function DiffView({ serverUrl, revId, oldRevId, diffUrl }: DiffViewProps) {
  const key = diffKey(serverUrl, revId, oldRevId)
  const [state, setState] = useState<DiffState>(() => initialState(key, oldRevId))
  // Incremented by "Reintentar" to run the request again.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (oldRevId <= 0 || cache.has(key)) {
      return
    }
    let ignore = false
    fetchDiff(serverUrl, revId, oldRevId)
      .then((diff) => {
        cache.set(key, diff)
        if (!ignore) setState({ status: 'ready', diff })
      })
      .catch((err: unknown) => {
        if (!ignore) {
          const final = err instanceof ApiError && (err.status === 422 || err.status === 404 || err.status === 400)
          setState({ status: 'error', message: diffErrorMessage(err), retry: !final })
        }
      })
    return () => {
      ignore = true
    }
  }, [key, serverUrl, revId, oldRevId, attempt])

  if (state.status === 'loading') {
    return (
      <div className="diff-view" aria-busy="true">
        <p className="diff-status mono" role="status">
          Cargando cambio…
        </p>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div className="diff-view">
        <p className={state.retry ? 'error diff-error' : 'diff-status diff-note mono'} role="alert">
          {state.message}
        </p>
        <div className="diff-actions">
          {state.retry && (
            <button
              type="button"
              className="btn"
              onClick={() => {
                setState({ status: 'loading' })
                setAttempt((value) => value + 1)
              }}
            >
              Reintentar
            </button>
          )}
          {diffUrl && oldRevId > 0 && (
            <a className="ext-link" href={diffUrl} target="_blank" rel="noreferrer">
              ver en Wikipedia ↗
            </a>
          )}
        </div>
      </div>
    )
  }

  const { diff } = state
  const empty = diff.html.trim() === ''
  return (
    <div className="diff-view">
      <p className="diff-head mono">
        <span>
          r{diff.old_rev_id} → r{diff.rev_id}
        </span>
        {diff.from_user && diff.to_user && (
          <span>
            {diff.from_user} → {diff.to_user}
          </span>
        )}
        {diff.diff_url && (
          <a className="ext-link" href={diff.diff_url} target="_blank" rel="noreferrer">
            abrir en Wikipedia ↗
          </a>
        )}
      </p>
      {empty ? (
        <p className="diff-status diff-note mono">Sin cambios de texto visibles (solo metadatos o formato).</p>
      ) : (
        <iframe
          className="diff-frame"
          title={`Cambio entre r${diff.old_rev_id} y r${diff.rev_id}`}
          sandbox=""
          referrerPolicy="no-referrer"
          srcDoc={diffDocument(diff.html, themeValues())}
          style={{ height: `${diffHeight(diff.html)}px` }}
        />
      )}
    </div>
  )
}
