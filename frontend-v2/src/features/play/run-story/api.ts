import { api, apiBlob } from '@/api/client'
import type { ScriptPreview } from '@/features/adventures/scriptTypes'

export interface StoryScene { id: string; title: string; kind: string; objective: string; description: string; public: boolean; exit: string; next_ids: string[]; hints: string[] }
export interface StoryPlan { format_version: number; theme: string; party_goal: string; mode: string; npc_policy: string; core_npcs: string[]; start: string; scenes: StoryScene[] }
export interface Finale { status: string; id?: string; revision?: number; epilogue?: string; recap?: string; gm_notes?: string; source_rounds?: number[]; receipt?: unknown; character?: unknown; characters?: Record<string, unknown>; character_names?: Record<string, string> }
export interface RunStoryState {
  ok: boolean; error?: string; run_id: string; adventure_bound?: boolean; blockers?: string[];
  available_npcs?: { id: string; name: string }[];
  story: { plan?: StoryPlan; revision?: number; current_id?: string; source?: string; exit?: string; stall_hint?: string; warnings?: string[]; candidate?: unknown; possible_next_nodes?: { id: string; name: string }[] };
  growth?: { supported: boolean; pending: { actor_uid: string; label: string }[]; receipts?: unknown };
  finale: Finale;
  carry_deliveries?: { id: string; status: string; game_key: string }[];
  context_diagnostics?: { text: string; max_chars: number; used_chars: number; source: string };
}
export const endpoint = (key: string) => `/games/${encodeURIComponent(key)}/run-story`
export const storyError = (error: unknown) => error instanceof Error ? error.message : String(error)
export async function loadStory(key: string): Promise<RunStoryState> {
  const result = await api<RunStoryState>(endpoint(key))
  if (!result || result.ok !== true || !result.story || !result.finale || typeof result.run_id !== 'string') throw new Error(result?.error || 'Story state is unavailable')
  return result
}
export const changeStory = (key: string, action: string, body: unknown) => api<RunStoryState>(`${endpoint(key)}/${action}`, { method: 'POST', body: JSON.stringify(body) })
export const prepareStoryAdventure = (key: string, body: unknown) => api<ScriptPreview & { error?: string }>(`${endpoint(key)}/adventure-draft`, { method: 'POST', body: JSON.stringify(body) })
export const carryGame = (key: string, body: unknown) => api<{ ok: boolean; error?: string; game_key: string }>(`${endpoint(key)}/carry`, { method: 'POST', body: JSON.stringify(body) })
export interface AiProgress { stage: string; completed: number; total: number }
export interface StoryDraft { plan?: StoryPlan; source?: string; run_id?: string; revision?: number; epilogue?: string; recap?: string; job_id?: string }
export async function generateStory(key: string, kind: 'plan' | 'finale', body: unknown, signal: AbortSignal, onProgress: (p: AiProgress) => void): Promise<StoryDraft> {
  const response = await apiBlob(`${endpoint(key)}/generate/${kind}`, { method: 'POST', body: JSON.stringify(body), signal })
  if (!response.body) throw new Error('Progress stream unavailable')
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = '', result: StoryDraft | undefined
  const consume = (line: string) => {
    if (!line.trim()) return
    const event = JSON.parse(line)
    if (event.type === 'error') throw new Error(event.error)
    if (event.type === 'progress') onProgress(event)
    if (event.type === 'result' && event.ok === true) result = event.draft
  }
  try {
    for (;;) {
      signal.throwIfAborted()
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      if (buffer.length > 2 * 1024 * 1024) throw new Error('AI response exceeds text limit')
      const lines = buffer.split('\n'); buffer = lines.pop() || ''
      lines.forEach(consume)
      if (done) break
    }
    if (buffer.trim()) consume(buffer)
    signal.throwIfAborted()
    if (!result) throw new Error('Generation did not complete; original state retained')
    return result
  } finally { await reader.cancel().catch(() => undefined); reader.releaseLock() }
}
export async function downloadRun(key: string, character = false, uid = '') {
  const response = await apiBlob(`${endpoint(key)}/export?kind=${character ? 'character' : 'recap'}&uid=${encodeURIComponent(uid)}`)
  const url = URL.createObjectURL(await response.blob())
  const a = document.createElement('a'); a.href = url; a.download = character ? 'diceframe-character.json' : 'diceframe-run-recap.json'; a.click()
  URL.revokeObjectURL(url)
}
