import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeEdit, makeStats } from '../test/fixtures'
import { DisputedPanel } from './DisputedPanel'
import { eventTag, LiveFeedPanel } from './LiveFeedPanel'
import { Panel } from './Panel'
import { Sparkline, sparklinePoints } from './Sparkline'

describe('LiveFeedPanel', () => {
  it('shows a waiting message without edits', () => {
    render(<LiveFeedPanel edits={[]} />)
    expect(screen.getByText('Esperando ediciones…')).toBeInTheDocument()
  })

  it('shows edits with link, delta and badges', () => {
    const edits = [
      { ...makeEdit({ event_id: 'a', title: 'Docker (software)', is_bot: true }), reverted: false, delta: 4 },
      { ...makeEdit({ event_id: 'b', title: 'Kubernetes' }), reverted: true, delta: -1840 },
      { ...makeEdit({ event_id: 'c', title: 'Nuevo', change_type: 'new' }), reverted: false, delta: 0 },
      { ...makeEdit({ event_id: 'd', title: 'Contenedor', change_type: 'revert' }), reverted: true, delta: null },
    ]
    render(<LiveFeedPanel edits={edits} />)

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
    // The event type is an uppercase tag, so it does not clash with the lowercase pills.
    expect(screen.getAllByText('EDIT')).toHaveLength(2)
    expect(screen.getByText('NEW')).toBeInTheDocument()
    expect(screen.getByText('REVERT')).toBeInTheDocument()
    expect(screen.getAllByText('Editor_A', { selector: '.t-user' })).toHaveLength(4)
  })

  it('marks reverted rows', () => {
    const { container } = render(
      <LiveFeedPanel edits={[{ ...makeEdit({ event_id: 'r' }), reverted: true, delta: 3 }]} />,
    )
    expect(container.querySelector('.term-line')).toHaveClass('is-revert')
  })

  it('uses EDIT when the change type is empty', () => {
    expect(eventTag({ change_type: '' })).toBe('EDIT')
    expect(eventTag({ change_type: 'log' })).toBe('LOG')
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

describe('Panel', () => {
  it('names the section after its title and adds extra classes', () => {
    render(
      <Panel title="Prueba" aside="nota" className="area-x">
        contenido
      </Panel>,
    )
    const section = screen.getByRole('region', { name: 'Prueba' })
    expect(section).toHaveClass('card', 'area-x')
    expect(screen.getByText('nota')).toHaveClass('card-aside')
  })

  it('has only the card class without extra classes', () => {
    render(<Panel title="Simple">contenido</Panel>)
    expect(screen.getByRole('region', { name: 'Simple' }).className).toBe('card')
  })
})
