// Form validation for detection rules. The limits mirror
// DetectionRule.validate() in libs/domain/src/editwar_domain/rules.py.
import type { Rule, RuleInput, RuleKind } from '../types'

export const MIN_WINDOW_SECONDS = 10
export const MAX_WINDOW_SECONDS = 86_400

export const RULE_KINDS: { value: RuleKind; label: string }[] = [
  { value: 'revert_war', label: 'Guerra de reversiones' },
  { value: 'burst', label: 'Ráfaga de ediciones' },
  { value: 'bot_spike', label: 'Pico de bots' },
]

// Number fields stay as text while the user types.
export interface RuleFormValues {
  name: string
  kind: RuleKind
  window_seconds: string
  threshold: string
  min_users: string
  enabled: boolean
}

export type RuleErrors = Partial<Record<keyof RuleFormValues, string>>

function parseInteger(text: string): number | null {
  const trimmed = text.trim()
  if (trimmed === '') {
    return null
  }
  const value = Number(trimmed)
  return Number.isInteger(value) ? value : null
}

export function validateRule(values: RuleFormValues): RuleErrors {
  const errors: RuleErrors = {}
  if (values.name.trim() === '') {
    errors.name = 'El nombre es obligatorio.'
  }
  if (!RULE_KINDS.some((kind) => kind.value === values.kind)) {
    errors.kind = 'Tipo de regla no válido.'
  }
  const windowSeconds = parseInteger(values.window_seconds)
  if (windowSeconds === null || windowSeconds < MIN_WINDOW_SECONDS || windowSeconds > MAX_WINDOW_SECONDS) {
    errors.window_seconds = `La ventana debe ser un entero entre ${MIN_WINDOW_SECONDS} y ${MAX_WINDOW_SECONDS} segundos.`
  }
  const threshold = parseInteger(values.threshold)
  if (threshold === null || threshold < 1) {
    errors.threshold = 'El umbral debe ser un entero mayor o igual a 1.'
  }
  const minUsers = parseInteger(values.min_users)
  if (minUsers === null || minUsers < 1) {
    errors.min_users = 'Los usuarios mínimos deben ser un entero mayor o igual a 1.'
  }
  return errors
}

// Call only after validateRule() returned no errors.
export function toRuleInput(values: RuleFormValues): RuleInput {
  return {
    name: values.name.trim(),
    kind: values.kind,
    window_seconds: Number(values.window_seconds),
    threshold: Number(values.threshold),
    min_users: Number(values.min_users),
    enabled: values.enabled,
  }
}

// Initial form values: the rule being edited, or defaults for a new rule.
export function toFormValues(rule?: Rule): RuleFormValues {
  if (!rule) {
    return { name: '', kind: 'revert_war', window_seconds: '3600', threshold: '3', min_users: '2', enabled: true }
  }
  return {
    name: rule.name,
    kind: rule.kind,
    window_seconds: String(rule.window_seconds),
    threshold: String(rule.threshold),
    min_users: String(rule.min_users),
    enabled: rule.enabled,
  }
}

export function ruleToInput(rule: Rule): RuleInput {
  return {
    name: rule.name,
    kind: rule.kind,
    window_seconds: rule.window_seconds,
    threshold: rule.threshold,
    min_users: rule.min_users,
    enabled: rule.enabled,
  }
}
