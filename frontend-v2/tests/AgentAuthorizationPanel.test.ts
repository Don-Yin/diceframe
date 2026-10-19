import { mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import AgentAuthorizationPanel from '../src/components/assistant/AgentAuthorizationPanel.vue'

const { capabilities } = vi.hoisted(() => ({ capabilities: vi.fn() }))
vi.mock('../src/api/assistant', async () => {
  const actual = await vi.importActual<typeof import('../src/api/assistant')>('../src/api/assistant')
  return { ...actual, getAssistantAgentCapabilities: capabilities }
})

describe('AgentAuthorizationPanel', () => {
  beforeEach(() => { capabilities.mockReset(); capabilities.mockResolvedValue({ ok: true, revision: 'r1', capabilities: [] }) })

  it('offers all modes, finite budget, current scope, and revoke', async () => {
    const authorize = vi.fn()
    const wrapper = mount(AgentAuthorizationPanel, { props: { locale: 'zh-CN', context: { game_key: 'g-1' }, authorization: { mode: 'task', scope: { game_key: 'g-1' }, domains: [], expires_at: 1, max_steps: 32, remaining_steps: 10 }, onAuthorize: authorize } })
    await wrapper.get('[data-testid="agent-authorization"] > button').trigger('click')
    expect(wrapper.text()).toContain('建议')
    expect(wrapper.text()).toContain('自动处理日常')
    expect(wrapper.text()).toContain('接管本次任务')
    await wrapper.findAll('button').find(button => button.text() === '建议')!.trigger('click')
    expect(authorize).toHaveBeenCalledWith('suggest', { game_key: 'g-1' }, undefined, 32)
  })

  it('shows a readable capability error from an old server', async () => {
    capabilities.mockRejectedValueOnce(Object.assign(new Error('HTTP_404'), { code: 'HTTP_404' }))
    const wrapper = mount(AgentAuthorizationPanel, { props: { locale: 'en' } })
    await wrapper.get('[data-testid="agent-authorization"] > button').trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('HTTP_404')
  })

  it('shows optional numeric token usage only when supplied', async () => {
    const wrapper = mount(AgentAuthorizationPanel, { props: { locale: 'en', task: { status: 'running', completed_steps: 1, used_tokens: 120, token_budget: 1000 } } })
    await wrapper.get('[data-testid="agent-authorization"] > button').trigger('click')
    expect(wrapper.text()).toContain('120/1000 tokens')
  })

  it('shows one pending approval badge and lets a budget-limited task continue explicitly', async () => {
    const onContinue = vi.fn()
    const wrapper = mount(AgentAuthorizationPanel, {
      props: {
        locale: 'en', pendingApproval: true, onContinue,
        task: { status: 'budget_reached', completed_steps: 24, used_tokens: 1000, token_budget: 1000 },
      },
    })
    const toggle = wrapper.get('[data-testid="agent-authorization"] > button')
    expect(toggle.find('.agent-authorization-badge').text()).toBe('1')
    expect(toggle.attributes('title')).toContain('Review pending action')
    await toggle.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === 'Continue task')!.trigger('click')
    expect(onContinue).toHaveBeenCalledOnce()
  })
})
