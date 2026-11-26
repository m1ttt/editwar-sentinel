import { useId } from 'react'
import type { RatePoint } from '../hooks/liveFeedReducer'
import { chartGeometry, formatSpan, throughputSummary } from '../lib/derive'
import { Panel } from './Panel'

interface TelemetryPanelProps {
  // Instantaneous edits per second between consecutive stats messages, oldest first.
  rates: RatePoint[]
}

const WIDTH = 600
const HEIGHT = 120
// Horizontal grid lines at these fractions of the y axis.
const GRID_LINES = [0.25, 0.5, 0.75]

function formatRate(value: number): string {
  return `${value.toFixed(1)} ed/s`
}

export function TelemetryPanel({ rates }: TelemetryPanelProps) {
  const throughput = rates.map((point) => point.value)
  const span = rates.length > 1 ? (rates[rates.length - 1].at - rates[0].at) / 1000 : 0
  // React ids contain colons, which do not work in url(#...).
  const fillId = `tele-fill-${useId().replace(/:/g, '')}`
  const geometry = chartGeometry(throughput, WIDTH, HEIGHT)
  const summary = throughputSummary(throughput)

  const readouts = summary && (
    <dl className="readouts">
      <div>
        <dt>actual</dt>
        <dd>{formatRate(summary.current)}</dd>
      </div>
      <div>
        <dt>pico</dt>
        <dd>{formatRate(summary.peak)}</dd>
      </div>
      <div>
        <dt>media</dt>
        <dd>{formatRate(summary.average)}</dd>
      </div>
    </dl>
  )

  return (
    <Panel title="Telemetría en vivo" aside="ediciones/s instantáneas" className="area-telemetry">
      {readouts}
      <div className="chart">
        <div className="chart-axis mono" aria-hidden="true">
          <span>{geometry ? geometry.max : '–'}</span>
          <span>{geometry ? geometry.max / 2 : ''}</span>
          <span>0</span>
        </div>
        <div className="chart-plot">
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`Ediciones por segundo, ${throughput.length} muestras`}
          >
            <defs>
              <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.45" />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
              </linearGradient>
            </defs>
            {GRID_LINES.map((fraction) => (
              <line key={fraction} className="grid-line" x1="0" x2={WIDTH} y1={HEIGHT * fraction} y2={HEIGHT * fraction} />
            ))}
            {geometry && (
              <>
                <path className="chart-area" d={geometry.area} fill={`url(#${fillId})`} />
                <path className="chart-line" d={geometry.line} />
              </>
            )}
          </svg>
          {geometry && (
            <span
              className="chart-marker"
              aria-hidden="true"
              style={{ left: `${(geometry.last.x / WIDTH) * 100}%`, top: `${(geometry.last.y / HEIGHT) * 100}%` }}
            />
          )}
          {!geometry && <p className="chart-empty">Esperando dos lecturas de /api/stats…</p>}
        </div>
      </div>
      <div className="chart-foot mono" aria-hidden="true">
        <span>{`−${formatSpan(span)} · ${throughput.length} muestras`}</span>
        <span>ahora</span>
      </div>
    </Panel>
  )
}
