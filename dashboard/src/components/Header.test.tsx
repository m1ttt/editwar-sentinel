import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeStats } from '../test/fixtures'
import { environmentClass, Header } from './Header'

describe('Header', () => {
  it('shows the version and the environment badge', () => {
    render(<Header version={{ service: 'api', version: '1.4.0', environment: 'prod' }} status="open" stats={null} />)
    expect(screen.getByTestId('version')).toHaveTextContent('api 1.4.0')
    expect(screen.getByTestId('ui-version')).toHaveTextContent('ui dev')
    const badge = screen.getByTestId('environment')
    expect(badge).toHaveTextContent('prod')
    expect(badge).toHaveClass('env', 'env-prod')
  })

  it('says when the version is not available', () => {
    render(<Header version={null} status="connecting" stats={null} />)
    expect(screen.getByText('versión no disponible')).toBeInTheDocument()
    expect(screen.queryByTestId('environment')).not.toBeInTheDocument()
  })

  it.each([
    ['open', 'Conectado · stream en vivo'],
    ['connecting', 'Conectando…'],
    ['closed', 'Desconectado · reintentando'],
  ] as const)('shows the %s connection status', (status, label) => {
    render(<Header version={null} status={status} stats={null} />)
    expect(screen.getByRole('status')).toHaveTextContent(label)
  })

  it('shows the KPIs from the stats', () => {
    render(<Header version={null} status="open" stats={makeStats()} />)
    expect(screen.getByText('41.7')).toBeInTheDocument()
    expect(screen.getByText('12,345')).toBeInTheDocument()
    expect(screen.getByText('67')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
  })

  it('maps environments to badge classes', () => {
    expect(environmentClass('local')).toBe('env-local')
    expect(environmentClass('DEV')).toBe('env-dev')
    expect(environmentClass('staging')).toBe('env-other')
  })
})
