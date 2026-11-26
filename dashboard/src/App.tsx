import { useEffect, useState } from 'react'
import { getStats, getVersion, listRecentGeo } from './api/client'
import { AlertsPanel } from './components/AlertsPanel'
import { DisputedPanel } from './components/DisputedPanel'
import { Header } from './components/Header'
import { KpiStrip } from './components/KpiStrip'
import { LiveFeedPanel } from './components/LiveFeedPanel'
import { MapPanel } from './components/MapPanel'
import { RulesPanel } from './components/RulesPanel'
import { TelemetryPanel } from './components/TelemetryPanel'
import { ThreatPanel } from './components/ThreatPanel'
import { WikiActivityPanel } from './components/WikiActivityPanel'
import { useLiveFeed } from './hooks/useLiveFeed'
import type { VersionInfo } from './types'

export default function App() {
  const { edits, throughput, stats, lastAlert, geo, status, connectionCount, dispatch } = useLiveFeed()
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

  useEffect(() => {
    // The map starts with the recent points. It loads again after each WebSocket
    // connection, because "geo" messages sent while the socket was closed are lost.
    listRecentGeo()
      .then((data) => dispatch({ type: 'geo_snapshot', data }))
      .catch(() => undefined)
  }, [dispatch, connectionCount])

  return (
    <div className="console">
      <Header version={version} status={status} />
      <KpiStrip stats={stats} throughput={throughput} />
      <main className="grid">
        {/* DOM order is the reading and tab order on narrow screens. CSS grid areas place the panels on wide screens. */}
        <ThreatPanel stats={stats} />
        <MapPanel points={geo} />
        <AlertsPanel lastAlert={lastAlert} openCount={stats?.open_alerts} refreshKey={connectionCount} />
        <RulesPanel refreshKey={connectionCount} />
        <TelemetryPanel throughput={throughput} />
        <LiveFeedPanel edits={edits} />
        <DisputedPanel articles={stats?.top_disputed ?? []} />
        <WikiActivityPanel edits={edits} />
      </main>
    </div>
  )
}
