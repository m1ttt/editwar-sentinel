// Tests for the console panels that show values derived from stats and the live feed.
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeEdit, makeStats } from '../test/fixtures'
import { KpiStrip } from './KpiStrip'
import { TelemetryPanel } from './TelemetryPanel'
import { WikiActivityPanel } from './WikiActivityPanel'

function feedRow(wiki: string, reverted = false, id = `${wiki}-${Math.random()}`) {
  return { ...makeEdit({ event_id: id, wiki }), reverted, delta: 1 }
}

describe('KpiStrip', () => {
  it('shows the four live KPIs from the stats', () => {
    render(
      <KpiStrip
        stats={makeStats()}
        rates={[
          { at: 0, value: 30 },
          { at: 2000, value: 41.7 },
        ]}
      />,
    )
    expect(screen.getByText('41.7')).toBeInTheDocument()
    expect(screen.getByText('12,345')).toBeInTheDocument()
    expect(screen.getByText('67')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('requieren revisión')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Ediciones por segundo' })).toBeInTheDocument()
    expect(screen.getAllByRole('term').map((term) => term.textContent)).toEqual([
      'Ediciones/s · media 60 s',
      'Ediciones',
      'Reversiones',
      'Alertas abiertas',
    ])
  })

  it('marks the open alerts tile only when there are open alerts', () => {
    const { rerender } = render(<KpiStrip stats={makeStats()} rates={[]} />)
    expect(screen.getByText('Alertas abiertas').closest('.kpi')).toHaveClass('kpi-alert')
    rerender(<KpiStrip stats={makeStats({ open_alerts: 0 })} rates={[]} />)
    expect(screen.getByText('Alertas abiertas').closest('.kpi')).not.toHaveClass('kpi-alert')
    expect(screen.getByText('sin pendientes')).toBeInTheDocument()
  })

  it('shows dashes before the first stats', () => {
    render(<KpiStrip stats={null} rates={[]} />)
    expect(screen.getAllByText('–')).toHaveLength(4)
  })
})

describe('TelemetryPanel', () => {
  const at = (seconds: number) => Date.UTC(2026, 10, 25, 21, 0, 0) + seconds * 1000

  it('draws the instantaneous rates with current, peak and average', () => {
    const rates = [
      { at: at(0), value: 8 },
      { at: at(2), value: 12 },
      { at: at(4), value: 11 },
    ]
    const { container } = render(<TelemetryPanel rates={rates} />)
    expect(screen.getByRole('img', { name: 'Ediciones por segundo, 3 muestras' })).toBeInTheDocument()
    const readouts = within(container.querySelector('.readouts') as HTMLElement)
    expect(readouts.getByText('11.0 ed/s')).toBeInTheDocument()
    expect(readouts.getByText('12.0 ed/s')).toBeInTheDocument()
    expect(readouts.getByText('10.3 ed/s')).toBeInTheDocument()
    expect(container.querySelector('.chart-line')).not.toBeNull()
    expect(container.querySelector('.chart-marker')).toHaveStyle({ left: '100%' })
    // The y axis goes up to a round number above the peak.
    expect(container.querySelector('.chart-axis')).toHaveTextContent('20100')
    // The window is the time between the first and the last sample.
    expect(screen.getByText('−4 s · 3 muestras')).toBeInTheDocument()
  })

  it('waits for two stats readings', () => {
    const { container } = render(<TelemetryPanel rates={[{ at: at(0), value: 5 }]} />)
    expect(screen.getByText('Esperando dos lecturas de /api/stats…')).toBeInTheDocument()
    expect(container.querySelector('.chart-line')).toBeNull()
    expect(screen.getByText('−0 s · 1 muestras')).toBeInTheDocument()
  })

  it('has no readouts without samples', () => {
    const { container } = render(<TelemetryPanel rates={[]} />)
    expect(container.querySelector('.readouts')).toBeNull()
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
