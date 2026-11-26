import type { DisputedArticle } from '../types'
import { Panel } from './Panel'

interface DisputedPanelProps {
  articles: DisputedArticle[]
}

export function DisputedPanel({ articles }: DisputedPanelProps) {
  // The bar of the first article is full. The other bars are relative to it.
  const max = Math.max(1, ...articles.map((article) => article.reverts))

  return (
    <Panel title="Artículos más disputados" aside="última hora">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Artículo</th>
              <th>Reversiones</th>
            </tr>
          </thead>
          <tbody>
            {articles.length === 0 && (
              <tr>
                <td colSpan={3} className="empty">
                  Sin reversiones en la última hora.
                </td>
              </tr>
            )}
            {articles.map((article, index) => (
              <tr key={`${article.wiki}:${article.title}`}>
                <td>{index + 1}</td>
                <td>
                  <a href={article.page_url} target="_blank" rel="noreferrer">
                    {article.title}
                  </a>{' '}
                  <span className="mono">{article.wiki}</span>
                </td>
                <td>
                  <span className="bar" aria-hidden="true">
                    <i style={{ width: `${(article.reverts / max) * 100}%` }} />
                  </span>{' '}
                  {article.reverts}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
