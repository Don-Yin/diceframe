import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/assistant', () => ({
  confirmAssistantAgent: vi.fn(),
  getAssistantAgentSession: vi.fn().mockResolvedValue({ status: 'idle', drafts: {}, receipts: [] }),
  reviewAssistantAgent: vi.fn(),
  streamAssistantAgent: vi.fn(),
}))

describe('DF Agent conversations', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  async function load() {
    const assistant = await import('../src/composables/useAssistant')
    const conversations = await import('../src/composables/useAssistantConversations')
    return { assistant: assistant.useAssistant(), history: conversations.useAssistantConversations() }
  }

  it('archives the current conversation, starts a new one and switches back', async () => {
    const { assistant, history } = await load()
    assistant.messages.value.push({ role: 'user', content: '帮我写一个港口小镇的世界书' }, { role: 'assistant', content: '好的' })
    await nextTick()
    expect(history.conversations.value).toHaveLength(1)
    expect(history.conversations.value[0].title).toBe('帮我写一个港口小镇的世界书')
    const firstId = history.activeId.value

    expect(history.startNew()).toBe(true)
    expect(assistant.messages.value).toEqual([])
    assistant.messages.value.push({ role: 'user', content: '开一局克苏鲁' })
    await nextTick()
    expect(history.conversations.value.map(item => item.title)).toEqual(['开一局克苏鲁', '帮我写一个港口小镇的世界书'])

    await history.open(firstId)
    expect(assistant.messages.value.map(message => message.content)).toEqual(['帮我写一个港口小镇的世界书', '好的'])
    const stored = JSON.parse(localStorage.getItem('diceframe_assistant_conversations') || '{}')
    expect(stored.activeId).toBe(firstId)
    expect(stored.items).toHaveLength(2)
  })

  it('renames and deletes conversations, falling back to the next one', async () => {
    const { assistant, history } = await load()
    assistant.messages.value.push({ role: 'user', content: '第一段' })
    await nextTick()
    history.startNew()
    assistant.messages.value.push({ role: 'user', content: '第二段' })
    await nextTick()
    const secondId = history.activeId.value

    history.rename(secondId, '  战役笔记  ')
    expect(history.conversations.value.find(item => item.id === secondId)?.title).toBe('战役笔记')

    await history.remove(secondId)
    expect(history.conversations.value.map(item => item.title)).toEqual(['第一段'])
    expect(assistant.messages.value.map(message => message.content)).toEqual(['第一段'])
  })

  it('refuses to switch while a reply is streaming', async () => {
    const { assistant, history } = await load()
    assistant.messages.value.push({ role: 'user', content: '旧对话' })
    await nextTick()
    const oldId = history.activeId.value
    history.startNew()
    assistant.streaming.value = true
    expect(history.startNew()).toBe(false)
    expect(await history.open(oldId)).toBe(false)
    assistant.streaming.value = false
  })
})
