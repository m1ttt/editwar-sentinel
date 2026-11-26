import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { fetchCalls, jsonResponse, makeGeo, makeStats, mockFetch } from './test/fixtures'

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
  it('renders every console panel with version and stats from the api', async () => {
    mockFetch((_method, url) => {
      if (url === '/api/version') return jsonResponse({ service: 'api', version: '0.3.0', environment: 'dev' })
      if (url === '/api/stats') return jsonResponse(makeStats())
      return jsonResponse([])
    })
    render(<App />)
    const titles = [
      'Nivel de amenaza',
      'Telemetría en vivo',
      'Incidentes',
      'Reglas de detección',
      'Flujo en vivo',
      'Artículos más disputados',
      'Actividad por wiki',
      'Mapa de incidentes',
    ]
    for (const title of titles) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    }
    expect(await screen.findByTestId('environment')).toHaveTextContent('dev')
    expect(await screen.findByText('41.7')).toBeInTheDocument()
    // The first stats also feed the telemetry chart and the threat gauge.
    // One sample, so the current, peak and average readouts are the same.
    expect(screen.getAllByText('41.7 ed/s', { selector: '.readouts dd' })).toHaveLength(3)
    expect(screen.getByRole('img', { name: 'Nivel Alto, 71 de 100' })).toBeInTheDocument()
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
    expect(await screen.findAllByRole('alert')).toHaveLength(2)
  })
})
