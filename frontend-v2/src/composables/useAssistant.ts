import { ref } from 'vue'
import {
  streamAssistantChat,
  type AssistantSource,
  type ChatMessage,
} from '@/api/assistant'

export interface AssistantMessage extends ChatMessage {
  sources?: AssistantSource[]
  error?: string
  stopped?: boolean
}

const STORAGE_KEY = 'diceframe_assistant_messages'
const MAX_MESSAGES = 20
const MAX_STORED_CHARS = 24_000

const messages = ref<AssistantMessage[]>(loadStored())
const streaming = ref(false)
let controller: AbortController | null = null

function loadStored(): AssistantMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(isStoredMessage)
      .slice(-MAX_MESSAGES)
  } catch {
    return []
  }
}

function isStoredMessage(value: unknown): value is AssistantMessage {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const record = value as Record<string, unknown>
  return (record.role === 'user' || record.role === 'assistant')
    && typeof record.content === 'string'
    && record.content.length <= 12_000
}

function persist() {
  try {
    const selected: AssistantMessage[] = []
    let chars = 0
    for (const message of [...messages.value].reverse()) {
      if (selected.length >= MAX_MESSAGES) break
      const size = message.content.length + (message.error?.length || 0)
      if (selected.length && chars + size > MAX_STORED_CHARS) break
      selected.push(message)
      chars += size
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selected.reverse()))
  } catch {
    // Storage is optional; chat remains usable.
  }
}

async function send(text: string, locale = 'zh-CN') {
  const value = text.trim()
  if (!value || streaming.value) return
  // Freeze the request before Vue wraps newly-pushed objects in reactive
  // proxies. Filtering the placeholder by object identity after push is not
  // reliable and used to leave an empty assistant message at the tail.
  const requestMessages: ChatMessage[] = messages.value
    .filter(message => message.content.trim())
    .map(({ role, content }) => ({ role, content }))
  requestMessages.push({ role: 'user', content: value })
  const userMessage: AssistantMessage = { role: 'user', content: value }
  const assistantMessage: AssistantMessage = { role: 'assistant', content: '' }
  messages.value.push(userMessage, assistantMessage)
  streaming.value = true
  controller = new AbortController()
  try {
    await streamAssistantChat(
      requestMessages,
      locale,
      {
        onDelta(delta) {
          assistantMessage.content += delta
        },
        onSources(sources) {
          assistantMessage.sources = sources
        },
        onReset() {
          // 服务端截断重试：清空已显示的部分回答，等重试后的完整内容。
          assistantMessage.content = ''
        },
      },
      controller.signal,
    )
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      assistantMessage.stopped = true
    } else {
      assistantMessage.error = error instanceof Error
        ? error.message
        : (locale.startsWith('zh') ? '助手请求失败，请重试。' : 'Assistant request failed.')
    }
  } finally {
    controller = null
    streaming.value = false
    persist()
  }
}

function stop() {
  controller?.abort()
}

async function retryLast(locale = 'zh-CN') {
  if (streaming.value) return
  let userIndex = -1
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    if (messages.value[index].role === 'user') {
      userIndex = index
      break
    }
  }
  if (userIndex < 0) return
  const text = messages.value[userIndex].content
  messages.value.splice(userIndex)
  await send(text, locale)
}

function clear() {
  stop()
  messages.value = []
  try { localStorage.removeItem(STORAGE_KEY) } catch { /* Storage is optional. */ }
}

export function useAssistant() {
  return { messages, streaming, send, stop, retryLast, clear }
}
