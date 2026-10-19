import { mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import AgentAuthorizationPanel from '../src/components/assistant/AgentAuthorizationPanel.vue'
import { NSelect } from 'naive-ui'

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

  it('uses live domains, appends paged results without duplicates, and resets offset on search', async () => {
    capabilities
      .mockResolvedValueOnce({ ok: true, revision: 'r1', domains: [{ domain: 'new-module', count: 3 }], offset: 0, has_more: true, capabilities: [{ name: 'one', label: 'One', domain: 'new-module', version: 1, effect: 'read', automatic: true, description: 'one' }] })
      .mockResolvedValueOnce({ ok: true, revision: 'r1', offset: 1, has_more: false, capabilities: [
        { name: 'one', label: 'One', domain: 'new-module', version: 1, effect: 'read', automatic: true, description: 'one' },
        { name: 'two', label: 'Two', domain: 'new-module', version: 1, effect: 'read', automatic: true, description: 'two' },
      ] })
      .mockResolvedValue({ ok: true, revision: 'r1', offset: 1, has_more: false, capabilities: [] })
    const wrapper = mount(AgentAuthorizationPanel, { props: { locale: 'en' } })
    await wrapper.get('[data-testid="agent-authorization"] > button').trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.find('.agent-capability-list').text()).toContain('One')
    const domainSelect = wrapper.findAllComponents(NSelect).at(1)
    expect(domainSelect?.props('options')).toEqual(expect.arrayContaining([expect.objectContaining({ value: 'new-module' })]))
    await wrapper.findAll('button').find(button => button.text() === 'Load more')!.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(capabilities.mock.calls[1]?.[0]).toMatchObject({ offset: 1 })
    expect(wrapper.findAll('.agent-capability-list li').filter(item => item.text().includes('One'))).toHaveLength(1)
    expect(wrapper.text()).toContain('Two')
    await wrapper.find('.agent-capability-filters input').setValue('new')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(capabilities.mock.calls.at(-1)?.[0]).toMatchObject({ q: 'new', offset: 0 })
  })

  it('does not let a slow older query overwrite the newer result', async () => {
    let resolveOld!: (value: unknown) => void
    const old = new Promise(resolve => { resolveOld = resolve })
    capabilities.mockReturnValueOnce(old)
      .mockResolvedValueOnce({ ok: true, revision: 'r1', offset: 0, has_more: false, capabilities: [{ name: 'new', label: 'New result', domain: 'new-module', version: 1, effect: 'read', automatic: true, description: 'new' }] })
    const wrapper = mount(AgentAuthorizationPanel, { props: { locale: 'en' } })
    await wrapper.get('[data-testid="agent-authorization"] > button').trigger('click')
    await wrapper.find('.agent-capability-filters input').setValue('new')
    await new Promise(resolve => setTimeout(resolve, 0))
    resolveOld({ ok: true, revision: 'r1', offset: 0, has_more: false, capabilities: [{ name: 'old', label: 'Old result', domain: 'old', version: 1, effect: 'read', automatic: true, description: 'old' }] })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.find('.agent-capability-list').text()).toContain('New result')
    expect(wrapper.find('.agent-capability-list').text()).not.toContain('Old result')
  })

  it('restarts pagination when the registry revision changes between pages', async () => {
    const entry = (name: string) => ({ name, label: name, domain: 'lorebook', version: 1, effect: 'read', automatic: false, description: name })
    capabilities
      .mockResolvedValueOnce({ ok: true, revision: 'r1', offset: 0, has_more: true, capabilities: [entry('Old page')] })
      .mockResolvedValueOnce({ ok: true, revision: 'r2', offset: 1, has_more: false, capabilities: [entry('Discarded page')] })
      .mockResolvedValueOnce({ ok: true, revision: 'r2', offset: 0, has_more: false, capabilities: [entry('Current page')] })
    const wrapper = mount(AgentAuthorizationPanel, { props: { locale: 'en' } })
    await wrapper.get('[data-testid="agent-authorization"] > button').trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    await wrapper.findAll('button').find(button => button.text() === 'Load more')!.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(capabilities.mock.calls.map(call => call[0].offset)).toEqual([0, 1, 0])
    expect(wrapper.find('.agent-capability-list').text()).toContain('Current page')
    expect(wrapper.find('.agent-capability-list').text()).not.toContain('Old page')
    expect(wrapper.find('.agent-capability-list').text()).not.toContain('Discarded page')
  })

  it('shows the server discovery hint for an empty live result', async () => {
    capabilities.mockResolvedValueOnce({ ok: true, revision: 'r1', capabilities: [], discovery_hint: 'Ask the server to refresh its capability index.' })
    const wrapper = mount(AgentAuthorizationPanel, { props: { locale: 'en' } })
    await wrapper.get('[data-testid="agent-authorization"] > button').trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Ask the server to refresh its capability index.')
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
