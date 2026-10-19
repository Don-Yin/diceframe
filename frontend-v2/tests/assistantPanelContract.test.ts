import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AssistantPanel from '../src/components/AssistantPanel.vue'
import type { AgentApproval } from '../src/api/assistant'
import type { AssistantMessage } from '../src/composables/useAssistant'

const send = vi.fn().mockResolvedValue(undefined)
const messages = ref<AssistantMessage[]>([])
const pendingApproval = ref<AgentApproval | null>(null)
const confirmApproval = vi.fn()
const navigation = ref<{ route: string; query?: Record<string, string> } | null>(null)
const streaming = ref(false)

vi.mock('@/composables/useLocale', () => ({
  useLocale: () => ({
    locale: ref('zh-CN'),
    t: (key: string) => {
      if (/(expand|enlarge|maximize|expanded)/i.test(key)) return '扩大窗口'
      if (/(collapse|shrink|sidebar|compact|collapsed)/i.test(key)) return '缩回侧栏'
      return `translated:${key}`
    },
  }),
}))

vi.mock('@/composables/useAssistantConversations', () => ({
  useAssistantConversations: () => ({
    conversations: ref([]), activeId: ref('active'), startNew: vi.fn(() => true), open: vi.fn(), remove: vi.fn(), rename: vi.fn(), sync: vi.fn(),
  }),
}))
vi.mock('@/composables/useAssistant', () => ({
  useAssistant: () => ({
    messages,
    streaming,
    status: ref(''),
    pendingApproval,
    drafts: ref({}),
    navigation,
    actionBusy: ref(false),
    actionError: ref(''),
    send,
    stop: vi.fn(),
    retryLast: vi.fn(),
    clear: vi.fn(),
    restoreSession: vi.fn(),
    confirmApproval,
    cancelApproval: vi.fn(),
    reviewDraft: vi.fn(),
    saveDraft: vi.fn(),
    invalidateApproval: vi.fn(),
  }),
}))

describe('DF Assistant runtime log entry', () => {
  afterEach(() => vi.unstubAllGlobals())
  beforeEach(() => {
    send.mockClear()
    messages.value = []
    pendingApproval.value = null
    navigation.value = null
    streaming.value = false
    localStorage.clear()
    confirmApproval.mockClear()
  })

  it('offers a named page for confirmed results and drops it once there, without a "continue previous task" shortcut', async () => {
    window.location.hash = '#/overview'
    messages.value = [{ role: 'user', content: '创作内容' }, { role: 'assistant', content: '已为你打开创作页面' }]
    navigation.value = { route: 'create' }
    const wrapper = mount(AssistantPanel)
    const button = wrapper.get('[data-testid="assistant-navigation"]')
    expect(button.text()).toBe('前往：创作')
    expect(wrapper.find('.assistant-continue').exists()).toBe(false)

    await button.trigger('click')
    expect(window.location.hash).toBe('#/create')
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="assistant-navigation"]').exists()).toBe(false)
    expect(send).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('follows agent navigation while answering and leaves the result and a way back in the reply', async () => {
    window.location.hash = '#/settings'
    streaming.value = true
    messages.value = [
      { role: 'user', content: '帮我导航到内容库' },
      { role: 'assistant', content: '已经帮你导航到内容库页面了', events: [{ event: 'tool_result', payload: { tool: 'navigate', ok: true, result: { ok: true, navigation: { route: 'library' } } } }] },
    ]
    const wrapper = mount(AssistantPanel)
    navigation.value = { route: 'library' }
    await wrapper.vm.$nextTick()
    expect(window.location.hash).toBe('#/library')
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    streaming.value = false
    await wrapper.vm.$nextTick()

    const action = wrapper.get('[data-testid="assistant-actions"]')
    expect(action.text()).toContain('已打开：内容库')
    expect(action.text()).not.toContain('{"ok"')
    expect(wrapper.find('[data-testid="assistant-navigation"]').exists()).toBe(false)
    expect(wrapper.find('.assistant-tasks').exists()).toBe(false)

    await wrapper.get('[data-testid="assistant-navigation-back"]').trigger('click')
    expect(window.location.hash).toBe('#/settings')
    wrapper.unmount()
  })

  it('only shows a button when automatic page changes are turned off', async () => {
    localStorage.setItem('diceframe_assistant_auto_navigate', '0')
    const { useAssistantPreferences } = await import('../src/composables/useAssistantPreferences')
    useAssistantPreferences().setAutoNavigate(false)
    window.location.hash = '#/settings'
    streaming.value = true
    messages.value = [{ role: 'user', content: '打开内容库' }, { role: 'assistant', content: '好的' }]
    const wrapper = mount(AssistantPanel)
    navigation.value = { route: 'library' }
    await wrapper.vm.$nextTick()
    expect(window.location.hash).toBe('#/settings')
    streaming.value = false
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-testid="assistant-navigation"]').text()).toBe('前往：内容库')
    useAssistantPreferences().setAutoNavigate(true)
    wrapper.unmount()
  })

  it('submits the runtime-log diagnostic action through the normal assistant request flow', async () => {
    const wrapper = mount(AssistantPanel)

    await wrapper.get('[data-assistant-intent="runtime-logs"]').trigger('click')

    expect(send).toHaveBeenCalledOnce()
    expect(send).toHaveBeenCalledWith(expect.any(String), 'zh-CN')
  })

  it('keeps the active confirmation after the latest conversation and explains the waiting state', () => {
    messages.value = [
      { role: 'user', content: '给克苏鲁恐怖·阿卡姆疑云资料册随便加一条' },
      { role: 'assistant', content: '' },
    ]
    pendingApproval.value = {
      approval_id: 'a'.repeat(32), plan_digest: `sha256:${'b'.repeat(64)}`,
      tool: 'write_lorebook_entries', label: 'Write entries', arguments: {}, expires_at: 4102444800,
      preview: { target_name: '克苏鲁恐怖·阿卡姆疑云' },
    }
    const wrapper = mount(AssistantPanel)
    const lastMessage = wrapper.findAll('.assistant-message').at(-1)!.element
    const approval = wrapper.get('[data-agent-approval]').element
    expect(lastMessage.compareDocumentPosition(approval) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(wrapper.get('.assistant-message-assistant').text()).toContain('等待确认')
    expect(wrapper.get('.assistant-composer-hint').text()).toContain('等待确认')
  })

  it('exposes the expanded-window control with Chinese title and aria label', async () => {
    const wrapper = mount(AssistantPanel, { props: { expanded: false } })
    const toggle = wrapper.get('[data-testid="assistant-toggle-expanded"]')

    expect(toggle.attributes('title')).toBe('最大化窗口')
    expect(toggle.attributes('aria-label')).toBe('最大化窗口')
    await toggle.trigger('click')
    expect(wrapper.emitted('toggleExpanded')).toHaveLength(1)

    await wrapper.setProps({ expanded: true })
    expect(wrapper.get('[data-testid="assistant-toggle-expanded"]').attributes('title')).toBe('还原窗口')
    expect(wrapper.get('[data-testid="assistant-toggle-expanded"]').attributes('aria-label')).toBe('还原窗口')
  })

  it('defaults to a folded phone workspace while keeping pending approval discoverable', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
    pendingApproval.value = { approval_id: 'a'.repeat(32), plan_digest: `sha256:${'b'.repeat(64)}`, tool: 'save_content', label: 'Save', arguments: {}, expires_at: 4102444800 }
    const wrapper = mount(AssistantPanel, { attachTo: document.body })
    const toggle = wrapper.get('[data-testid="assistant-workspace-toggle"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.text()).toContain('等待确认')
    expect(wrapper.get('[data-agent-approval]').isVisible()).toBe(false)
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-agent-approval]').isVisible()).toBe(true)
    await toggle.trigger('click')
    expect(wrapper.get('[data-agent-approval]').isVisible()).toBe(false)
    expect(confirmApproval).not.toHaveBeenCalled()
    expect(pendingApproval.value?.approval_id).toBe('a'.repeat(32))
    wrapper.unmount()
  })
})
