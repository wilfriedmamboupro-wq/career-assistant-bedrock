import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ChatResponse } from '../api'
import { ChatWidget } from './ChatWidget'

const reply = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  session_id: 's-1',
  answer: 'Deux jours de télétravail par semaine [1].',
  sources: [{ id: 1, title: 'Mode hybride', url: 'https://example.com/hybrid', snippet: '' }],
  jobs: [],
  grounded: true,
  guardrail: { input_masked: false, blocked: false },
  ...over,
})

function mockFetch(...bodies: unknown[]) {
  const fn = vi.spyOn(globalThis, 'fetch')
  for (const body of bodies) {
    fn.mockResolvedValueOnce(new Response(JSON.stringify(body), { status: 200 }))
  }
  return fn
}

async function ask(text: string) {
  await userEvent.type(screen.getByLabelText('Votre question…'), text)
  await userEvent.click(screen.getByRole('button', { name: 'Envoyer' }))
}

describe('ChatWidget', () => {
  afterEach(() => {
    cleanup()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('always shows the non-affiliation notice and the disclaimer', () => {
    render(<ChatWidget defaultOpen />)
    expect(screen.getByText(/non affilié/)).toBeInTheDocument()
    expect(screen.getByText(/Je peux me tromper/)).toBeInTheDocument()
  })

  it('sends the question and renders the answer with its sources', async () => {
    const fetch = mockFetch(reply())
    render(<ChatWidget defaultOpen />)
    await ask('Télétravail ?')

    expect(await screen.findByText(/Deux jours de télétravail/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Mode hybride' })).toHaveAttribute(
      'href',
      'https://example.com/hybrid',
    )
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('/api/chat')
    expect(JSON.parse(init!.body as string)).toEqual({ message: 'Télétravail ?', session_id: null })
  })

  it('reuses the session id on the next question', async () => {
    const fetch = mockFetch(reply(), reply({ answer: 'Suite.' }))
    render(<ChatWidget defaultOpen />)
    await ask('Un')
    await screen.findByText(/Deux jours/)
    await ask('Deux')
    await screen.findByText('Suite.')
    expect(JSON.parse(fetch.mock.calls[1][1]!.body as string).session_id).toBe('s-1')
  })

  it('renders job cards and the PII-masked notice', async () => {
    mockFetch(
      reply({
        answer: 'Un poste correspond.',
        sources: [],
        guardrail: { input_masked: true, blocked: false },
        jobs: [
          {
            id: 'J1',
            title: 'Analyste de données',
            city: 'Montréal',
            language: 'bilingual',
            url: 'https://example.com/j1',
            summary: '',
          },
        ],
      }),
    )
    render(<ChatWidget defaultOpen />)
    await ask('Postes ?')

    expect(await screen.findByText('Analyste de données')).toBeInTheDocument()
    expect(screen.getByText('Montréal · Bilingue')).toBeInTheDocument()
    expect(screen.getByText(/renseignements personnels ont été masqués/)).toBeInTheDocument()
  })

  it('shows an error message when the API fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('', { status: 503 }))
    render(<ChatWidget defaultOpen />)
    await ask('Bonjour')
    expect(await screen.findByText(/Le service ne répond pas/)).toBeInTheDocument()
  })

  it('creates a recruiter ticket once a session exists', async () => {
    const fetch = mockFetch(reply(), { ticket_id: 'abc', message: 'Demande n° abc transmise' })
    render(<ChatWidget defaultOpen />)
    const recruiter = screen.getByRole('button', { name: /Parler à un recruteur/ })
    expect(recruiter).toBeDisabled()

    await ask('Bonjour')
    await screen.findByText(/Deux jours/)
    await userEvent.click(recruiter)

    expect(await screen.findByText('Demande n° abc transmise')).toBeInTheDocument()
    expect(fetch.mock.calls[1][0]).toBe('/api/escalations')
    expect(screen.getByRole('button', { name: /Demande envoyée/ })).toBeDisabled()
  })

  it('starts a new conversation: clears messages, session and recruiter state', async () => {
    const fetch = mockFetch(
      reply(),
      { ticket_id: 'abc', message: 'Demande n° abc transmise' },
      reply({ session_id: 's-2', answer: 'Nouvelle réponse.' }),
    )
    render(<ChatWidget defaultOpen />)
    await ask('Un')
    await screen.findByText(/Deux jours/)
    await userEvent.click(screen.getByRole('button', { name: /Parler à un recruteur/ }))
    await screen.findByText('Demande n° abc transmise')

    await userEvent.click(screen.getByRole('button', { name: 'Nouvelle conversation' }))
    expect(screen.queryByText(/Deux jours/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Parler à un recruteur/ })).toBeDisabled()
    expect(sessionStorage.getItem('career-assistant-session')).toBeNull()

    await ask('Deux')
    await screen.findByText('Nouvelle réponse.')
    expect(JSON.parse(fetch.mock.calls[2][1]!.body as string).session_id).toBeNull()
  })

  it('switches the interface to English', async () => {
    render(<ChatWidget defaultOpen />)
    await userEvent.click(screen.getByRole('button', { name: 'Switch to English' }))
    expect(screen.getByText(/not affiliated/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
  })
})
