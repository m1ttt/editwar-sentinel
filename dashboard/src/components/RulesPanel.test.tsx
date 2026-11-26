import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { emptyResponse, fetchCalls, jsonResponse, makeRule, mockFetch } from '../test/fixtures'
import { RulesPanel } from './RulesPanel'

const warRule = makeRule()
const botRule = makeRule({
  id: '00000000-0000-0000-0000-000000000003',
  name: 'Pico de bots',
  kind: 'bot_spike',
  window_seconds: 60,
  threshold: 100,
  min_users: 1,
  enabled: false,
})

function mockApi() {
  return mockFetch((method) => {
    if (method === 'GET') return jsonResponse([warRule, botRule])
    if (method === 'DELETE') return emptyResponse()
    return jsonResponse(warRule)
  })
}

async function renderPanel() {
  render(<RulesPanel />)
  await screen.findByText('Guerra de edición')
}

function row(name: string): HTMLElement {
  return screen.getByText(name).closest('tr') as HTMLElement
}

describe('RulesPanel', () => {
  it('lists the rules', async () => {
    mockApi()
    await renderPanel()
    expect(within(row('Guerra de edición')).getByText('3600 s')).toBeInTheDocument()
    expect(within(row('Guerra de edición')).getByText('3 (≥2 usuarios)')).toBeInTheDocument()
    expect(within(row('Guerra de edición')).getByText('activa')).toBeInTheDocument()
    expect(within(row('Pico de bots')).getByText('pausada')).toBeInTheDocument()
  })

  it('creates a rule with POST', async () => {
    const fetchMock = mockApi()
    await renderPanel()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '+ Nueva regla' }))
    await user.type(screen.getByLabelText(/Nombre/), 'Nueva')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() =>
      expect(fetchCalls(fetchMock)).toContainEqual([
        'POST',
        '/api/rules',
        { name: 'Nueva', kind: 'revert_war', window_seconds: 3600, threshold: 3, min_users: 2, enabled: true },
      ]),
    )
    // The form closes after a successful save.
    await waitFor(() => expect(screen.queryByRole('form')).not.toBeInTheDocument())
  })

  it('edits a rule with PUT', async () => {
    const fetchMock = mockApi()
    await renderPanel()
    const user = userEvent.setup()
    await user.click(within(row('Pico de bots')).getByRole('button', { name: 'Editar' }))
    const threshold = screen.getByLabelText(/Umbral/)
    await user.clear(threshold)
    await user.type(threshold, '150')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() =>
      expect(fetchCalls(fetchMock)).toContainEqual([
        'PUT',
        `/api/rules/${botRule.id}`,
        { name: 'Pico de bots', kind: 'bot_spike', window_seconds: 60, threshold: 150, min_users: 1, enabled: false },
      ]),
    )
  })

  it('closes the form on cancel', async () => {
    mockApi()
    await renderPanel()
    await userEvent.click(screen.getByRole('button', { name: '+ Nueva regla' }))
    expect(screen.getByRole('form')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
  })

  it('toggles a rule with PUT and the opposite enabled value', async () => {
    const fetchMock = mockApi()
    await renderPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Pausar Guerra de edición' }))
    await waitFor(() =>
      expect(fetchCalls(fetchMock)).toContainEqual([
        'PUT',
        `/api/rules/${warRule.id}`,
        { name: warRule.name, kind: 'revert_war', window_seconds: 3600, threshold: 3, min_users: 2, enabled: false },
      ]),
    )
  })

  it('deletes a rule after confirmation', async () => {
    const fetchMock = mockApi()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await renderPanel()
    await userEvent.click(within(row('Pico de bots')).getByRole('button', { name: 'Eliminar' }))
    await waitFor(() => expect(fetchCalls(fetchMock)).toContainEqual(['DELETE', `/api/rules/${botRule.id}`, undefined]))
  })

  it('does not delete when the user cancels', async () => {
    const fetchMock = mockApi()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    await renderPanel()
    await userEvent.click(within(row('Pico de bots')).getByRole('button', { name: 'Eliminar' }))
    expect(fetchCalls(fetchMock).some(([method]) => method === 'DELETE')).toBe(false)
  })

  it('reloads when the refresh key changes', async () => {
    const fetchMock = mockApi()
    const { rerender } = render(<RulesPanel refreshKey={0} />)
    await screen.findByText('Guerra de edición')
    rerender(<RulesPanel refreshKey={1} />)
    await waitFor(() => expect(fetchCalls(fetchMock)).toHaveLength(2))
  })

  it('shows api errors', async () => {
    mockFetch((method) => (method === 'GET' ? jsonResponse([warRule]) : jsonResponse({ detail: 'Rule not found' }, 404)))
    await renderPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Pausar Guerra de edición' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Rule not found')
  })

  it('shows an empty state and a load error', async () => {
    mockFetch(() => new Response('bad gateway', { status: 502 }))
    render(<RulesPanel />)
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 502')
    expect(screen.getByText('No hay reglas.')).toBeInTheDocument()
  })
})
