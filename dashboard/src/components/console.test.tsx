// Tests for the console panels that only show values derived from stats and the live feed.
import { act, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeEdit, makeStats } from '../test/fixtures'
import { KpiStrip } from './KpiStrip'
import { TelemetryPanel } from './TelemetryPanel'
import { gaugeArc, ThreatPanel } from './ThreatPanel'
import { WikiActivityPanel } from './WikiActivityPanel'

function feedRow(wiki: string, reverted = false, id = `${wiki}-${Math.random()}`) {
  return { ...makeEdit({ event_id: id, wiki }), reverted, delta: 1 }
}

describe('KpiStrip', () => {
  it('shows the KPIs from the stats', () => {
    render(<KpiStrip stats={makeStats()} throughput={[30, 41.7]} />)
    expect(screen.getByText('41.7')).toBeInTheDocument()
    expect(screen.getByText('12,345')).toBeInTheDocument()
    expect(screen.getByText('67')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    // 67 reverts / 12,345 edits.
    expect(screen.getByText('0.54 %')).toBeInTheDocument()
    expect(screen.getByText('requieren revisión')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Ediciones por segundo' })).toBeInTheDocument()
  })

  it('marks the open alerts tile only when there are open alerts', () => {
    const { rerender } = render(<KpiStrip stats={makeStats()} throughput={[]} />)
    expect(screen.getByText('Alertas abiertas').closest('.kpi')).toHaveClass('kpi-alert')
    rerender(<KpiStrip stats={makeStats({ open_alerts: 0 })} throughput={[]} />)
    expect(screen.getByText('Alertas abiertas').closest('.kpi')).not.toHaveClass('kpi-alert')
    expect(screen.getByText('sin pendientes')).toBeInTheDocument()
  })

  it('shows dashes before the first stats', () => {
    render(<KpiStrip stats={null} throughput={[]} />)
    expect(screen.getAllByText('–')).toHaveLength(6)
  })

  it('counts the uptime from started_at every second', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-25T21:30:05Z'))
    render(<KpiStrip stats={makeStats()} throughput={[]} />)
    expect(screen.getByText('01:30:05')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getByText('01:30:06')).toBeInTheDocument()
  })
})

describe('ThreatPanel', () => {
  it('shows the score, the band and the two factors', () => {
    // 12 open alerts give 60 points. 67 / 12,345 = 0.54 % gives 11 points.
    const { container } = render(<ThreatPanel stats={makeStats()} />)
    expect(screen.getByRole('img', { name: 'Nivel Alto, 71 de 100' })).toBeInTheDocument()
    expect(screen.getByText('71')).toBeInTheDocument()
    expect(screen.getByText('Alto')).toBeInTheDocument()
    expect(screen.getByText('60/60 pts')).toBeInTheDocument()
    expect(screen.getByText('11/40 pts')).toBeInTheDocument()
    expect(container.querySelector('.threat')).toHaveClass('threat-high')
    expect(container.querySelector('.gauge-value')).not.toBeNull()
  })

  it('has no value arc at zero', () => {
    const { container } = render(<ThreatPanel stats={makeStats({ open_alerts: 0, total_reverts: 0 })} />)
    expect(screen.getByText('Bajo')).toBeInTheDocument()
    expect(container.querySelector('.gauge-value')).toBeNull()
  })

  it('says when there is no data', () => {
    const { container } = render(<ThreatPanel stats={null} />)
    expect(screen.getByText('Sin datos')).toBeInTheDocument()
    expect(container.querySelector('.threat')).toHaveClass('threat-none')
    expect(container.querySelector('.factors')).toBeNull()
  })

  it('draws the arc from left to right and clamps the fractions', () => {
    expect(gaugeArc(0, 1, 80)).toBe('M20.0 96.0 A80 80 0 0 1 180.0 96.0')
    expect(gaugeArc(-1, 0.5, 80)).toBe('M20.0 96.0 A80 80 0 0 1 100.0 16.0')
    expect(gaugeArc(0.5, 0.2, 80)).toBe('M100.0 16.0 A80 80 0 0 1 100.0 16.0')
  })
})

describe('TelemetryPanel', () => {
  it('draws the chart and the readouts', () => {
    const { container } = render(<TelemetryPanel throughput={[8, 12, 11]} />)
    expect(screen.getByRole('img', { name: 'Ediciones por segundo, 3 muestras' })).toBeInTheDocument()
    const readouts = within(container.querySelector('.readouts') as HTMLElement)
    expect(readouts.getByText('11.0 ed/s')).toBeInTheDocument()
    expect(readouts.getByText('12.0 ed/s')).toBeInTheDocument()
    expect(readouts.getByText('10.3 ed/s')).toBeInTheDocument()
    expect(container.querySelector('.chart-line')).not.toBeNull()
    expect(container.querySelector('.chart-marker')).toHaveStyle({ left: '100%' })
    // The y axis goes up to a round number above the peak.
    expect(container.querySelector('.chart-axis')).toHaveTextContent('20100')
  })

  it('waits for samples', () => {
    const { container } = render(<TelemetryPanel throughput={[]} />)
    expect(screen.getByText('Esperando muestras de /api/stats…')).toBeInTheDocument()
    expect(container.querySelector('.readouts')).toBeNull()
    expect(container.querySelector('.chart-line')).toBeNull()
  })
})

describe('WikiActivityPanel', () => {
  it('ranks the wikis of the feed with relative bars and revert counts', () => {
    const edits = [feedRow('enwiki', true), feedRow('enwiki'), feedRow('eswiki')]
    const { container } = render(<WikiActivityPanel edits={edits} />)
    expect(screen.getByText('últimos 3')).toBeInTheDocument()
    const items = container.querySelectorAll('.barlist li')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('enwiki')
    expect(within(items[0] as HTMLElement).getByText('· 1 rev.')).toBeInTheDocument()
    const bars = container.querySelectorAll<HTMLElement>('.bar i')
    expect(bars[0].style.width).toBe('100%')
    expect(bars[1].style.width).toBe('50%')
    expect(container.querySelectorAll('.bar b')).toHaveLength(1)
  })

  it('shows an empty state', () => {
    render(<WikiActivityPanel edits={[]} />)
    expect(screen.getByText('Sin eventos todavía.')).toBeInTheDocument()
  })
})
