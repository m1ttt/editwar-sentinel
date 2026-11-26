import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { emptyResponse, fetchCalls, jsonResponse, makeAlert, mockFetch } from '../test/fixtures'
import type { Alert } from '../types'
import { AlertsPanel } from './AlertsPanel'

const openAlert = makeAlert({ id: 'a1', title: 'Kubernetes', status: 'open' })
const ackAlert = makeAlert({ id: 'a2', title: 'Apache Kafka', status: 'acknowledged', acknowledged_by: 'ana', severity: 'medium' })
const dismissedAlert = makeAlert({ id: 'a3', title: '*', wiki: 'dewiki', status: 'dismissed', kind: 'bot_spike', severity: 'low' })

// The api answers GET with the list, PATCH with the alert and DELETE with 204.
function mockApi(alerts: Alert[] = [openAlert, ackAlert, dismissedAlert]) {
  return mockFetch((method) => {
    if (method === 'GET') return jsonResponse(alerts)
    if (method === 'DELETE') return emptyResponse()
    return jsonResponse(alerts[0])
  })
}

async function renderPanel() {
  render(<AlertsPanel lastAlert={null} openCount={1} />)
  await screen.findByText('Kubernetes')
}

function row(title: string): HTMLElement {
  return screen.getByText(title).closest('tr') as HTMLElement
}

describe('AlertsPanel', () => {
  it('loads and shows the alerts', async () => {
    const fetchMock = mockApi()
    await renderPanel()
    expect(fetchCalls(fetchMock)[0]).toEqual(['GET', '/api/alerts?limit=50', undefined])
    expect(screen.getByText('1 abiertas')).toBeInTheDocument()
    expect(screen.getByText('Toda la wiki (dewiki)')).toBeInTheDocument()
    expect(within(row('Kubernetes')).getByText('alta')).toHaveClass('pill', 'hi')
    expect(within(row('Kubernetes')).getByText('reverts: 4 · users: Editor_B, Editor_C')).toBeInTheDocument()
    expect(within(row('Apache Kafka')).getByText('(ana)')).toBeInTheDocument()
  })

  it('shows the severity of the loaded alerts', async () => {
    mockApi()
    await renderPanel()
    const legend = screen.getByRole('list', { name: 'Severidad de las 3 alertas cargadas' })
    expect(within(legend).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['alta 1', 'media 1', 'baja 1'])
    expect(row('Kubernetes')).toHaveClass('sev-row-hi', 'status-open')
    expect(row('Toda la wiki (dewiki)')).toHaveClass('sev-row-lo', 'status-dismissed')
  })

  it('shows unknown severity and status values as they come', async () => {
    const odd = { ...makeAlert({ id: 'x', title: 'Rareza' }), severity: 'critical', status: 'archived' } as unknown as Alert
    mockApi([odd])
    render(<AlertsPanel lastAlert={null} />)
    await screen.findByText('Rareza')
    expect(within(row('Rareza')).getByText('critical')).toHaveClass('pill', 'lo')
    expect(within(row('Rareza')).getByText('archived')).toBeInTheDocument()
    expect(row('Rareza')).toHaveClass('sev-row-lo')
  })

  it('flashes the row of the alert that just arrived', async () => {
    mockApi()
    const { rerender } = render(<AlertsPanel lastAlert={null} />)
    await screen.findByText('Kubernetes')
    expect(row('Apache Kafka')).not.toHaveClass('row-new')
    rerender(<AlertsPanel lastAlert={ackAlert} />)
    await waitFor(() => expect(row('Apache Kafka')).toHaveClass('row-new'))
    expect(row('Kubernetes')).not.toHaveClass('row-new')
  })

  it('shows only the buttons that fit the alert status', async () => {
    mockApi()
    await renderPanel()
    expect(within(row('Kubernetes')).getAllByRole('button').map((b) => b.textContent)).toEqual(['Reconocer', 'Descartar', 'Eliminar'])
    expect(within(row('Apache Kafka')).getAllByRole('button').map((b) => b.textContent)).toEqual(['Descartar', 'Eliminar'])
    expect(within(row('Toda la wiki (dewiki)')).getAllByRole('button').map((b) => b.textContent)).toEqual(['Eliminar'])
  })

  it('acknowledges with the operator name', async () => {
    const fetchMock = mockApi()
    await renderPanel()
    const user = userEvent.setup()
    const operator = screen.getByLabelText('Operador')
    await user.clear(operator)
    await user.type(operator, 'maria')
    await user.click(within(row('Kubernetes')).getByRole('button', { name: 'Reconocer' }))
    await waitFor(() =>
      expect(fetchCalls(fetchMock)).toContainEqual(['PATCH', '/api/alerts/a1', { status: 'acknowledged', user: 'maria' }]),
    )
    // The list reloads after the action.
    await waitFor(() => expect(fetchCalls(fetchMock).filter(([method]) => method === 'GET')).toHaveLength(2))
  })

  it('disables Reconocer without an operator name', async () => {
    mockApi()
    await renderPanel()
    await userEvent.clear(screen.getByLabelText('Operador'))
    expect(within(row('Kubernetes')).getByRole('button', { name: 'Reconocer' })).toBeDisabled()
  })

  it('dismisses an alert', async () => {
    const fetchMock = mockApi()
    await renderPanel()
    await userEvent.click(within(row('Apache Kafka')).getByRole('button', { name: 'Descartar' }))
    await waitFor(() => expect(fetchCalls(fetchMock)).toContainEqual(['PATCH', '/api/alerts/a2', { status: 'dismissed' }]))
  })

  it('deletes an alert after confirmation', async () => {
    const fetchMock = mockApi()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await renderPanel()
    await userEvent.click(within(row('Kubernetes')).getByRole('button', { name: 'Eliminar' }))
    await waitFor(() => expect(fetchCalls(fetchMock)).toContainEqual(['DELETE', '/api/alerts/a1', undefined]))
  })

  it('does not delete when the user cancels', async () => {
    const fetchMock = mockApi()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    await renderPanel()
    await userEvent.click(within(row('Kubernetes')).getByRole('button', { name: 'Eliminar' }))
    expect(fetchCalls(fetchMock).some(([method]) => method === 'DELETE')).toBe(false)
  })

  it('filters by status', async () => {
    const fetchMock = mockApi()
    await renderPanel()
    await userEvent.selectOptions(screen.getByLabelText('Estado'), 'acknowledged')
    await waitFor(() => expect(fetchCalls(fetchMock).at(-1)).toEqual(['GET', '/api/alerts?status=acknowledged&limit=50', undefined]))
  })

  it('reloads when a new alert arrives from the WebSocket', async () => {
    const fetchMock = mockApi()
    const { rerender } = render(<AlertsPanel lastAlert={null} />)
    await screen.findByText('Kubernetes')
    rerender(<AlertsPanel lastAlert={makeAlert({ id: 'new' })} />)
    await waitFor(() => expect(fetchCalls(fetchMock)).toHaveLength(2))
  })

  it('reloads when the refresh key changes', async () => {
    const fetchMock = mockApi()
    const { rerender } = render(<AlertsPanel lastAlert={null} refreshKey={0} />)
    await screen.findByText('Kubernetes')
    rerender(<AlertsPanel lastAlert={null} refreshKey={1} />)
    await waitFor(() => expect(fetchCalls(fetchMock)).toHaveLength(2))
  })

  it('shows api errors', async () => {
    mockFetch((method) => (method === 'GET' ? jsonResponse([openAlert]) : jsonResponse({ detail: 'Alert not found' }, 404)))
    await renderPanel()
    await userEvent.click(within(row('Kubernetes')).getByRole('button', { name: 'Descartar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Alert not found')
  })

  it('shows an empty state and a load error', async () => {
    mockFetch(() => new Response('bad gateway', { status: 502 }))
    render(<AlertsPanel lastAlert={null} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 502')
    expect(screen.getByText('No hay alertas.')).toBeInTheDocument()
  })
})
