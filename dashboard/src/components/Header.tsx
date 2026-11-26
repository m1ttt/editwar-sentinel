import type { ConnectionStatus } from '../hooks/useLiveFeed'
import { formatNumber } from '../lib/format'
import type { Stats, VersionInfo } from '../types'

interface HeaderProps {
  version: VersionInfo | null
  status: ConnectionStatus
  stats: Stats | null
}

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connecting: 'Conectando…',
  open: 'Conectado · stream en vivo',
  closed: 'Desconectado · reintentando',
}

const KNOWN_ENVIRONMENTS = ['local', 'dev', 'prod']

// The badge color tells at a glance which environment serves the page.
export function environmentClass(environment: string): string {
  const name = environment.toLowerCase()
  return KNOWN_ENVIRONMENTS.includes(name) ? `env-${name}` : 'env-other'
}

export function Header({ version, status, stats }: HeaderProps) {
  const kpis = [
    { label: 'Ediciones/s', value: stats ? stats.edits_per_second.toFixed(1) : '–' },
    { label: 'Ediciones', value: stats ? formatNumber(stats.total_edits) : '–' },
    { label: 'Reversiones', value: stats ? formatNumber(stats.total_reverts) : '–' },
    { label: 'Alertas abiertas', value: stats ? formatNumber(stats.open_alerts) : '–' },
  ]

  return (
    <header className="top">
      <div className="brand">
        <span className="logo">
          EditWar <span>Sentinel</span>
        </span>
        {version ? (
          <span className="version">
            <span className="mono" data-testid="version">
              v{version.version}
            </span>
            <span className={`env ${environmentClass(version.environment)}`} data-testid="environment">
              {version.environment}
            </span>
          </span>
        ) : (
          <span className="version muted">versión no disponible</span>
        )}
      </div>
      <div className="live" role="status">
        <span className={`dot dot-${status}`} aria-hidden="true" />
        {STATUS_LABELS[status]}
      </div>
      <dl className="kpis">
        {kpis.map((kpi) => (
          <div key={kpi.label}>
            <dt>{kpi.label}</dt>
            <dd>{kpi.value}</dd>
          </div>
        ))}
      </dl>
    </header>
  )
}
