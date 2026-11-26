import { useEffect, useState } from 'react'
import { createRule, deleteRule, errorMessage, listRules, updateRule } from '../api/client'
import { ruleToInput } from '../lib/ruleValidation'
import type { Rule, RuleInput } from '../types'
import { Panel } from './Panel'
import { RuleForm } from './RuleForm'

// null: no form open. 'new': create form. A Rule: edit form for that rule.
type Editing = null | 'new' | Rule

interface RulesPanelProps {
  // A new value makes the panel reload (App passes the WebSocket connection count).
  refreshKey?: number
}

export function RulesPanel({ refreshKey = 0 }: RulesPanelProps) {
  const [rules, setRules] = useState<Rule[]>([])
  const [editing, setEditing] = useState<Editing>(null)
  const [error, setError] = useState<string | null>(null)
  // Incremented after each change to load the list again.
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    // "ignore" drops the answer of an old request when a newer one has started.
    let ignore = false
    listRules()
      .then((data) => {
        if (!ignore) {
          setRules(data)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(errorMessage(err))
        }
      })
    return () => {
      ignore = true
    }
  }, [reloadKey, refreshKey])

  const reload = () => setReloadKey((key) => key + 1)

  // Errors from save go back to RuleForm, which shows them inside the form.
  const save = async (input: RuleInput) => {
    if (editing === 'new') {
      await createRule(input)
    } else if (editing) {
      await updateRule(editing.id, input)
    }
    setEditing(null)
    reload()
  }

  const run = async (action: () => Promise<unknown>) => {
    try {
      await action()
      reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const toggle = (rule: Rule) => run(() => updateRule(rule.id, { ...ruleToInput(rule), enabled: !rule.enabled }))

  const remove = (rule: Rule) => {
    if (window.confirm(`¿Eliminar la regla "${rule.name}"?`)) {
      void run(() => deleteRule(rule.id))
    }
  }

  const newRuleButton = (
    <button className="btn ghost" onClick={() => setEditing('new')}>
      + Nueva regla
    </button>
  )

  return (
    <Panel title="Reglas de detección" aside={newRuleButton} className="area-rules">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {editing && (
        <RuleForm
          // A new key resets the form when the user switches to another rule.
          key={editing === 'new' ? 'new' : editing.id}
          rule={editing === 'new' ? undefined : editing}
          onSubmit={save}
          onCancel={() => setEditing(null)}
        />
      )}
      <div className="table-wrap">
        <table className="rules">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Tipo</th>
              <th>Ventana</th>
              <th>Umbral</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  No hay reglas.
                </td>
              </tr>
            )}
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td className="rule-name">{rule.name}</td>
                <td className="mono">{rule.kind}</td>
                <td className="mono">{rule.window_seconds} s</td>
                <td>
                  {rule.threshold}
                  {rule.min_users > 1 && ` (≥${rule.min_users} usuarios)`}
                </td>
                <td>
                  <button
                    className={`pill toggle ${rule.enabled ? 'ok' : 'off'}`}
                    title={rule.enabled ? 'Pausar regla' : 'Activar regla'}
                    aria-label={`${rule.enabled ? 'Pausar' : 'Activar'} ${rule.name}`}
                    onClick={() => void toggle(rule)}
                  >
                    {rule.enabled ? 'activa' : 'pausada'}
                  </button>
                </td>
                <td className="actions">
                  <button className="btn" onClick={() => setEditing(rule)}>
                    Editar
                  </button>
                  <button className="btn danger" onClick={() => remove(rule)}>
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
