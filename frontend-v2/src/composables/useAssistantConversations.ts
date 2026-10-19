import { computed, ref, watch } from 'vue'
import {
  compactConversation,
  storedConversationMessages,
  useAssistant,
  type AssistantMessage,
} from '@/composables/useAssistant'

/*
 * DF Agent conversation history. The transcript lives in this browser (the
 * agent receives it with every request); each conversation also remembers
 * its own server session id so approvals and drafts come back with it. The
 * active conversation keeps using useAssistant's storage; this module keeps
 * the archive and switches between entries.
 */

export const ASSISTANT_CONVERSATIONS_STORAGE_KEY = 'diceframe_assistant_conversations'
export const MAX_ASSISTANT_CONVERSATIONS = 30
const TITLE_CHARS = 28

export interface AssistantConversation {
  id: string
  title: string
  customTitle?: boolean
  createdAt: number
  updatedAt: number
  sessionId: string | null
  messages: AssistantMessage[]
}

interface StoredArchive { activeId: string; items: AssistantConversation[] }

function newId(): string {
  try { return crypto.randomUUID() } catch { return `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}` }
}

function isConversation(value: unknown): value is AssistantConversation {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const record = value as Record<string, unknown>
  return typeof record.id === 'string' && typeof record.title === 'string'
    && typeof record.createdAt === 'number' && typeof record.updatedAt === 'number'
    && (record.sessionId === null || typeof record.sessionId === 'string')
}

function readArchive(): StoredArchive {
  try {
    const parsed = JSON.parse(localStorage.getItem(ASSISTANT_CONVERSATIONS_STORAGE_KEY) || 'null') as Partial<StoredArchive> | null
    const items = Array.isArray(parsed?.items)
      ? parsed.items.filter(isConversation).map(item => ({ ...item, messages: storedConversationMessages(item.messages) }))
      : []
    return { activeId: typeof parsed?.activeId === 'string' ? parsed.activeId : '', items }
  } catch {
    return { activeId: '', items: [] }
  }
}

export function conversationTitle(messages: AssistantMessage[], fallback: string): string {
  const first = messages.find(message => message.role === 'user' && message.content.trim())
  const text = (first?.content || '').replace(/\s+/g, ' ').trim()
  if (!text) return fallback
  return text.length > TITLE_CHARS ? `${text.slice(0, TITLE_CHARS)}…` : text
}

const stored = readArchive()
const items = ref<AssistantConversation[]>(stored.items)
const activeId = ref(stored.activeId || newId())
let watching = false

function save(): void {
  try {
    localStorage.setItem(ASSISTANT_CONVERSATIONS_STORAGE_KEY, JSON.stringify({ activeId: activeId.value, items: items.value }))
  } catch { /* Storage is optional; history stays available for this session. */ }
}

function sortAndTrim(): void {
  items.value.sort((left, right) => right.updatedAt - left.updatedAt)
  if (items.value.length > MAX_ASSISTANT_CONVERSATIONS) items.value.splice(MAX_ASSISTANT_CONVERSATIONS)
}

/** Copy the active conversation into the archive; empty ones are not kept. */
function syncActive(): void {
  const { messages, sessionId } = useAssistant()
  const index = items.value.findIndex(item => item.id === activeId.value)
  if (!messages.value.length) {
    if (index >= 0 && !items.value[index].messages.length) items.value.splice(index, 1)
    save()
    return
  }
  const snapshot = compactConversation(JSON.parse(JSON.stringify(messages.value)) as AssistantMessage[])
  const previous = index >= 0 ? items.value[index] : null
  const changed = !previous || JSON.stringify(previous.messages) !== JSON.stringify(snapshot) || previous.sessionId !== sessionId.value
  const entry: AssistantConversation = {
    id: activeId.value,
    title: previous?.customTitle ? previous.title : conversationTitle(snapshot, previous?.title || ''),
    customTitle: previous?.customTitle,
    createdAt: previous?.createdAt || Date.now(),
    updatedAt: changed ? Date.now() : previous.updatedAt,
    sessionId: sessionId.value,
    messages: snapshot,
  }
  if (index >= 0) items.value.splice(index, 1, entry)
  else items.value.unshift(entry)
  sortAndTrim()
  save()
}

function ensureWatching(): void {
  if (watching) return
  watching = true
  const { messages, streaming, actionBusy, sessionId } = useAssistant()
  // Archive at rest points rather than on every streamed character.
  watch([streaming, actionBusy, messages, () => messages.value.length, sessionId], () => {
    if (!streaming.value && !actionBusy.value) syncActive()
  })
}

function busy(): boolean {
  const { streaming, actionBusy } = useAssistant()
  return streaming.value || actionBusy.value
}

function startNew(): boolean {
  if (busy()) return false
  syncActive()
  activeId.value = newId()
  useAssistant().clear()
  save()
  return true
}

async function open(id: string): Promise<boolean> {
  if (busy() || id === activeId.value) return false
  const target = items.value.find(item => item.id === id)
  if (!target) return false
  syncActive()
  activeId.value = target.id
  save()
  await useAssistant().loadConversation(target.messages, target.sessionId)
  return true
}

async function remove(id: string): Promise<boolean> {
  if (id === activeId.value) {
    if (busy()) return false
    items.value = items.value.filter(item => item.id !== id)
    const next = items.value[0]
    if (next) {
      activeId.value = next.id
      save()
      await useAssistant().loadConversation(next.messages, next.sessionId)
    } else {
      activeId.value = newId()
      useAssistant().clear()
      save()
    }
    return true
  }
  items.value = items.value.filter(item => item.id !== id)
  save()
  return true
}

function rename(id: string, title: string): void {
  const value = title.replace(/\s+/g, ' ').trim().slice(0, 60)
  const target = items.value.find(item => item.id === id)
  if (!target || !value) return
  target.title = value
  target.customTitle = true
  save()
}

export function useAssistantConversations() {
  ensureWatching()
  const conversations = computed(() => items.value)
  return { conversations, activeId, startNew, open, remove, rename, sync: syncActive }
}
