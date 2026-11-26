import { dotsPath, landDots, MAP_HEIGHT, MAP_WIDTH, project } from '../lib/geo'
import { alertTitle, formatTime, SEVERITY_LABELS } from '../lib/format'
import type { GeoEvent } from '../types'
import { Panel } from './Panel'

interface MapPanelProps {
  // Points from the live feed, newest first.
  points: GeoEvent[]
}

// The land never changes, so the path is built once.
const LAND_PATH = dotsPath(landDots(), 0.8)

// The newest points pulse.
export const PULSE_COUNT = 5
// How many points the list next to the map shows.
export const LIST_COUNT = 6

const SEVERITY_CLASSES = { high: 'hi', medium: 'me', low: 'lo' } as const

// Reverts use the accent color. Alerts use the color of their severity.
export function markerClass(point: Pick<GeoEvent, 'kind' | 'severity'>): string {
  if (point.kind === 'revert') {
    return 'geo-revert'
  }
  return `geo-${SEVERITY_CLASSES[point.severity ?? 'low'] ?? 'lo'}`
}

export function markerLabel(point: GeoEvent): string {
  const kind =
    point.kind === 'revert'
      ? 'Reversión'
      : `Alerta ${point.alert_kind ?? ''} ${point.severity ? SEVERITY_LABELS[point.severity] : ''}`.replace(/\s+/g, ' ').trim()
  return `${kind}: ${alertTitle(point.title, point.wiki)} (${point.wiki}) · ${formatTime(point.timestamp)}`
}

export function MapPanel({ points }: MapPanelProps) {
  // Oldest first, so the newest markers are drawn on top.
  const drawOrder = points.map((point, index) => ({ point, index })).reverse()

  return (
    <Panel title="Mapa de incidentes" aside="ubicación del artículo editado" className="area-map">
      <div className="map">
        <div className="map-canvas">
          <svg
            className="map-svg"
            viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label={`Mapa con ${points.length} reversiones y alertas, en la ubicación del artículo`}
          >
            <path className="map-land" d={LAND_PATH} />
            {drawOrder.map(({ point, index }) => {
              const { x, y } = project(point.lat, point.lon)
              return (
                <a
                  key={`${point.kind}|${point.wiki}|${point.title}|${point.timestamp}`}
                  href={point.page_url}
                  target="_blank"
                  rel="noreferrer"
                  // The list next to the map has the same links for the keyboard.
                  tabIndex={-1}
                  className={`geo-marker ${markerClass(point)}`}
                >
                  <title>{markerLabel(point)}</title>
                  {index < PULSE_COUNT && <circle className="geo-pulse" cx={x} cy={y} r="2.2" />}
                  <circle className="geo-dot" cx={x} cy={y} r={index < PULSE_COUNT ? 2.2 : 1.6} />
                </a>
              )
            })}
          </svg>
          {points.length === 0 && <p className="map-empty">Sin incidentes con ubicación todavía</p>}
          <ul className="map-legend" aria-label="Leyenda">
            <li className="geo-revert">reversión</li>
            <li className="geo-hi">alerta alta</li>
            <li className="geo-me">media</li>
            <li className="geo-lo">baja</li>
          </ul>
        </div>
        <ol className="map-list" aria-label="Últimos puntos del mapa">
          {points.slice(0, LIST_COUNT).map((point) => (
            <li key={`${point.kind}|${point.wiki}|${point.title}|${point.timestamp}`} className={markerClass(point)}>
              <span className="map-list-time mono">{formatTime(point.timestamp)}</span>
              <span className="map-list-kind mono">{point.kind === 'revert' ? 'REV' : 'ALERTA'}</span>
              <a href={point.page_url} target="_blank" rel="noreferrer" title={markerLabel(point)}>
                {alertTitle(point.title, point.wiki)}
              </a>
              <span className="map-list-wiki mono">{point.wiki}</span>
            </li>
          ))}
        </ol>
      </div>
    </Panel>
  )
}
