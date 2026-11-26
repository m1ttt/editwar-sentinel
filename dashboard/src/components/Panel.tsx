import type { ReactNode } from 'react'

interface PanelProps {
  title: string
  // Small text or a control on the right side of the title bar.
  aside?: ReactNode
  children: ReactNode
}

export function Panel({ title, aside, children }: PanelProps) {
  return (
    <section className="card" aria-label={title}>
      <header className="card-head">
        <h2>{title}</h2>
        {aside && <div className="card-aside">{aside}</div>}
      </header>
      {children}
    </section>
  )
}
