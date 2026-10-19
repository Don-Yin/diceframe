import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import AISeatsPanel from '../src/features/play/ai-seats/AISeatsPanel.vue'

const apiMock = vi.hoisted(() => ({ call: vi.fn() }))
vi.mock('../src/api/client', () => ({ api: apiMock.call }))

const data = {
  ok: true, revision: 3, defaults: { provider_ref: null, model: null, style: 'character' },
  providers: [{ id: 'local', name: 'Local', models: ['small'] }, { id: 'other', name: 'Other', models: ['large'] }],
  styles: ['character', 'concise', 'cautious', 'bold', 'supportive'],
  seats: { a: { ready: true, reason: '', provider_ref: 'local', provider_name: 'Local', model: 'small', style: 'character',
    settings: {}, inherits: true, generating: false, retry_reason: 'waiting_humans',
    last_outcome: { status: 'skipped', reason: 'call_failed:TimeoutError', round: 2 } } },
}
function render(isGm = true, preview = false, round?: number) {
  return mount(AISeatsPanel, { global: { plugins: [i18n], stubs: { Teleport: true } }, props: {
    gameKey: 'web|room|bot', runId: 'run', isGm, preview,
    ...(round === undefined ? {} : { round }),
    players: [{ user_id: 'a', character_name: 'A', control: { mode: 'ai', revision: 1 } }],
  } })
}
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers() })

describe('AI seat configuration and recovery', () => {
  it('shows model, inherited style, failure cause, combat policy and retry gate', async () => {
    i18n.global.locale.value = 'zh-CN'; apiMock.call.mockResolvedValue(structuredClone(data))
    const wrapper = render(); await flushPromises()
    expect(wrapper.text()).toContain('small')
    expect(wrapper.text()).toContain('继承本局默认')
    expect(wrapper.text()).toContain('模型调用失败')
    expect(wrapper.text()).toContain('等待真人行动')
    expect(wrapper.text()).toContain('战斗模型仅选择规则提供的合法动作')
    expect(wrapper.get('[data-testid="retry-a"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('saves seat overrides as references and rejects stale UI edits using captured revision', async () => {
    apiMock.call.mockResolvedValue(structuredClone(data))
    const wrapper = render(); await flushPromises()
    await wrapper.get('[data-testid="configure-a"]').trigger('click')
    await wrapper.get('[data-testid="provider"]').setValue('other')
    await wrapper.get('[data-testid="model"]').setValue('large')
    await wrapper.get('[data-testid="style"]').setValue('cautious')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const mutation = apiMock.call.mock.calls.find(call => call[1]?.method === 'PUT')
    expect(mutation?.[0]).toBe('/games/web%7Croom%7Cbot/ai-seats/seats/a')
    expect(JSON.parse(mutation?.[1]?.body)).toEqual({ expected_revision: 3,
      settings: { provider_ref: 'other', model: 'large', style: 'cautious' } })
    wrapper.unmount()
  })

  it.each([[false, false], [true, true]])('does not fetch or display GM configuration in player/preview mode', async (gm, preview) => {
    const wrapper = render(gm, preview); await flushPromises()
    expect(apiMock.call).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="ai-seats"]').exists()).toBe(false)
    expect(wrapper.emitted('attention')?.at(-1)).toEqual([0])
    wrapper.unmount()
  })

  it('discards a late response after switching games', async () => {
    let finish!: (value: typeof data) => void
    apiMock.call.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    apiMock.call.mockResolvedValue({ ...data, seats: { a: { ...data.seats.a, model: 'NEW-GAME' } } })
    const wrapper = render(); await flushPromises()
    await wrapper.setProps({ gameKey: 'new-game', runId: 'new-run' }); await flushPromises()
    finish(structuredClone(data)); await flushPromises()
    expect(wrapper.text()).toContain('NEW-GAME')
    expect(wrapper.text()).not.toContain('small')
    wrapper.unmount()
  })

  it('keeps the edit revision captured before a concurrent update', async () => {
    vi.useFakeTimers()
    apiMock.call.mockResolvedValue(structuredClone(data))
    const wrapper = render(); await flushPromises()
    await wrapper.get('[data-testid="configure-a"]').trigger('click')
    await wrapper.get('[data-testid="style"]').setValue('bold')
    apiMock.call.mockResolvedValue({ ...data, revision: 4 })
    await vi.advanceTimersByTimeAsync(4000); await flushPromises()
    apiMock.call.mockRejectedValueOnce(new Error('stale revision'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const mutation = apiMock.call.mock.calls.find(call => call[1]?.method === 'PUT')
    expect(JSON.parse(mutation?.[1]?.body).expected_revision).toBe(3)
    expect(wrapper.get('form').text()).toContain('读取或保存失败')
    expect(wrapper.get('[data-testid="style"]').element).toHaveProperty('value', 'bold')
    wrapper.unmount()
  })

  it('keeps malformed or unavailable settings responses from crashing the play screen', async () => {
    apiMock.call.mockResolvedValue({})
    const wrapper = render(); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('读取或保存失败')
    expect(wrapper.find('[data-testid="configure-a"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('refreshes the game when a background combat result arrives', async () => {
    vi.useFakeTimers(); apiMock.call.mockResolvedValue(structuredClone(data))
    const wrapper = render(); await flushPromises()
    expect(wrapper.emitted('changed')).toBeUndefined()
    const next = structuredClone(data)
    next.seats.a.last_outcome = { status: 'added', reason: '', round: 3 }
    apiMock.call.mockResolvedValue(next)
    await vi.advanceTimersByTimeAsync(4000); await flushPromises()
    expect(wrapper.emitted('changed')).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(4000); await flushPromises()
    expect(wrapper.emitted('changed')).toHaveLength(1)
    wrapper.unmount()
  })

  it('reports only visible current AI-seat fallback or skipped attention', async () => {
    apiMock.call.mockResolvedValue(structuredClone(data))
    const wrapper = render(true, false, 2)
    await flushPromises()
    expect(wrapper.emitted('attention')?.at(-1)).toEqual([1])

    await wrapper.setProps({ round: 3 })
    expect(wrapper.emitted('attention')?.at(-1)).toEqual([0])
    wrapper.unmount()

    const human = mount(AISeatsPanel, { global: { plugins: [i18n], stubs: { Teleport: true } }, props: {
      gameKey: 'web|room|bot', runId: 'run', isGm: true, players: [{ user_id: 'a', character_name: 'A', control: { mode: 'human', revision: 1 } }],
    } })
    await flushPromises()
    expect(human.emitted('attention')?.at(-1)).toEqual([0])
    human.unmount()
  })

  it('clears attention when switching games or unmounting', async () => {
    const attention = vi.fn()
    apiMock.call.mockResolvedValue(structuredClone(data))
    const wrapper = mount(AISeatsPanel, { global: { plugins: [i18n], stubs: { Teleport: true } }, attrs: { onAttention: attention }, props: {
      gameKey: 'web|room|bot', runId: 'run', isGm: true,
      players: [{ user_id: 'a', character_name: 'A', control: { mode: 'ai', revision: 1 } }],
    } })
    await flushPromises()
    await wrapper.setProps({ gameKey: 'new-game', runId: 'new-run' })
    expect(wrapper.emitted('attention')?.at(-1)).toEqual([0])
    const countBeforeUnmount = attention.mock.calls.length
    wrapper.unmount()
    expect(attention.mock.calls).toHaveLength(countBeforeUnmount + 1)
    expect(attention.mock.calls.at(-1)).toEqual([0])
  })
})
