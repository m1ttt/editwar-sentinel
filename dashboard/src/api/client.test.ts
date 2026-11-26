import { describe, expect, it } from 'vitest'
import { ruleToInput } from '../lib/ruleValidation'
import { emptyResponse, fetchCalls, jsonResponse, makeAlert, makeRule, makeStats, mockFetch } from '../test/fixtures'
import {
  acknowledgeAlert,
  alertsQuery,
  ApiError,
  createRule,
  deleteAlert,
  deleteRule,
  dismissAlert,
  errorMessage,
  formatDetail,
  getRule,
  getStats,
  getVersion,
  listAlerts,
  listRules,
  updateRule,
} from './client'

describe('api client', () => {
  it('reads the version', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ service: 'api', version: '1.2.3', environment: 'dev' }))
    await expect(getVersion()).resolves.toEqual({ service: 'api', version: '1.2.3', environment: 'dev' })
    expect(fetchCalls(fetchMock)).toEqual([['GET', '/api/version', undefined]])
  })

  it('reads the stats', async () => {
    const stats = makeStats()
    const fetchMock = mockFetch(() => jsonResponse(stats))
    await expect(getStats()).resolves.toEqual(stats)
    expect(fetchCalls(fetchMock)[0][1]).toBe('/api/stats')
  })

  it('sends JSON headers only when there is a body', async () => {
    const fetchMock = mockFetch(() => jsonResponse(makeRule()))
    await getRule('r1')
    await createRule({ ...makeRule(), name: 'x' })
    const [, getInit] = fetchMock.mock.calls[0]
    const [, postInit] = fetchMock.mock.calls[1]
    expect(getInit?.headers).toEqual({ Accept: 'application/json' })
    expect(postInit?.headers).toEqual({ Accept: 'application/json', 'Content-Type': 'application/json' })
  })

  it('calls every rule endpoint with the right method and body', async () => {
    const rule = makeRule()
    const input = ruleToInput(rule)
    const fetchMock = mockFetch((method) => (method === 'DELETE' ? emptyResponse() : jsonResponse(method === 'GET' ? [rule] : rule)))

    await expect(listRules()).resolves.toEqual([rule])
    await createRule(input)
    await updateRule('r 1', input)
    await expect(deleteRule('r1')).resolves.toBeUndefined()

    expect(fetchCalls(fetchMock)).toEqual([
      ['GET', '/api/rules', undefined],
      ['POST', '/api/rules', input],
      ['PUT', '/api/rules/r%201', input],
      ['DELETE', '/api/rules/r1', undefined],
    ])
  })

  it('calls every alert endpoint with the right method and body', async () => {
    const alert = makeAlert()
    const fetchMock = mockFetch((method) => (method === 'DELETE' ? emptyResponse() : jsonResponse(method === 'GET' ? [alert] : alert)))

    await expect(listAlerts({ status: 'open', limit: 50 })).resolves.toEqual([alert])
    await acknowledgeAlert('a1', 'ana')
    await dismissAlert('a1')
    await deleteAlert('a1')

    expect(fetchCalls(fetchMock)).toEqual([
      ['GET', '/api/alerts?status=open&limit=50', undefined],
      ['PATCH', '/api/alerts/a1', { status: 'acknowledged', user: 'ana' }],
      ['PATCH', '/api/alerts/a1', { status: 'dismissed' }],
      ['DELETE', '/api/alerts/a1', undefined],
    ])
  })

  it('accepts a paginated alert list', async () => {
    const alert = makeAlert()
    mockFetch(() => jsonResponse({ items: [alert], total: 1 }))
    await expect(listAlerts()).resolves.toEqual([alert])
  })

  it('leaves empty filters out of the query string', () => {
    expect(alertsQuery({})).toBe('')
    expect(alertsQuery({ status: undefined, wiki: '', kind: 'burst', offset: 0 })).toBe('?kind=burst&offset=0')
  })

  it('throws ApiError with a string detail', async () => {
    mockFetch(() => jsonResponse({ detail: 'Rule not found' }, 404))
    const error = await getRule('missing').catch((err: unknown) => err)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, message: 'Rule not found' })
  })

  it('formats a FastAPI 422 validation list', async () => {
    mockFetch(() =>
      jsonResponse(
        {
          detail: [
            { loc: ['body', 'window_seconds'], msg: 'Input should be greater than or equal to 10' },
            { loc: ['body', 'threshold'], msg: 'Input should be greater than or equal to 1' },
          ],
        },
        422,
      ),
    )
    await expect(createRule({ ...makeRule(), window_seconds: 1 })).rejects.toThrow(
      'window_seconds: Input should be greater than or equal to 10; threshold: Input should be greater than or equal to 1',
    )
  })

  it('falls back to the HTTP status when the body is not JSON', async () => {
    mockFetch(() => new Response('<html>Bad Gateway</html>', { status: 502 }))
    await expect(getStats()).rejects.toThrow('HTTP 502')
  })

  it('falls back to the HTTP status when the JSON has no usable detail', async () => {
    mockFetch(() => jsonResponse({ detail: 42 }, 500))
    await expect(getStats()).rejects.toThrow('HTTP 500')
  })

  it('formats detail values', () => {
    expect(formatDetail('plain')).toBe('plain')
    expect(formatDetail([{ msg: 'no location' }])).toBe('no location')
    expect(formatDetail([{ loc: ['body'] }])).toBe('')
    expect(formatDetail({})).toBeNull()
  })

  it('turns any error into a message', () => {
    expect(errorMessage(new Error('boom'))).toBe('boom')
    expect(errorMessage('text')).toBe('text')
  })
})
