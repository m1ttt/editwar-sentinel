import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeEdit, makeStats } from '../test/fixtures'
import { backoffDelay, liveFeedUrl, MAX_BACKOFF_MS, useLiveFeed } from './useLiveFeed'

// A minimal WebSocket double. Tests call open(), receive() and drop() on it.
class FakeSocket {
  static instances: FakeSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onclose: (() => void) | null = null
  closed = false

  constructor(public url: string) {
    FakeSocket.instances.push(this)
  }

  open() {
    this.onopen?.()
  }

  receive(data: unknown) {
    this.onmessage?.({ data })
  }

  drop() {
    this.onclose?.()
  }

  close() {
    this.closed = true
    this.onclose?.()
  }
}

function latest(): FakeSocket {
  return FakeSocket.instances[FakeSocket.instances.length - 1]
}

beforeEach(() => {
  FakeSocket.instances = []
  vi.stubGlobal('WebSocket', FakeSocket)
})

describe('liveFeedUrl', () => {
  it('uses ws for http pages and wss for https pages', () => {
    expect(liveFeedUrl({ protocol: 'http:', host: 'localhost:5173' })).toBe('ws://localhost:5173/ws/live')
    expect(liveFeedUrl({ protocol: 'https:', host: 'editwar.example' })).toBe('wss://editwar.example/ws/live')
  })

  it('defaults to the page location', () => {
    expect(liveFeedUrl()).toBe(`ws://${window.location.host}/ws/live`)
  })
})

describe('backoffDelay', () => {
  it('doubles the delay up to the maximum', () => {
    expect([0, 1, 2, 3].map(backoffDelay)).toEqual([1000, 2000, 4000, 8000])
    expect(backoffDelay(10)).toBe(MAX_BACKOFF_MS)
  })
})

describe('useLiveFeed', () => {
  it('stamps stats messages with the receive time, so the rate can be computed', () => {
    vi.useFakeTimers()
    vi.setSystemTime(Date.UTC(2026, 10, 25, 21, 0, 0))
    const { result } = renderHook(() => useLiveFeed('ws://test/ws/live'))
    act(() => latest().open())
    act(() => latest().receive(JSON.stringify({ type: 'stats', data: makeStats({ total_edits: 100 }) })))
    vi.setSystemTime(Date.UTC(2026, 10, 25, 21, 0, 2))
    act(() => latest().receive(JSON.stringify({ type: 'stats', data: makeStats({ total_edits: 130 }) })))
    expect(result.current.rates).toEqual([{ at: Date.UTC(2026, 10, 25, 21, 0, 2), value: 15 }])
  })

  it('connects, reports the status and applies messages', () => {
    const { result } = renderHook(() => useLiveFeed('ws://test/ws/live'))
    expect(result.current.status).toBe('connecting')
    expect(latest().url).toBe('ws://test/ws/live')

    expect(result.current.connectionCount).toBe(0)
    act(() => latest().open())
    expect(result.current.status).toBe('open')
    expect(result.current.connectionCount).toBe(1)

    act(() => latest().receive(JSON.stringify({ type: 'edit', data: makeEdit({ event_id: 'x' }) })))
    expect(result.current.edits.map((edit) => edit.event_id)).toEqual(['x'])

    // Invalid messages are ignored.
    act(() => latest().receive('not json'))
    expect(result.current.edits).toHaveLength(1)
  })

  it('reconnects with backoff after the socket drops', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useLiveFeed('ws://test/ws/live'))
    const first = latest()

    act(() => first.drop())
    expect(result.current.status).toBe('closed')

    const count = FakeSocket.instances.length
    act(() => vi.advanceTimersByTime(999))
    expect(FakeSocket.instances).toHaveLength(count)
    act(() => vi.advanceTimersByTime(1))
    expect(FakeSocket.instances).toHaveLength(count + 1)

    // The second failure waits twice as long.
    act(() => latest().drop())
    act(() => vi.advanceTimersByTime(1999))
    expect(FakeSocket.instances).toHaveLength(count + 1)
    act(() => vi.advanceTimersByTime(1))
    expect(FakeSocket.instances).toHaveLength(count + 2)

    // A successful open resets the backoff.
    act(() => latest().open())
    act(() => latest().drop())
    act(() => vi.advanceTimersByTime(1000))
    expect(FakeSocket.instances).toHaveLength(count + 3)
  })

  it('closes the socket and does not reconnect after unmount', () => {
    vi.useFakeTimers()
    const { unmount } = renderHook(() => useLiveFeed('ws://test/ws/live'))
    const socket = latest()
    unmount()
    expect(socket.closed).toBe(true)
    act(() => vi.advanceTimersByTime(MAX_BACKOFF_MS))
    expect(FakeSocket.instances).toHaveLength(1)
  })
})
