import {
  formatPercent,
  MAX_ALERT_POINTS,
  MAX_RATE_POINTS,
  revertRate,
  threatLevel,
  type ThreatBand,
} from '../lib/derive'
import { formatNumber } from '../lib/format'
import type { Stats } from '../types'
import { Panel } from './Panel'

interface ThreatPanelProps {
  stats: Stats | null
}

const CENTER_X = 100
const CENTER_Y = 96
const RADIUS = 80

// Bands of the gauge, as fractions of the 0-100 score.
const BANDS: { band: ThreatBand; from: number; to: number }[] = [
  { band: 'low', from: 0, to: 0.25 },
  { band: 'guarded', from: 0.25, to: 0.5 },
  { band: 'high', from: 0.5, to: 0.75 },
  { band: 'critical', from: 0.75, to: 1 },
]

function polar(fraction: number, radius: number): { x: number; y: number } {
  const angle = Math.PI * (1 - fraction)
  return { x: CENTER_X + radius * Math.cos(angle), y: CENTER_Y - radius * Math.sin(angle) }
}

function pointAt(fraction: number, radius: number): string {
  const { x, y } = polar(fraction, radius)
  return `${x.toFixed(1)} ${y.toFixed(1)}`
}

// SVG path of the upper half circle between two fractions (0 = left, 1 = right).
export function gaugeArc(from: number, to: number, radius = RADIUS): string {
  const start = Math.min(Math.max(from, 0), 1)
  const end = Math.min(Math.max(to, start), 1)
  return `M${pointAt(start, radius)} A${radius} ${radius} 0 0 1 ${pointAt(end, radius)}`
}

interface FactorProps {
  label: string
  value: string
  points: number
  max: number
}

function Factor({ label, value, points, max }: FactorProps) {
  return (
    <li className="factor">
      <span className="factor-label">{label}</span>
      <span className="factor-value mono">{value}</span>
      <span className="meter" aria-hidden="true">
        <i style={{ width: `${(points / max) * 100}%` }} />
      </span>
      <span className="factor-points mono">{`${Math.round(points)}/${max} pts`}</span>
    </li>
  )
}

export function ThreatPanel({ stats }: ThreatPanelProps) {
  const level = stats ? threatLevel(stats) : null
  const fraction = level ? level.score / 100 : 0
  const band = level?.band ?? 'none'
  const needle = polar(fraction, RADIUS - 20)

  return (
    <Panel title="Nivel de amenaza" aside="derivado" className="area-threat">
      <div className={`threat threat-${band}`}>
        <svg className="gauge" viewBox="0 0 200 104" role="img" aria-label={level ? `Nivel ${level.label}, ${level.score} de 100` : 'Sin datos'}>
          {BANDS.map((item) => (
            <path key={item.band} className={`gauge-band band-${item.band}`} d={gaugeArc(item.from + 0.006, item.to - 0.006)} />
          ))}
          {level && level.score > 0 && <path className="gauge-value" d={gaugeArc(0, fraction, RADIUS - 12)} />}
          <line
            className="gauge-needle"
            x1={CENTER_X}
            y1={CENTER_Y}
            x2={needle.x.toFixed(1)}
            y2={needle.y.toFixed(1)}
          />
          <circle className="gauge-hub" cx={CENTER_X} cy={CENTER_Y} r="4" />
        </svg>
        <div className="threat-readout">
          <span className="threat-score mono">{level ? level.score : '–'}</span>
          <span className="threat-label">{level ? level.label : 'Sin datos'}</span>
        </div>
      </div>
      {stats && level && (
        <ul className="factors">
          <Factor
            label="Alertas abiertas"
            value={formatNumber(stats.open_alerts)}
            points={level.alertPoints}
            max={MAX_ALERT_POINTS}
          />
          <Factor
            label="Tasa de reversión"
            value={formatPercent(revertRate(stats))}
            points={level.ratePoints}
            max={MAX_RATE_POINTS}
          />
        </ul>
      )}
    </Panel>
  )
}
