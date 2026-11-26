import type { ChatResponse } from '../api'
import type { Strings } from '../i18n'

interface Props {
  reply: ChatResponse
  t: Strings
}

export function AssistantMessage({ reply, t }: Props) {
  return (
    <div className="msg msg-assistant">
      {reply.guardrail.input_masked && (
        <p className="notice" role="note">
          🔒 {t.masked}
        </p>
      )}
      <p className="msg-text">{reply.answer}</p>

      {reply.jobs.length > 0 && (
        <section aria-label={t.jobs} className="jobs">
          {reply.jobs.map((job) => (
            <article key={job.id} className="job-card">
              <h4>{job.title}</h4>
              <p className="job-meta">
                {job.city} · {t.jobLang[job.language]}
              </p>
              <a href={job.url} target="_blank" rel="noopener noreferrer">
                {t.viewJob} ↗
              </a>
            </article>
          ))}
        </section>
      )}

      {reply.sources.length > 0 && (
        <details className="sources" open>
          <summary>{t.sources}</summary>
          <ol>
            {reply.sources.map((s) => (
              <li key={s.id} value={s.id}>
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer">
                    {s.title}
                  </a>
                ) : (
                  s.title
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  )
}
