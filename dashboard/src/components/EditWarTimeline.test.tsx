import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { fetchCalls, jsonResponse, makeDiff, makeTimeline, makeTimelineEntry, mockFetch } from '../test/fixtures'
import { clearDiffCache, diffDocument, diffErrorMessage, diffHeight, DiffView } from './DiffView'
import { EditWarTimeline, shortComment } from './EditWarTimeline'

const SERVER = 'https://en.wikipedia.org'

beforeEach(() => {
  clearDiffCache()
})

function entries(): HTMLElement[] {
  return within(screen.getByRole('list', { name: 'Ediciones en orden cronológico' })).getAllByRole('listitem')
}

describe('EditWarTimeline', () => {
  it('summarizes the participants', () => {
    render(<EditWarTimeline timeline={makeTimeline()} serverUrl={SERVER} />)
    const items = within(screen.getByRole('list', { name: 'Participantes' })).getAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      '●Editor_B2 ediciones · 1 reversión · revertido 1 vez',
      '▲Editor_C1 edición · 1 reversión · revertido 1 vez',
      '■TidyBotbot1 edición · 0 reversiones · revertido 0 veces',
    ])
  })

  it('lists the edits oldest first with user, delta, badges and links', () => {
    render(<EditWarTimeline timeline={makeTimeline()} serverUrl={SERVER} />)
    const rows = entries()
    expect(rows).toHaveLength(4)
    expect(rows.map((row) => row.querySelector('.ew-user')?.textContent)).toEqual([
      '●Editor_B',
      '▲Editor_C',
      '●Editor_B',
      '■TidyBot',
    ])
    // The same user keeps the same color in every row.
    const color = (row: HTMLElement) => (row.querySelector('.ew-user') as HTMLElement).style.color
    expect(color(rows[0])).toBe(color(rows[2]))
    expect(color(rows[0])).not.toBe(color(rows[1]))

    expect(within(rows[0]).getByText('+300')).toHaveClass('delta-up')
    expect(within(rows[1]).getByText('-300')).toHaveClass('delta-down')
    expect(within(rows[3]).getByText('0')).not.toHaveClass('delta-up')

    expect(rows[0]).not.toHaveClass('is-revert')
    expect(rows[1]).toHaveClass('is-revert')
    expect(within(rows[1]).getByText('revierte a Editor_B')).toHaveAttribute(
      'title',
      'detectado por el comentario de la edición',
    )
    expect(within(rows[2]).getByText('revierte a Editor_C')).toBeInTheDocument()
    expect(within(rows[2]).getByText('(sin comentario)')).toBeInTheDocument()
    expect(within(rows[3]).getByText('bot')).toBeInTheDocument()

    expect(within(rows[1]).getByRole('link', { name: 'diff ↗' })).toHaveAttribute(
      'href',
      'https://en.wikipedia.org/w/index.php?diff=102&oldid=101',
    )
    expect(within(rows[1]).getByRole('link', { name: 'diff ↗' })).toHaveAttribute('target', '_blank')
  })

  it('shows "revert" when the reverted user is not known', () => {
    render(
      <EditWarTimeline
        timeline={[makeTimelineEntry({ is_revert: true, diff_url: '', rev_id: 0 })]}
        serverUrl={SERVER}
      />,
    )
    const [row] = entries()
    expect(within(row).getByText('revert')).not.toHaveAttribute('title')
    expect(within(row).queryByRole('link')).toBeNull()
    expect(within(row).queryByRole('button')).toBeNull()
  })

  it('cuts long comments and keeps the full text in the title', () => {
    const long = 'x'.repeat(200)
    render(<EditWarTimeline timeline={[makeTimelineEntry({ comment: long })]} serverUrl={SERVER} />)
    const comment = entries()[0].querySelector('.ew-comment') as HTMLElement
    expect(comment).toHaveAttribute('title', long)
    expect(comment.textContent).toHaveLength(90)
    expect(shortComment('  corto  ')).toBe('corto')
  })

  it('shows a note when older edits were left out', () => {
    const { rerender } = render(<EditWarTimeline timeline={makeTimeline()} serverUrl={SERVER} />)
    expect(screen.queryByText(/Solo se muestran/)).toBeNull()
    rerender(<EditWarTimeline timeline={makeTimeline()} serverUrl={SERVER} truncated />)
    expect(screen.getByText(/Solo se muestran las ediciones más recientes/)).toBeInTheDocument()
  })

  it('opens and closes the diff of one edit', async () => {
    const fetchMock = mockFetch(() => jsonResponse(makeDiff()))
    render(<EditWarTimeline timeline={makeTimeline()} serverUrl={SERVER} />)
    const row = entries()[1]
    const button = within(row).getByRole('button', { name: 'Ver cambio' })
    expect(button).toHaveAttribute('aria-expanded', 'false')

    await userEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(button).toHaveTextContent('Ocultar cambio')
    const frame = await within(row).findByTitle('Cambio entre r101 y r102')
    expect(document.getElementById(button.getAttribute('aria-controls') as string)).toContainElement(frame)
    expect(fetchCalls(fetchMock)).toEqual([
      ['GET', '/api/diff?server_url=https%3A%2F%2Fen.wikipedia.org&rev_id=102&old_rev_id=101', undefined],
    ])

    await userEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(within(row).queryByTitle('Cambio entre r101 y r102')).toBeNull()
  })
})

describe('DiffView', () => {
  it('loads the diff and renders it in a sandboxed iframe', async () => {
    mockFetch(() => jsonResponse(makeDiff()))
    render(<DiffView serverUrl={SERVER} revId={102} oldRevId={101} />)
    expect(screen.getByRole('status')).toHaveTextContent('Cargando cambio…')

    const frame = await screen.findByTitle('Cambio entre r101 y r102')
    expect(frame.tagName).toBe('IFRAME')
    expect(frame).toHaveAttribute('sandbox', '')
    const doc = frame.getAttribute('srcdoc') ?? ''
    expect(doc).toContain('<table class="diff">')
    expect(doc).toContain('diff-addedline')
    expect(doc).toContain("default-src 'none'")
    expect(screen.getByText('Editor_B → Editor_C')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'abrir en Wikipedia ↗' })).toHaveAttribute(
      'href',
      'https://en.wikipedia.org/w/index.php?diff=102&oldid=101',
    )
  })

  it('uses the cache for a diff that was already loaded', async () => {
    const fetchMock = mockFetch(() => jsonResponse(makeDiff()))
    const { unmount } = render(<DiffView serverUrl={SERVER} revId={102} oldRevId={101} />)
    await screen.findByTitle('Cambio entre r101 y r102')
    unmount()
    render(<DiffView serverUrl={SERVER} revId={102} oldRevId={101} />)
    expect(screen.getByTitle('Cambio entre r101 y r102')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('says when the diff has no visible text change', async () => {
    mockFetch(() => jsonResponse(makeDiff({ html: '  ', from_user: '', diff_url: '' })))
    render(<DiffView serverUrl={SERVER} revId={102} oldRevId={101} />)
    expect(await screen.findByText(/Sin cambios de texto visibles/)).toBeInTheDocument()
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('explains a new page without calling the api', () => {
    const fetchMock = mockFetch(() => jsonResponse(makeDiff()))
    render(<DiffView serverUrl={SERVER} revId={5} oldRevId={0} diffUrl="https://d" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Página nueva')
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
    expect(screen.queryByRole('link')).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('explains a 422 from the api as a new page', async () => {
    mockFetch(() => jsonResponse({ detail: 'old_rev_id is 0' }, 422))
    render(<DiffView serverUrl={SERVER} revId={5} oldRevId={4} diffUrl="https://d" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Página nueva')
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
    expect(screen.getByRole('link', { name: 'ver en Wikipedia ↗' })).toHaveAttribute('href', 'https://d')
  })

  it('shows an upstream error and retries', async () => {
    let calls = 0
    const fetchMock = mockFetch(() => {
      calls += 1
      return calls === 1 ? jsonResponse({ detail: 'upstream' }, 502) : jsonResponse(makeDiff())
    })
    render(<DiffView serverUrl={SERVER} revId={102} oldRevId={101} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Wikipedia no respondió')
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByTitle('Cambio entre r101 y r102')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('writes a message for each kind of error', () => {
    expect(diffErrorMessage(new Error('boom'))).toBe('No se pudo cargar el cambio: boom')
  })

  it('reports a missing revision without retry', async () => {
    mockFetch(() => jsonResponse({ detail: 'not found' }, 404))
    render(<DiffView serverUrl={SERVER} revId={102} oldRevId={101} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('ya no tiene esta revisión')
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
  })

  it('builds a themed document and estimates its height', () => {
    const doc = diffDocument('<tr><td>x</td></tr>', {
      '--panel': '#fff',
      '--panel-head': '#eee',
      '--line': '#ccc',
      '--text': '#111',
      '--text-faint': '#555',
      '--high-text': '#b00',
      '--ok': '#070',
      '--font-mono': 'monospace',
    })
    expect(doc).toContain('--panel:#fff;')
    expect(doc).toContain('<tbody><tr><td>x</td></tr></tbody>')
    expect(diffHeight('')).toBe(80)
    expect(diffHeight('<tr>a</tr>'.repeat(100))).toBe(420)
  })
})
