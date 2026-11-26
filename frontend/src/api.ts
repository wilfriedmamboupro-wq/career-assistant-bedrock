// Same-origin "/api" in every environment: Vite proxies it locally,
// CloudFront routes it to API Gateway in AWS (no CORS to manage).
const BASE = import.meta.env.VITE_API_URL ?? '/api'

export interface Source {
  id: number
  title: string
  url: string | null
  snippet: string
}

export interface Job {
  id: string
  title: string
  city: string
  language: 'fr' | 'en' | 'bilingual'
  url: string
  summary: string
}

export interface ChatResponse {
  session_id: string
  answer: string
  sources: Source[]
  jobs: Job[]
  grounded: boolean
  guardrail: { input_masked: boolean; blocked: boolean }
}

export interface EscalationResponse {
  ticket_id: string
  message: string
}

export class ApiError extends Error {
  readonly status: number
  constructor(status: number) {
    super(`API error ${status}`)
    this.status = status
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new ApiError(res.status)
  return res.json() as Promise<T>
}

export const sendMessage = (message: string, sessionId: string | null) =>
  post<ChatResponse>('/chat', { message, session_id: sessionId })

export const requestRecruiter = (sessionId: string, topic: string) =>
  post<EscalationResponse>('/escalations', { session_id: sessionId, topic })
