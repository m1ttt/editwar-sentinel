import { useEffect, useState } from 'react'
import { acknowledgeAlert, deleteAlert, dismissAlert, errorMessage, listAlerts } from '../api/client'
import { severityCounts } from '../lib/derive'
import { alertTitle, formatTime, SEVERITY_LABELS, summarizeEvidence } from '../lib/format'
import type { Alert, AlertStatus, Severity } from '../types'
import { Panel } from './Panel'

interface AlertsPanelProps {
  // The last alert from the WebSocket. A new one makes the panel reload.
  lastAlert: Alert | null
  openCount?: number
  // A new value makes the panel reload (App passes the WebSocket connection count).
  refreshKey?: number
}

const STATUS_FILTERS: { value: AlertStatus | ''; label: string }[] = [
  { value: '', label: 'Todas' },
  { value: 'open', label: 'Abiertas' },
  { value: 'acknowledged', label: 'Reconocidas' },
  { value: 'dismissed', label: 'Descartadas' },
]

const STATUS_LABELS: Record<AlertStatus, string> = {
  open: 'abierta',
  acknowledged: 'reconocida',
  dismissed: 'descartada',
}

const SEVERITY_CLASSES = { high: 'hi', medium: 'me', low: 'lo' } as const

const SEVERITY_ORDER: Severity[] = ['high', 'medium', 'low']

// Stacked bar with the severity of the alerts in the table (the loaded set, not every alert).
function SeverityBreakdown({ alerts }: { alerts: Alert[] }) {
  const counts = severityCounts(alerts)
  const total = Math.max(1, alerts.length)
  return (
    <div className="severity">
      <span className="severity-bar" aria-hidden="true">
        {SEVERITY_ORDER.map((severity) => (
          <i key={severity} className={SEVERITY_CLASSES[severity]} style={{ width: `${(counts[severity] / total) * 100}%` }} />
        ))}
      </span>
      <ul className="severity-legend" aria-label={`Severidad de las ${alerts.length} alertas cargadas`}>
        {SEVERITY_ORDER.map((severity) => (
          <li key={severity} className={`sev-${SEVERITY_CLASSES[severity]}`}>
            {`${SEVERITY_LABELS[severity]} ${counts[severity]}`}
          </li>
        ))}
      </ul>
    </div>
  )
}

export const ALERTS_LIMIT = 50

export function AlertsPanel({ lastAlert, openCount, refreshKey = 0 }: AlertsPanelProps) {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [statusFilter, setStatusFilter] = useState<AlertStatus | ''>('')
  const [operator, setOperator] = useState('operador')
  const [error, setError] = useState<string | null>(null)
  // Incremented after each action to load the list again.
  const [reloadKey, setReloadKey] = useState(0)

  const lastAlertId = lastAlert?.id
  useEffect(() => {
    // "ignore" drops the answer of an old request when a newer one has started.
    let ignore = false
    listAlerts({ status: statusFilter || undefined, limit: ALERTS_LIMIT })
      .then((data) => {
        if (!ignore) {
          setAlerts(data)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(errorMessage(err))
        }
      })
    return () => {
      ignore = true
    }
  }, [statusFilter, lastAlertId, reloadKey, refreshKey])

  // Runs one action against the api, then reloads the list.
  const run = async (action: () => Promise<unknown>) => {
    try {
      await action()
      setReloadKey((key) => key + 1)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const remove = (alert: Alert) => {
    if (window.confirm(`¿Eliminar la alerta de "${alertTitle(alert.title, alert.wiki)}"?`)) {
      void run(() => deleteAlert(alert.id))
    }
  }

  const operatorName = operator.trim()

  return (
    <Panel
      title="Incidentes"
      aside={openCount === undefined ? undefined : `${openCount} abiertas`}
      className="area-alerts"
    >
      <div className="toolbar">
        <label>
          Estado{' '}
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as AlertStatus | '')}>
            {STATUS_FILTERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Operador <input value={operator} onChange={(event) => setOperator(event.target.value)} size={10} />
        </label>
        <SeverityBreakdown alerts={alerts} />
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="table-wrap">
        <table className="incidents">
          <thead>
            <tr>
              <th>Hora</th>
              <th>Sev.</th>
              <th>Incidente · evidencia</th>
              <th>Estado</th>
              <th>
                <span className="sr-only">Acciones</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {alerts.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  No hay alertas.
                </td>
              </tr>
            )}
            {alerts.map((alert) => (
              <tr
                key={alert.id}
                className={[
                  `sev-row-${SEVERITY_CLASSES[alert.severity] ?? 'lo'}`,
                  `status-${alert.status}`,
                  alert.id === lastAlertId ? 'row-new' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                <td className="mono">{formatTime(alert.created_at)}</td>
                <td>
                  <span className={`pill ${SEVERITY_CLASSES[alert.severity] ?? 'lo'}`}>
                    {SEVERITY_LABELS[alert.severity] ?? alert.severity}
                  </span>
                </td>
                <td className="incident">
                  <a href={alert.page_url} target="_blank" rel="noreferrer">
                    {alertTitle(alert.title, alert.wiki)}
                  </a>
                  <span className="incident-line">
                    <span className="mono incident-meta">
                      {alert.kind} · {alert.wiki}
                    </span>
                    <span className="evidence" title={JSON.stringify(alert.evidence)}>
                      {summarizeEvidence(alert.evidence)}
                    </span>
                  </span>
                </td>
                <td className="status">
                  <span className={`status-dot status-dot-${alert.status}`} aria-hidden="true" />
                  {STATUS_LABELS[alert.status] ?? alert.status}
                  {alert.acknowledged_by && <span className="muted"> ({alert.acknowledged_by})</span>}
                </td>
                <td className="actions">
                  {alert.status === 'open' && (
                    <button
                      className="btn primary"
                      disabled={operatorName === ''}
                      onClick={() => void run(() => acknowledgeAlert(alert.id, operatorName))}
                    >
                      Reconocer
                    </button>
                  )}
                  {alert.status !== 'dismissed' && (
                    <button className="btn" onClick={() => void run(() => dismissAlert(alert.id))}>
                      Descartar
                    </button>
                  )}
                  <button className="btn danger" onClick={() => remove(alert)}>
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
