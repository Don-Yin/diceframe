import { apiUrl, authHeaders } from '@/api/client'
import { i18n } from '@/i18n'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface AssistantSource {
  source: string
  heading: string
}

export interface AssistantStreamHandlers {
  onDelta: (text: string) => void
  onSources?: (sources: AssistantSource[]) => void
  /** 服务端因输出截断需放大预算重试：清空当前已显示内容后重新流式。 */
  onReset?: () => void
}

export class AssistantStreamError extends Error {
  readonly code: string

  constructor(message: string, code = 'ASSISTANT_FAILED') {
    super(message)
    this.name = 'AssistantStreamError'
    this.code = code
  }
}

export async function streamAssistantChat(
  messages: ChatMessage[],
  locale: string,
  handlers: AssistantStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(apiUrl('/assistant/chat'), {
    method: 'POST',
    headers: authHeaders(undefined, true),
    body: JSON.stringify({ messages, language: locale }),
    signal,
    credentials: 'include',
  })
  if (!resp.ok || !resp.body) {
    throw new AssistantStreamError(await responseError(resp), `HTTP_${resp.status}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const consume = (final = false): boolean => {
    while (true) {
      const separator = buffer.match(/\r?\n\r?\n/)
      if (!separator || separator.index === undefined) break
      const block = buffer.slice(0, separator.index)
      buffer = buffer.slice(separator.index + separator[0].length)
      if (dispatchEvent(block, handlers)) return true
    }
    if (final && buffer.trim()) {
      const done = dispatchEvent(buffer, handlers)
      buffer = ''
      return done
    }
    return false
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        buffer += decoder.decode()
        consume(true)
        return
      }
      buffer += decoder.decode(value, { stream: true })
      if (consume()) {
        await reader.cancel()
        return
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function dispatchEvent(block: string, handlers: AssistantStreamHandlers): boolean {
  const lines = block.split(/\r?\n/)
  const event = lines.find(line => line.startsWith('event:'))?.slice(6).trim() || 'message'
  const data = lines
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).replace(/^ /, ''))
    .join('\n')
  if (event === 'done') return true
  if (!data) return false

  const payload = parsePayload(data)
  if (event === 'error') {
    throw new AssistantStreamError(
      typeof payload.error === 'string' ? payload.error : i18n.global.t('assistantError'),
      typeof payload.code === 'string' ? payload.code : 'ASSISTANT_FAILED',
    )
  }
  if (event === 'sources') {
    const sources = Array.isArray(payload.sources)
      ? payload.sources.filter(isAssistantSource)
      : []
    handlers.onSources?.(sources)
    return false
  }
  if (event === 'reset') {
    handlers.onReset?.()
    return false
  }
  if (typeof payload.delta === 'string') handlers.onDelta(payload.delta)
  return false
}

function parsePayload(data: string): Record<string, unknown> {
  try {
    const value = JSON.parse(data) as unknown
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {}
  } catch {
    return {}
  }
}

function isAssistantSource(value: unknown): value is AssistantSource {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const record = value as Record<string, unknown>
  return typeof record.source === 'string' && typeof record.heading === 'string'
}

async function responseError(resp: Response): Promise<string> {
  try {
    const payload = await resp.json() as { error?: unknown }
    if (typeof payload.error === 'string' && payload.error) return payload.error
  } catch {
    // Fall through to the stable UI message.
  }
  return i18n.global.t('assistantRequestFailed')
}
