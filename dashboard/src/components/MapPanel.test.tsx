import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeGeo } from '../test/fixtures'
import { LIST_COUNT, MapPanel, markerClass, markerLabel, PULSE_COUNT } from './MapPanel'

function points(count: number) {
  return Array.from({ length: count }, (_, index) =>
    makeGeo({
      title: `Artículo ${index}`,
      lat: 10 + index,
      lon: -100 + index,
      page_url: `https://en.wikipedia.org/wiki/A${index}`,
      timestamp: new Date(Date.UTC(2026, 10, 25, 21, 0, 59 - index)).toISOString(),
    }),
  )
}

describe('MapPanel', () => {
  it('says what the coordinates mean and shows an empty state', () => {
    const { container } = render(<MapPanel points={[]} />)
    expect(screen.getByText('ubicación del artículo editado')).toBeInTheDocument()
    expect(screen.getByText('Sin incidentes con ubicación todavía')).toBeInTheDocument()
    // The land is drawn even without points.
    expect(container.querySelector('.map-land')?.getAttribute('d')).toMatch(/^M/)
    expect(container.querySelectorAll('.geo-marker')).toHaveLength(0)
  })

  it('draws one marker per point at its projected position, newest on top', () => {
    const list = points(8)
    const { container } = render(<MapPanel points={list} />)
    expect(screen.getByRole('img', { name: 'Mapa con 8 reversiones y alertas, en la ubicación del artículo' })).toBeInTheDocument()
    const markers = container.querySelectorAll('.geo-marker')
    expect(markers).toHaveLength(8)
    // The newest point (index 0) is the last element, so it is drawn on top.
    const newest = markers[markers.length - 1]
    expect(newest).toHaveAttribute('href', 'https://en.wikipedia.org/wiki/A0')
    expect(newest).toHaveAttribute('target', '_blank')
    const dot = newest.querySelector('.geo-dot') as SVGCircleElement
    // lat 10, lon -100 -> x 80, y 74.
    expect(dot.getAttribute('cx')).toBe('80')
    expect(dot.getAttribute('cy')).toBe('74')
    expect(container.querySelectorAll('.geo-pulse')).toHaveLength(PULSE_COUNT)
    expect(newest.querySelector('title')?.textContent).toMatch(/^Reversión: Artículo 0 \(enwiki\) · /)
  })

  it('lists the newest points with links for the keyboard', () => {
    render(<MapPanel points={points(9)} />)
    const list = screen.getByRole('list', { name: 'Últimos puntos del mapa' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(LIST_COUNT)
    expect(within(items[0]).getByRole('link', { name: 'Artículo 0' })).toHaveAttribute('href', 'https://en.wikipedia.org/wiki/A0')
    expect(within(items[0]).getByText('REV')).toBeInTheDocument()
    expect(screen.queryByText('Sin incidentes con ubicación todavía')).not.toBeInTheDocument()
  })

  it('colors reverts with the accent and alerts by severity', () => {
    expect(markerClass({ kind: 'revert', severity: null })).toBe('geo-revert')
    expect(markerClass({ kind: 'alert', severity: 'high' })).toBe('geo-hi')
    expect(markerClass({ kind: 'alert', severity: 'medium' })).toBe('geo-me')
    expect(markerClass({ kind: 'alert', severity: null })).toBe('geo-lo')
    expect(markerClass({ kind: 'alert', severity: 'extreme' as 'high' })).toBe('geo-lo')
  })

  it('describes an alert with its rule kind and severity', () => {
    const alert = makeGeo({ kind: 'alert', severity: 'high', alert_kind: 'revert_war', title: '*', wiki: 'dewiki', timestamp: 'x' })
    expect(markerLabel(alert)).toBe('Alerta revert_war alta: Toda la wiki (dewiki) (dewiki) · --:--:--')
    expect(markerLabel(makeGeo({ kind: 'alert', timestamp: 'x' }))).toBe('Alerta: Guadalajara (enwiki) · --:--:--')
  })

  it('shows ALERTA in the list for an alert', () => {
    render(<MapPanel points={[makeGeo({ kind: 'alert', severity: 'medium', alert_kind: 'burst' })]} />)
    expect(screen.getByText('ALERTA')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Guadalajara' }).closest('li')).toHaveClass('geo-me')
  })
})
