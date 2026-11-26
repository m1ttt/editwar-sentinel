import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeEdit, makeStats } from '../test/fixtures'
import { DisputedPanel } from './DisputedPanel'
import { LiveFeedPanel } from './LiveFeedPanel'
import { Sparkline, sparklinePoints } from './Sparkline'

describe('LiveFeedPanel', () => {
  it('shows a waiting message without edits', () => {
    render(<LiveFeedPanel edits={[]} throughput={[]} />)
    expect(screen.getByText('Esperando ediciones…')).toBeInTheDocument()
  })

  it('shows edits with link, delta and badges', () => {
    const edits = [
      { ...makeEdit({ event_id: 'a', title: 'Docker (software)', is_bot: true }), reverted: false, delta: 4 },
      { ...makeEdit({ event_id: 'b', title: 'Kubernetes' }), reverted: true, delta: -1840 },
      { ...makeEdit({ event_id: 'c', title: 'Nuevo', change_type: 'new' }), reverted: false, delta: 0 },
      { ...makeEdit({ event_id: 'd', title: 'Contenedor', change_type: 'revert' }), reverted: true, delta: null },
    ]
    render(<LiveFeedPanel edits={edits} throughput={[1, 2]} />)

    expect(screen.getByRole('link', { name: 'Docker (software)' })).toHaveAttribute(
      'href',
      'https://en.wikipedia.org/wiki/Docker_(software)',
    )
    expect(screen.getByText('+4')).toHaveClass('delta-up')
    expect(screen.getByText('-1,840')).toHaveClass('delta-down')
    expect(screen.getByText('0')).not.toHaveClass('delta-up')
    expect(screen.getByText('–')).not.toHaveClass('delta-down')
    expect(screen.getByText('bot')).toBeInTheDocument()
    expect(screen.getAllByText('revert')).toHaveLength(2)
    expect(screen.getByText('nuevo')).toBeInTheDocument()
  })
})

describe('DisputedPanel', () => {
  it('ranks articles with links and relative bars', () => {
    const { container } = render(<DisputedPanel articles={makeStats().top_disputed} />)
    expect(screen.getByRole('link', { name: 'Kubernetes' })).toHaveAttribute('href', 'https://en.wikipedia.org/wiki/Kubernetes')
    const bars = container.querySelectorAll<HTMLElement>('.bar i')
    expect(bars[0].style.width).toBe('100%')
    expect(bars[1].style.width).toBe('50%')
  })

  it('shows an empty state', () => {
    render(<DisputedPanel articles={[]} />)
    expect(screen.getByText('Sin reversiones en la última hora.')).toBeInTheDocument()
  })
})

describe('Sparkline', () => {
  it('needs at least two values', () => {
    expect(sparklinePoints([5], 100, 50)).toBe('')
  })

  it('scales values to the box', () => {
    expect(sparklinePoints([0, 10], 100, 50)).toBe('0.0,48.0 100.0,2.0')
  })

  it('shows the last value', () => {
    const { container } = render(<Sparkline values={[1, 2.25]} />)
    expect(screen.getByText('2.3 ed/s')).toBeInTheDocument()
    expect(container.querySelector('polyline')).not.toBeNull()
  })

  it('shows a dash without values', () => {
    const { container } = render(<Sparkline values={[]} />)
    expect(screen.getByText('–')).toBeInTheDocument()
    expect(container.querySelector('polyline')).toBeNull()
  })
})
