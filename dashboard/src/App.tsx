import { useEffect, useState } from 'react'
import { getStats, getVersion } from './api/client'
import { AlertsPanel } from './components/AlertsPanel'
import { DisputedPanel } from './components/DisputedPanel'
import { Header } from './components/Header'
import { LiveFeedPanel } from './components/LiveFeedPanel'
import { RulesPanel } from './components/RulesPanel'
import { useLiveFeed } from './hooks/useLiveFeed'
import type { VersionInfo } from './types'

export default function App() {
  const { edits, throughput, stats, lastAlert, status, connectionCount, dispatch } = useLiveFeed()
  const [version, setVersion] = useState<VersionInfo | null>(null)

  useEffect(() => {
    // The header shows version and environment, so a deploy is visible on the page.
    // It loads again after each WebSocket connection, so a new deploy shows its version.
    getVersion()
      .then(setVersion)
      .catch(() => setVersion(null))
  }, [connectionCount])

  useEffect(() => {
    // Fill the KPIs and the ranking before the first stats message arrives.
    // After that, the api sends a stats message on every connection.
    getStats()
      .then((data) => dispatch({ type: 'stats', data }))
      .catch(() => undefined)
  }, [dispatch])

  return (
    <>
      <Header version={version} status={status} stats={stats} />
      <main className="grid">
        <LiveFeedPanel edits={edits} throughput={throughput} />
        <DisputedPanel articles={stats?.top_disputed ?? []} />
        <AlertsPanel lastAlert={lastAlert} openCount={stats?.open_alerts} refreshKey={connectionCount} />
        <RulesPanel refreshKey={connectionCount} />
      </main>
    </>
  )
}
