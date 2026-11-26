import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { fetchCalls, jsonResponse, makeGeo, makeRule, makeStats, mockFetch } from './test/fixtures'

class SilentSocket {
  onopen = null
  onmessage = null
  onclose = null
  close() {}
}

beforeEach(() => {
  vi.stubGlobal('WebSocket', SilentSocket)
})

describe('App', () => {
  it('renders the live panels of the Monitor view with version and stats from the api', async () => {
    mockFetch((_method, url) => {
      if (url === '/api/version') return jsonResponse({ service: 'api', version: '0.3.0', environment: 'dev' })
      if (url === '/api/stats') return jsonResponse(makeStats())
      return jsonResponse([])
    })
    render(<App />)
    const titles = [
      'Mapa de incidentes',
      'Incidentes',
      'Telemetría en vivo',
      'Artículos más disputados',
      'Flujo en vivo',
      'Actividad por wiki',
    ]
    for (const title of titles) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    }
    // The rules are in the other view.
    expect(screen.queryByRole('heading', { name: 'Reglas de detección' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Nivel de amenaza' })).not.toBeInTheDocument()
    expect(screen.getByRole('tabpanel', { name: 'Monitor' })).toBeInTheDocument()
    expect(await screen.findByTestId('environment')).toHaveTextContent('dev')
    expect(await screen.findByText('41.7')).toBeInTheDocument()
    // One stats reading gives no rate yet: the chart needs two.
    expect(screen.getByText('Esperando dos lecturas de /api/stats…')).toBeInTheDocument()
  })

  it('switches to the Reglas view and back', async () => {
    mockFetch((_method, url) => {
      if (url === '/api/version') return jsonResponse({ service: 'api', version: '0.3.0', environment: 'dev' })
      if (url === '/api/stats') return jsonResponse(makeStats())
      if (url === '/api/rules') return jsonResponse([makeRule()])
      return jsonResponse([])
    })
    render(<App />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('tab', { name: 'Reglas' }))
    expect(screen.getByRole('tab', { name: 'Reglas' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel', { name: 'Reglas' })).toBeInTheDocument()
    expect(await screen.findByText('Guerra de edición')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Mapa de incidentes' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Monitor' }))
    expect(screen.getByRole('heading', { name: 'Mapa de incidentes' })).toBeInTheDocument()
  })

  it('loads the recent map points', async () => {
    const fetchMock = mockFetch((_method, url) => {
      if (url.startsWith('/api/geo/recent')) return jsonResponse([makeGeo()])
      if (url === '/api/stats') return jsonResponse(makeStats())
      if (url === '/api/version') return jsonResponse({ service: 'api', version: '0.3.0', environment: 'dev' })
      return jsonResponse([])
    })
    render(<App />)
    expect(await screen.findByRole('link', { name: 'Guadalajara' })).toBeInTheDocument()
    expect(fetchCalls(fetchMock).map(([, url]) => url)).toContain('/api/geo/recent?limit=200')
  })

  it('shows an empty map when the api has no geo endpoint yet', async () => {
    mockFetch((_method, url) => {
      if (url.startsWith('/api/geo/recent')) return jsonResponse({ detail: 'Not Found' }, 404)
      if (url === '/api/stats') return jsonResponse(makeStats())
      if (url === '/api/version') return jsonResponse({ service: 'api', version: '0.3.0', environment: 'dev' })
      return jsonResponse([])
    })
    render(<App />)
    expect(await screen.findByText('Sin incidentes con ubicación todavía')).toBeInTheDocument()
  })

  it('still renders when every api call fails', async () => {
    mockFetch(() => new Response('bad gateway', { status: 502 }))
    render(<App />)
    expect(await screen.findByText('versión no disponible')).toBeInTheDocument()
    expect(screen.getByText('Esperando ediciones…')).toBeInTheDocument()
    // Monitor has one panel that can show an api error: Incidentes.
    expect(await screen.findAllByRole('alert')).toHaveLength(1)
    await userEvent.click(screen.getByRole('tab', { name: 'Reglas' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('HTTP 502'))
    expect(screen.getByText('No hay reglas.')).toBeInTheDocument()
  })
})
