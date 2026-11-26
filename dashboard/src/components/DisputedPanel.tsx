import type { DisputedArticle } from '../types'
import { Panel } from './Panel'

interface DisputedPanelProps {
  articles: DisputedArticle[]
}

export function DisputedPanel({ articles }: DisputedPanelProps) {
  // The bar of the first article is full. The other bars are relative to it.
  const max = Math.max(1, ...articles.map((article) => article.reverts))

  return (
    <Panel title="Artículos más disputados" aside="1 h" className="area-disputed">
      {articles.length === 0 ? (
        <p className="empty">Sin reversiones en la última hora.</p>
      ) : (
        <ol className="ranking">
          {articles.map((article, index) => (
            <li key={`${article.wiki}:${article.title}`}>
              <span className="rank mono">{String(index + 1).padStart(2, '0')}</span>
              <span className="ranking-title">
                <a href={article.page_url} target="_blank" rel="noreferrer">
                  {article.title}
                </a>
                <span className="mono">{article.wiki}</span>
              </span>
              <span className="bar" aria-hidden="true">
                <i style={{ width: `${(article.reverts / max) * 100}%` }} />
              </span>
              <span className="ranking-count mono">
                {article.reverts}
                <span className="sr-only"> reversiones</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}
