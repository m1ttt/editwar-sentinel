import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { jsonResponse, makeStats, mockFetch } from './test/fixtures'

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
  it('renders the four panels with version and stats from the api', async () => {
    mockFetch((_method, url) => {
      if (url === '/api/version') return jsonResponse({ service: 'api', version: '0.3.0', environment: 'dev' })
      if (url === '/api/stats') return jsonResponse(makeStats())
      return jsonResponse([])
    })
    render(<App />)
    for (const title of ['Flujo en vivo', 'Artículos más disputados', 'Alertas', 'Reglas de detección']) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    }
    expect(await screen.findByTestId('environment')).toHaveTextContent('dev')
    expect(await screen.findByText('41.7')).toBeInTheDocument()
  })

  it('still renders when every api call fails', async () => {
    mockFetch(() => new Response('bad gateway', { status: 502 }))
    render(<App />)
    expect(await screen.findByText('versión no disponible')).toBeInTheDocument()
    expect(screen.getByText('Esperando ediciones…')).toBeInTheDocument()
    expect(await screen.findAllByRole('alert')).toHaveLength(2)
  })
})
