import { ref } from 'vue'
import { useAssistantPreferences } from '@/composables/useAssistantPreferences'
import {
  ASSISTANT_REACTIONS,
  type AssistantReactionDetail,
  type AssistantReactionKind,
} from '@/features/assistant/reactions'

export type { AssistantReactionKind } from '@/features/assistant/reactions'

/*
 * Short-lived reactions of the DF Agent avatar to things happening at the
 * table. Producers only report what happened; the reaction catalogue decides
 * how it looks. Reactions are presentation only and never feed back into
 * rules or the agent's conversation.
 */

export interface AssistantReaction {
  id: number
  kind: AssistantReactionKind
  detail: AssistantReactionDetail
}

const current = ref<AssistantReaction | null>(null)
let sequence = 0
let timer: ReturnType<typeof setTimeout> | undefined
let startedAt = 0
const listeners = new Set<(reaction: AssistantReaction) => void>()

// A lower-priority reaction does not cut off a stronger one that has only
// just started (e.g. "Hit!" arriving right after "Critical hit!").
const PROTECT_MS = 900

export function reportAssistantReaction(kind: AssistantReactionKind, detail: AssistantReactionDetail = {}): void {
  const preferences = useAssistantPreferences()
  const spec = ASSISTANT_REACTIONS[kind]
  if (!preferences.reactions.value || !spec || preferences.disabledReactionCategories.value.includes(spec.category)) return
  const active = current.value
  if (active && Date.now() - startedAt < PROTECT_MS && ASSISTANT_REACTIONS[active.kind].priority > spec.priority) return
  sequence += 1
  const reaction = { id: sequence, kind, detail }
  current.value = reaction
  startedAt = Date.now()
  if (timer !== undefined) clearTimeout(timer)
  timer = setTimeout(() => {
    if (current.value?.id === reaction.id) current.value = null
    timer = undefined
  }, spec.durationMs)
  for (const listener of listeners) listener(reaction)
}

export function clearAssistantReaction(): void {
  if (timer !== undefined) clearTimeout(timer)
  timer = undefined
  current.value = null
}

/** Observe reactions as they start (e.g. to read them aloud). */
export function onAssistantReaction(listener: (reaction: AssistantReaction) => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function useAssistantReactions() {
  return { reaction: current, report: reportAssistantReaction, clear: clearAssistantReaction }
}
