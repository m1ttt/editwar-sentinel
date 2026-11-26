import type { ReactNode } from 'react'
import type { RatePoint } from '../hooks/liveFeedReducer'
import { formatNumber } from '../lib/format'
import type { Stats } from '../types'
import { Sparkline } from './Sparkline'

interface KpiStripProps {
  stats: Stats | null
  // Instantaneous edits per second, oldest first (see TelemetryPanel).
  rates: RatePoint[]
}

interface KpiProps {
  label: string
  value: ReactNode
  // Small line under the value: a short explanation or a sparkline.
  detail: ReactNode
  tone?: 'accent' | 'alert'
}

function Kpi({ label, value, detail, tone }: KpiProps) {
  return (
    <div className={tone ? `kpi kpi-${tone}` : 'kpi'}>
      <dt>{label}</dt>
      <dd>
        <div className="kpi-value">{value}</div>
        <div className="kpi-sub">{detail}</div>
      </dd>
    </div>
  )
}

export function KpiStrip({ stats, rates }: KpiStripProps) {
  const openAlerts = stats?.open_alerts ?? 0
  return (
    <dl className="kpis" aria-label="Indicadores">
      <Kpi
        label="Ediciones/s · media 60 s"
        value={stats ? stats.edits_per_second.toFixed(1) : '–'}
        detail={<Sparkline values={rates.map((point) => point.value)} height={18} showValue={false} />}
        tone="accent"
      />
      <Kpi label="Ediciones" value={stats ? formatNumber(stats.total_edits) : '–'} detail="total acumulado" />
      <Kpi label="Reversiones" value={stats ? formatNumber(stats.total_reverts) : '–'} detail="detectadas" />
      <Kpi
        label="Alertas abiertas"
        value={stats ? formatNumber(stats.open_alerts) : '–'}
        detail={openAlerts > 0 ? 'requieren revisión' : 'sin pendientes'}
        tone={openAlerts > 0 ? 'alert' : undefined}
      />
    </dl>
  )
}
