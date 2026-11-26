import type { ReactNode } from 'react'

interface PanelProps {
  title: string
  // Small text or a control on the right side of the title bar.
  aside?: ReactNode
  // Extra classes, for example the grid area of the panel.
  className?: string
  children: ReactNode
}

// A console panel: thin border, corner marks, a title bar and a body that
// scrolls inside the panel, so the page itself does not scroll.
export function Panel({ title, aside, className, children }: PanelProps) {
  return (
    <section className={className ? `card ${className}` : 'card'} aria-label={title}>
      <header className="card-head">
        <h2>{title}</h2>
        {aside && <div className="card-aside">{aside}</div>}
      </header>
      <div className="card-body">{children}</div>
    </section>
  )
}
