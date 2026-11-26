// WebSocket connection to /ws/live. It reconnects with exponential backoff
// when the socket closes, and stops when the component unmounts.
import { useEffect, useReducer, useState } from 'react'
import { initialFeedState, liveFeedReducer, parseMessage } from './liveFeedReducer'

export type ConnectionStatus = 'connecting' | 'open' | 'closed'

export const MAX_BACKOFF_MS = 30_000

// Same host as the page: ws:// for http pages and wss:// for https pages.
export function liveFeedUrl(location: Pick<Location, 'protocol' | 'host'> = window.location): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/ws/live`
}

// 1 s, 2 s, 4 s, 8 s ... up to 30 s.
export function backoffDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS)
}

export function useLiveFeed(url: string = liveFeedUrl()) {
  const [state, dispatch] = useReducer(liveFeedReducer, initialFeedState)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  // Counts successful connections. The panels reload their data when it changes,
  // for example when the api comes back after a restart or a new deploy.
  const [connectionCount, setConnectionCount] = useState(0)

  useEffect(() => {
    let socket: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    // True after unmount, so a close that we caused does not reconnect.
    let stopped = false

    const connect = () => {
      setStatus('connecting')
      socket = new WebSocket(url)
      socket.onopen = () => {
        attempt = 0
        setStatus('open')
        setConnectionCount((count) => count + 1)
      }
      socket.onmessage = (event: MessageEvent) => {
        const message = parseMessage(event.data)
        if (message) {
          dispatch(message)
        }
      }
      // The browser fires "close" after an error too, so one handler is enough.
      socket.onclose = () => {
        if (stopped) {
          return
        }
        setStatus('closed')
        timer = setTimeout(connect, backoffDelay(attempt))
        attempt += 1
      }
    }

    connect()

    return () => {
      stopped = true
      clearTimeout(timer)
      socket?.close()
    }
  }, [url])

  return { ...state, status, connectionCount, dispatch }
}
