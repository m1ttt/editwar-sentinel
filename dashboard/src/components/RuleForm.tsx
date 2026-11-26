import { useState, type FormEvent } from 'react'
import { errorMessage } from '../api/client'
import {
  MAX_WINDOW_SECONDS,
  MIN_WINDOW_SECONDS,
  RULE_KINDS,
  toFormValues,
  toRuleInput,
  validateRule,
  type RuleErrors,
  type RuleFormValues,
} from '../lib/ruleValidation'
import type { Rule, RuleInput, RuleKind } from '../types'

interface RuleFormProps {
  // The rule to edit. Without it the form creates a new rule.
  rule?: Rule
  onSubmit: (input: RuleInput) => Promise<void>
  onCancel: () => void
}

export function RuleForm({ rule, onSubmit, onCancel }: RuleFormProps) {
  const [values, setValues] = useState<RuleFormValues>(() => toFormValues(rule))
  const [errors, setErrors] = useState<RuleErrors>({})
  const [serverError, setServerError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const set = <K extends keyof RuleFormValues>(field: K, value: RuleFormValues[K]) => {
    setValues((current) => ({ ...current, [field]: value }))
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const found = validateRule(values)
    setErrors(found)
    if (Object.keys(found).length > 0) {
      return
    }
    setSaving(true)
    setServerError(null)
    try {
      await onSubmit(toRuleInput(values))
    } catch (err) {
      // For example a 422 from the api.
      setServerError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="rule-form" onSubmit={handleSubmit} noValidate aria-label="Formulario de regla">
      <h3>{rule ? `Editar regla: ${rule.name}` : 'Nueva regla'}</h3>
      {serverError && (
        <p className="error" role="alert">
          {serverError}
        </p>
      )}
      <div className="fields">
        <label>
          Nombre
          <input value={values.name} onChange={(event) => set('name', event.target.value)} />
          {errors.name && <span className="field-error">{errors.name}</span>}
        </label>
        <label>
          Tipo
          <select value={values.kind} onChange={(event) => set('kind', event.target.value as RuleKind)}>
            {RULE_KINDS.map((kind) => (
              <option key={kind.value} value={kind.value}>
                {kind.value} · {kind.label}
              </option>
            ))}
          </select>
          {errors.kind && <span className="field-error">{errors.kind}</span>}
        </label>
        <label>
          Ventana (s)
          <input
            type="number"
            min={MIN_WINDOW_SECONDS}
            max={MAX_WINDOW_SECONDS}
            value={values.window_seconds}
            onChange={(event) => set('window_seconds', event.target.value)}
          />
          {errors.window_seconds && <span className="field-error">{errors.window_seconds}</span>}
        </label>
        <label>
          Umbral
          <input
            type="number"
            min={1}
            value={values.threshold}
            onChange={(event) => set('threshold', event.target.value)}
          />
          {errors.threshold && <span className="field-error">{errors.threshold}</span>}
        </label>
        <label>
          Usuarios mínimos
          <input
            type="number"
            min={1}
            value={values.min_users}
            onChange={(event) => set('min_users', event.target.value)}
          />
          {errors.min_users && <span className="field-error">{errors.min_users}</span>}
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={values.enabled}
            onChange={(event) => set('enabled', event.target.checked)}
          />
          Activa
        </label>
      </div>
      <div className="form-actions">
        <button type="submit" className="btn primary" disabled={saving}>
          Guardar
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancelar
        </button>
      </div>
    </form>
  )
}
