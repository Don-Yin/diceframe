import { apiBlob } from '@/api/client'
import type { Locale } from '@/i18n'
import type { ScriptDraft, ScriptPreview } from './scriptTypes'

export type AiImportProgress = {
  stage: 'preparing' | 'organizing' | 'linking' | 'validating' | 'complete'
  completed: number; total: number; current?: number; chunks?: number
}

export async function organizeScript(draft: ScriptDraft, instructions: string, language: Locale,
  signal: AbortSignal, onProgress: (value: AiImportProgress) => void): Promise<ScriptPreview> {
  const response = await apiBlob(`/adventures/script/ai?language=${encodeURIComponent(language)}`, {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft, instructions, token_consent: true }),
  })
  if (!response.body) throw new Error('AI progress stream is unavailable')
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = '', result: ScriptPreview | undefined
  function consume(line: string) {
    if (!line.trim()) return
    const event = JSON.parse(line)
    if (event.type === 'error') throw new Error(event.error || 'AI organization failed')
    if (event.type === 'progress') {
      if (!['preparing', 'organizing', 'linking', 'validating', 'complete'].includes(event.stage)
        || !Number.isInteger(event.completed) || !Number.isInteger(event.total)
        || event.total < 1 || event.completed < 0 || event.completed > event.total) throw new Error('Invalid AI progress')
      const { stage, completed, total, current, chunks } = event
      onProgress({ stage, completed, total, ...(current === undefined ? {} : { current }), ...(chunks === undefined ? {} : { chunks }) })
    } else if (event.type === 'result') {
      if (result || event.preview?.ok !== true || !event.preview.draft || !Array.isArray(event.preview.blockers)) {
        throw new Error('Invalid AI draft result')
      }
      result = event.preview
    } else if (event.type !== 'heartbeat') throw new Error('Unknown AI progress event')
  }
  try {
    while (true) {
      signal.throwIfAborted()
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      if (buffer.length > 2 * 1024 * 1024) throw new Error('AI draft result is too large')
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) consume(line)
      if (done) break
    }
    if (buffer.trim()) consume(buffer)
    signal.throwIfAborted()
    if (!result) throw new Error('AI organization did not finish; the original draft was kept')
    return result
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
