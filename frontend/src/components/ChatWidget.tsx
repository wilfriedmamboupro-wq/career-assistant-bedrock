import { useEffect, useRef, useState, type FormEvent } from 'react'
import { requestRecruiter, sendMessage, type ChatResponse } from '../api'
import { strings, type Lang } from '../i18n'
import { AssistantMessage } from './AssistantMessage'

type Entry =
  | { kind: 'user'; text: string }
  | { kind: 'assistant'; reply: ChatResponse }
  | { kind: 'system'; text: string }

const SESSION_KEY = 'career-assistant-session'

export function ChatWidget({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const [lang, setLang] = useState<Lang>('fr')
  const [entries, setEntries] = useState<Entry[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [escalated, setEscalated] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(() =>
    sessionStorage.getItem(SESSION_KEY),
  )
  const logRef = useRef<HTMLDivElement>(null)
  const t = strings[lang]

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight })
  }, [entries, busy])

  async function ask(question: string) {
    const text = question.trim()
    if (!text || busy) return
    setEntries((e) => [...e, { kind: 'user', text }])
    setInput('')
    setBusy(true)
    try {
      const reply = await sendMessage(text, sessionId)
      setSessionId(reply.session_id)
      sessionStorage.setItem(SESSION_KEY, reply.session_id)
      setEntries((e) => [...e, { kind: 'assistant', reply }])
    } catch {
      setEntries((e) => [...e, { kind: 'system', text: t.error }])
    } finally {
      setBusy(false)
    }
  }

  async function escalate() {
    if (!sessionId || escalated) return
    try {
      const res = await requestRecruiter(sessionId, '')
      setEscalated(true)
      setEntries((e) => [...e, { kind: 'system', text: res.message }])
    } catch {
      setEntries((e) => [...e, { kind: 'system', text: t.error }])
    }
  }

  // New session: the server keeps the old one until its 7-day TTL, nothing is reused
  function resetConversation() {
    sessionStorage.removeItem(SESSION_KEY)
    setSessionId(null)
    setEntries([])
    setEscalated(false)
    setInput('')
  }

  function onSubmit(ev: FormEvent) {
    ev.preventDefault()
    void ask(input)
  }

  if (!open) {
    return (
      <button className="launcher" onClick={() => setOpen(true)} aria-label={t.open}>
        💬
      </button>
    )
  }

  return (
    <section className="widget" role="dialog" aria-label={t.title} lang={lang}>
      <header className="widget-header">
        <div>
          <h2>{t.title}</h2>
          <p className="badge">{t.badge}</p>
        </div>
        <div className="header-actions">
          <button
            className="ghost"
            onClick={resetConversation}
            disabled={busy || entries.length === 0}
            aria-label={t.reset}
            title={t.reset}
          >
            ↺
          </button>
          <button
            className="ghost"
            onClick={() => setLang(lang === 'fr' ? 'en' : 'fr')}
            aria-label={t.langLabel}
          >
            {t.langSwitch}
          </button>
          <button className="ghost" onClick={() => setOpen(false)} aria-label={t.close}>
            ✕
          </button>
        </div>
      </header>

      <div className="log" ref={logRef} aria-live="polite">
        <div className="msg msg-assistant">
          <p className="msg-text">{t.welcome}</p>
        </div>
        {entries.length === 0 && (
          <div className="chips">
            {t.suggestions.map((s) => (
              <button key={s} className="chip" onClick={() => void ask(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {entries.map((entry, i) =>
          entry.kind === 'assistant' ? (
            <AssistantMessage key={i} reply={entry.reply} t={t} />
          ) : (
            <div key={i} className={`msg msg-${entry.kind}`}>
              <p className="msg-text">{entry.text}</p>
            </div>
          ),
        )}
        {busy && (
          <p className="typing" role="status">
            {t.thinking}
          </p>
        )}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <label className="sr-only" htmlFor="ca-input">
          {t.placeholder}
        </label>
        <input
          id="ca-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t.placeholder}
          maxLength={2000}
          autoComplete="off"
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {t.send}
        </button>
      </form>

      <footer className="widget-footer">
        <button className="link" onClick={() => void escalate()} disabled={!sessionId || escalated}>
          👤 {escalated ? t.recruiterDone : t.recruiter}
        </button>
        <p>{t.disclaimer}</p>
      </footer>
    </section>
  )
}
