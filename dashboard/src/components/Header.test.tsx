import { act, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { environmentClass, Header } from './Header'

describe('Header', () => {
  it('shows the version and the environment badge', () => {
    render(<Header version={{ service: 'api', version: '1.4.0', environment: 'prod' }} status="open" />)
    expect(screen.getByTestId('version')).toHaveTextContent('api 1.4.0')
    expect(screen.getByTestId('ui-version')).toHaveTextContent('ui dev')
    const badge = screen.getByTestId('environment')
    expect(badge).toHaveTextContent('prod')
    expect(badge).toHaveClass('env', 'env-prod')
  })

  it('says when the version is not available', () => {
    render(<Header version={null} status="connecting" />)
    expect(screen.getByText('versión no disponible')).toBeInTheDocument()
    expect(screen.queryByTestId('environment')).not.toBeInTheDocument()
  })

  it.each([
    ['open', 'Conectado · stream en vivo'],
    ['connecting', 'Conectando…'],
    ['closed', 'Desconectado · reintentando'],
  ] as const)('shows the %s connection status', (status, label) => {
    render(<Header version={null} status={status} />)
    expect(screen.getByRole('status')).toHaveTextContent(label)
  })

  it('shows a clock that moves every second', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 10, 25, 21, 4, 12))
    render(<Header version={null} status="open" />)
    expect(screen.getByText('21:04:12')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getByText('21:04:13')).toBeInTheDocument()
  })

  it('maps environments to badge classes', () => {
    expect(environmentClass('local')).toBe('env-local')
    expect(environmentClass('DEV')).toBe('env-dev')
    expect(environmentClass('staging')).toBe('env-other')
  })
})
