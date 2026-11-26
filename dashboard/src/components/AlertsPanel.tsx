import { useEffect, useState } from 'react'
import { acknowledgeAlert, deleteAlert, dismissAlert, errorMessage, listAlerts } from '../api/client'
import { alertTitle, formatTime, SEVERITY_LABELS, summarizeEvidence } from '../lib/format'
import type { Alert, AlertStatus } from '../types'
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
    <Panel title="Alertas" aside={openCount === undefined ? undefined : `${openCount} abiertas`}>
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
          Operador <input value={operator} onChange={(event) => setOperator(event.target.value)} size={12} />
        </label>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Hora</th>
              <th>Tipo</th>
              <th>Severidad</th>
              <th>Artículo</th>
              <th>Evidencia</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {alerts.length === 0 && (
              <tr>
                <td colSpan={7} className="empty">
                  No hay alertas.
                </td>
              </tr>
            )}
            {alerts.map((alert) => (
              <tr key={alert.id}>
                <td className="mono">{formatTime(alert.created_at)}</td>
                <td className="mono">{alert.kind}</td>
                <td>
                  <span className={`pill ${SEVERITY_CLASSES[alert.severity] ?? 'lo'}`}>
                    {SEVERITY_LABELS[alert.severity] ?? alert.severity}
                  </span>
                </td>
                <td>
                  <a href={alert.page_url} target="_blank" rel="noreferrer">
                    {alertTitle(alert.title, alert.wiki)}
                  </a>{' '}
                  <span className="mono">{alert.wiki}</span>
                </td>
                <td className="evidence" title={JSON.stringify(alert.evidence)}>
                  {summarizeEvidence(alert.evidence)}
                </td>
                <td>
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
