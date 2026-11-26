import type { ReactNode } from 'react'
import { useNow } from '../hooks/useNow'
import { formatPercent, revertRate, uptimeSince } from '../lib/derive'
import { formatNumber } from '../lib/format'
import type { Stats } from '../types'
import { Sparkline } from './Sparkline'

interface KpiStripProps {
  stats: Stats | null
  // Edits per second of the last stats messages.
  throughput: number[]
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

// Time since the api started. It has its own clock, so only this tile re-renders each second.
function Uptime({ startedAt }: { startedAt: string }) {
  const now = useNow()
  return <>{uptimeSince(startedAt, now)}</>
}

export function KpiStrip({ stats, throughput }: KpiStripProps) {
  const openAlerts = stats?.open_alerts ?? 0
  return (
    <dl className="kpis" aria-label="Indicadores">
      <Kpi
        label="Ediciones/s"
        value={stats ? stats.edits_per_second.toFixed(1) : '–'}
        detail={<Sparkline values={throughput} height={18} showValue={false} />}
        tone="accent"
      />
      <Kpi label="Ediciones" value={stats ? formatNumber(stats.total_edits) : '–'} detail="total acumulado" />
      <Kpi label="Reversiones" value={stats ? formatNumber(stats.total_reverts) : '–'} detail="detectadas" />
      <Kpi
        label="Tasa de reversión"
        value={stats ? formatPercent(revertRate(stats)) : '–'}
        detail="reversiones / ediciones"
      />
      <Kpi
        label="Alertas abiertas"
        value={stats ? formatNumber(stats.open_alerts) : '–'}
        detail={openAlerts > 0 ? 'requieren revisión' : 'sin pendientes'}
        tone={openAlerts > 0 ? 'alert' : undefined}
      />
      <Kpi
        label="Tiempo activo"
        value={stats ? <Uptime startedAt={stats.started_at} /> : '–'}
        detail="desde el arranque"
      />
    </dl>
  )
}
