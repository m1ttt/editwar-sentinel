import { describe, expect, it } from 'vitest'
import { makeRule } from '../test/fixtures'
import type { RuleKind } from '../types'
import { ruleToInput, toFormValues, toRuleInput, validateRule, type RuleFormValues } from './ruleValidation'

const valid: RuleFormValues = {
  name: 'Guerra de edición',
  kind: 'revert_war',
  window_seconds: '600',
  threshold: '4',
  min_users: '2',
  enabled: true,
}

describe('validateRule', () => {
  it('accepts a valid rule', () => {
    expect(validateRule(valid)).toEqual({})
  })

  it.each(['10', '86400'])('accepts the window limit %s', (window_seconds) => {
    expect(validateRule({ ...valid, window_seconds })).toEqual({})
  })

  it.each(['9', '86401', '', 'abc', '60.5'])('rejects the window %j', (window_seconds) => {
    expect(validateRule({ ...valid, window_seconds })).toHaveProperty('window_seconds')
  })

  it.each(['0', '-1', '', '1.5'])('rejects the threshold %j', (threshold) => {
    expect(validateRule({ ...valid, threshold })).toHaveProperty('threshold')
  })

  it.each(['0', '', 'x'])('rejects min_users %j', (min_users) => {
    expect(validateRule({ ...valid, min_users })).toHaveProperty('min_users')
  })

  it('rejects an empty name', () => {
    expect(validateRule({ ...valid, name: '   ' })).toEqual({ name: 'El nombre es obligatorio.' })
  })

  it('rejects an unknown kind', () => {
    expect(validateRule({ ...valid, kind: 'other' as RuleKind })).toHaveProperty('kind')
  })

  it('reports every invalid field at once', () => {
    const errors = validateRule({ ...valid, name: '', window_seconds: '1', threshold: '0', min_users: '0' })
    expect(Object.keys(errors).sort()).toEqual(['min_users', 'name', 'threshold', 'window_seconds'])
  })
})

describe('conversions', () => {
  it('converts form text to numbers and trims the name', () => {
    expect(toRuleInput({ ...valid, name: '  Regla  ', window_seconds: ' 600 ' })).toEqual({
      name: 'Regla',
      kind: 'revert_war',
      window_seconds: 600,
      threshold: 4,
      min_users: 2,
      enabled: true,
    })
  })

  it('gives defaults for a new rule that pass validation', () => {
    const values = toFormValues()
    expect(values.name).toBe('')
    expect(validateRule({ ...values, name: 'x' })).toEqual({})
  })

  it('fills the form from an existing rule', () => {
    expect(toFormValues(makeRule({ enabled: false }))).toEqual({
      name: 'Guerra de edición',
      kind: 'revert_war',
      window_seconds: '3600',
      threshold: '3',
      min_users: '2',
      enabled: false,
    })
  })

  it('removes the id from a rule', () => {
    expect(ruleToInput(makeRule())).not.toHaveProperty('id')
  })
})
