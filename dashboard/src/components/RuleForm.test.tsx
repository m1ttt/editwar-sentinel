import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { makeRule } from '../test/fixtures'
import { RuleForm } from './RuleForm'

describe('RuleForm', () => {
  it('shows validation errors and does not submit', async () => {
    const onSubmit = vi.fn(async () => undefined)
    render(<RuleForm onSubmit={onSubmit} onCancel={vi.fn()} />)
    const user = userEvent.setup()
    await user.clear(screen.getByLabelText(/Ventana/))
    await user.type(screen.getByLabelText(/Ventana/), '5')
    await user.clear(screen.getByLabelText(/Umbral/))
    await user.type(screen.getByLabelText(/Umbral/), '0')
    await user.clear(screen.getByLabelText(/Usuarios mínimos/))
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(screen.getByText('El nombre es obligatorio.')).toBeInTheDocument()
    expect(screen.getByText('La ventana debe ser un entero entre 10 y 86400 segundos.')).toBeInTheDocument()
    expect(screen.getByText('El umbral debe ser un entero mayor o igual a 1.')).toBeInTheDocument()
    expect(screen.getByText('Los usuarios mínimos deben ser un entero mayor o igual a 1.')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits numbers for a new rule', async () => {
    const onSubmit = vi.fn(async () => undefined)
    render(<RuleForm onSubmit={onSubmit} onCancel={vi.fn()} />)
    const user = userEvent.setup()
    expect(screen.getByRole('heading', { name: 'Nueva regla' })).toBeInTheDocument()
    await user.type(screen.getByLabelText(/Nombre/), 'Ráfaga')
    await user.selectOptions(screen.getByLabelText(/Tipo/), 'burst')
    await user.click(screen.getByLabelText(/Activa/))
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Ráfaga',
      kind: 'burst',
      window_seconds: 3600,
      threshold: 3,
      min_users: 2,
      enabled: false,
    })
  })

  it('starts with the values of the rule being edited', () => {
    render(<RuleForm rule={makeRule({ name: 'Pico de bots', window_seconds: 60 })} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Editar regla: Pico de bots' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Ventana/)).toHaveValue(60)
  })

  it('shows the server error when saving fails', async () => {
    const onSubmit = vi.fn(async () => {
      throw new ApiError(422, 'window_seconds: Input should be less than or equal to 86400')
    })
    render(<RuleForm rule={makeRule()} onSubmit={onSubmit} onCancel={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('window_seconds: Input should be less than or equal to 86400')
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeEnabled()
  })

  it('calls onCancel', async () => {
    const onCancel = vi.fn()
    render(<RuleForm onSubmit={vi.fn()} onCancel={onCancel} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(onCancel).toHaveBeenCalled()
  })
})
