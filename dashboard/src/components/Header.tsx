import type { ConnectionStatus } from '../hooks/useLiveFeed'
import { useNow } from '../hooks/useNow'
import type { VersionInfo } from '../types'

export type View = 'monitor' | 'rules'

export const VIEWS: { id: View; label: string }[] = [
  { id: 'monitor', label: 'Monitor' },
  { id: 'rules', label: 'Reglas' },
]

// id of the element that shows a view, for aria-controls.
export function viewPanelId(view: View): string {
  return `view-${view}`
}

interface HeaderProps {
  version: VersionInfo | null
  status: ConnectionStatus
  view?: View
  onViewChange?: (view: View) => void
}

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connecting: 'Conectando…',
  open: 'Conectado · stream en vivo',
  closed: 'Desconectado · reintentando',
}

const KNOWN_ENVIRONMENTS = ['local', 'dev', 'prod']

// Version of this dashboard build. The api version comes from /api/version.
export const UI_VERSION = import.meta.env.VITE_APP_VERSION || 'dev'

// The badge color tells at a glance which environment serves the page.
export function environmentClass(environment: string): string {
  const name = environment.toLowerCase()
  return KNOWN_ENVIRONMENTS.includes(name) ? `env-${name}` : 'env-other'
}

// Local time of the browser, "21:04:12".
function Clock() {
  const now = useNow()
  return (
    <time className="clock mono" dateTime={new Date(now).toISOString()}>
      {new Date(now).toLocaleTimeString('es-MX', { hour12: false })}
    </time>
  )
}

function Logo() {
  return (
    <svg className="logo-mark" viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
      <path d="M16 2 28 9v14l-12 7-12-7V9z" fill="none" stroke="currentColor" strokeWidth="2" />
      <polyline
        points="8,19 12,14 15,17 19,10 24,15"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function Header({ version, status, view = 'monitor', onViewChange }: HeaderProps) {
  return (
    <header className="top">
      <div className="brand">
        <Logo />
        <div className="brand-text">
          <span className="logo">
            EditWar <span>Sentinel</span>
          </span>
          <span className="tagline">Consola de amenazas · Wikipedia</span>
        </div>
      </div>
      <div className="tabs" role="tablist" aria-label="Vistas">
        {VIEWS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`tab-${item.id}`}
            aria-selected={view === item.id}
            aria-controls={viewPanelId(item.id)}
            className={view === item.id ? 'tab tab-active' : 'tab'}
            onClick={() => onViewChange?.(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className={`live live-${status}`} role="status">
        <span className={`dot dot-${status}`} aria-hidden="true" />
        {STATUS_LABELS[status]}
      </div>
      <div className="top-meta">
        <Clock />
        {version ? (
          <span className="version">
            <span className="mono" data-testid="version">
              api {version.version}
            </span>
            <span className="mono" data-testid="ui-version">
              ui {UI_VERSION}
            </span>
            <span className={`env ${environmentClass(version.environment)}`} data-testid="environment">
              {version.environment}
            </span>
          </span>
        ) : (
          <span className="version muted">versión no disponible</span>
        )}
      </div>
    </header>
  )
}
