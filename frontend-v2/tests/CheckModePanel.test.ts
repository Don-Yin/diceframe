import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import CheckModePanel from '../src/features/play/check-modes/CheckModePanel.vue'

const mocked = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/client', () => ({ api: mocked.api }))
const seat = { uid: 'a', name: 'Alice', kind: 'd20_keep_high_low', context_id: 'round:2',
  scope: 'narrative_round', blocked_reason: '', request: null, grant: null, previews: [] }
const data = { ok: true, revision: 4, run_id: 'run', is_gm: false, seats: [seat] }
const bob = { ...seat, uid: 'b', name: 'Bob' }
const render = (isGm = false, preview = false, delegate = false) => mount(CheckModePanel, { global: { plugins: [i18n], stubs: { Teleport: true } },
  props: { gameKey: 'web|room|bot', runId: 'run', actorId: 'a', isGm, preview, delegate } })
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers() })

describe('check mode requests and GM grants', () => {
  it('player sends a request with captured run, context and revision, never a grant', async () => {
    i18n.global.locale.value = 'zh-CN'; mocked.api.mockResolvedValue(structuredClone(data))
    const wrapper = render(); await flushPromises()
    await wrapper.get('[data-testid="check-mode-trigger"]').trigger('click')
    expect(wrapper.text()).toContain('本轮行动检定')
    await wrapper.get('[data-testid="request-a"]').trigger('click')
    await wrapper.get('[data-testid="mode-reason"]').setValue('高地')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const call = mocked.api.mock.calls.find(call => call[1]?.method === 'POST')
    expect(call?.[0]).toBe('/games/web%7Croom%7Cbot/check-modes/seats/a/request')
    expect(JSON.parse(call?.[1]?.body)).toEqual({ expected_revision: 4, run_id: 'run', context_id: 'round:2', mode: 'advantage', reason: '高地' })
    expect(wrapper.find('[data-testid="grant-a"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('GM reviews requests and automatic sources before granting', async () => {
    mocked.api.mockResolvedValue({ ...data, is_gm: true, seats: [{ ...seat,
      request: { mode: 'advantage', reason: '玩家申请理由', status: 'pending' },
      previews: [{ label: 'Bow → Goblin', mode: 'disadvantage', sources: [{ code: 'long_range', mode: 'disadvantage' }] }],
    }] })
    const wrapper = render(true); await flushPromises()
    await wrapper.get('[data-testid="check-mode-trigger"]').trigger('click')
    expect(wrapper.text()).toContain('玩家申请理由')
    expect(wrapper.text()).toContain('远距离')
    await wrapper.get('[data-testid="grant-a"]').trigger('click')
    await wrapper.get('[data-testid="mode-reason"]').setValue('GM 确认')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(mocked.api.mock.calls.some(call => call[0].endsWith('/grant') && call[1]?.method === 'POST')).toBe(true)
    wrapper.unmount()
  })

  it('preview and prepared checks are read only', async () => {
    mocked.api.mockResolvedValue({ ...data, seats: [{ ...seat, blocked_reason: 'checks_prepared' }] })
    const wrapper = render(false, true); await flushPromises()
    await wrapper.get('[data-testid="check-mode-trigger"]').trigger('click')
    expect(wrapper.get('[data-testid="request-a"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('keeps a delegated draft when preview mode becomes active', async () => {
    mocked.api.mockResolvedValue(structuredClone(data))
    const wrapper = render(false, false, true); await flushPromises()
    await wrapper.get('[data-testid="check-mode-trigger"]').trigger('click')
    await wrapper.get('[data-testid="request-a"]').trigger('click')
    await wrapper.get('[data-testid="mode-reason"]').setValue('保留这份申请')
    await wrapper.setProps({ preview: true }); await flushPromises()
    expect(wrapper.get('[data-testid="mode-reason"]').element).toHaveProperty('value', '保留这份申请')
    expect(mocked.api.mock.calls.some(call => call[1]?.method === 'POST')).toBe(false)
    wrapper.unmount()
  })

  it('closes a draft when delegated preview loses write authority', async () => {
    mocked.api.mockResolvedValue(structuredClone(data))
    const wrapper = render(false, true, true); await flushPromises()
    await wrapper.get('[data-testid="check-mode-trigger"]').trigger('click')
    await wrapper.get('[data-testid="request-a"]').trigger('click')
    await wrapper.get('[data-testid="mode-reason"]').setValue('撤销代操作')
    await wrapper.setProps({ delegate: false }); await flushPromises()
    expect(wrapper.find('[data-testid="mode-reason"]').exists()).toBe(false)
    expect(mocked.api.mock.calls.some(call => call[1]?.method === 'POST')).toBe(false)
    wrapper.unmount()
  })

  it('discards late responses after changing games and keeps failed drafts', async () => {
    let finish!: (v: typeof data) => void
    mocked.api.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    mocked.api.mockResolvedValue({ ...data, seats: [{ ...seat, name: 'New seat' }] })
    const wrapper = render(); await flushPromises()
    await wrapper.setProps({ gameKey: 'next', runId: 'next' }); await flushPromises()
    finish(data); await flushPromises()
    await wrapper.get('[data-testid="check-mode-trigger"]').trigger('click')
    expect(wrapper.text()).toContain('New seat')
    expect(wrapper.text()).not.toContain('Alice')
    await wrapper.get('[data-testid="request-a"]').trigger('click')
    await wrapper.get('[data-testid="mode-reason"]').setValue('keep draft')
    mocked.api.mockRejectedValueOnce(new Error('stale'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[data-testid="mode-reason"]').element.value).toBe('keep draft')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps the idle surface compact and does not create another poll on open and close', async () => {
    vi.useFakeTimers(); const interval = vi.spyOn(globalThis, 'setInterval')
    mocked.api.mockResolvedValue(structuredClone(data))
    const wrapper = render(); await flushPromises()
    expect(wrapper.find('[data-testid="check-mode-trigger"]').exists()).toBe(true)
    expect(wrapper.find('article').exists()).toBe(false)
    const calls = interval.mock.calls.length
    await wrapper.get('[data-testid="check-mode-trigger"]').trigger('click')
    await wrapper.get('[data-testid="check-mode-close"]').trigger('click')
    expect(interval.mock.calls.length).toBe(calls)
    wrapper.unmount()
  })

  it('isolates player data and exposes own pending state while GM gets a pending badge', async () => {
    mocked.api.mockResolvedValue({ ...data, seats: [{ ...seat, request: { mode: 'advantage', reason: 'wait', status: 'pending' } }, bob] })
    const player = render(); await flushPromises(); await player.get('[data-testid="check-mode-trigger"]').trigger('click')
    expect(player.text()).toContain('等待 GM'); expect(player.text()).not.toContain('Bob')
    player.unmount()
    mocked.api.mockResolvedValue({ ...data, is_gm: true, seats: [{ ...seat, request: { mode: 'advantage', reason: 'wait', status: 'pending' } }, bob] })
    const gm = render(true); await flushPromises()
    expect(gm.get('[data-testid="check-mode-pending-badge"]').text()).toContain('1')
    gm.unmount()
  })

  it('hides the tool when every available seat is unsupported', async () => {
    mocked.api.mockResolvedValue({ ...data, seats: [{ ...seat, blocked_reason: 'unsupported' }] })
    const wrapper = render(); await flushPromises()
    expect(wrapper.find('[data-testid="check-mode-trigger"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('hides the player tool when that player seat is unsupported even if another seat is supported', async () => {
    mocked.api.mockResolvedValue({ ...data, seats: [{ ...seat, blocked_reason: 'unsupported' }, { ...bob }] })
    const wrapper = render()
    await flushPromises()
    expect(wrapper.find('[data-testid="check-mode-trigger"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('uses the localized tool label', async () => {
    i18n.global.locale.value = 'en'
    mocked.api.mockResolvedValue(structuredClone(data))
    const wrapper = render()
    await flushPromises()
    expect(wrapper.get('[data-testid="check-mode-trigger"]').text()).toContain('Checks')
    wrapper.unmount()
  })

  it('emits status and exposes open without another fetch', async () => {
    mocked.api.mockResolvedValue({ ...data, is_gm: true, seats: [{ ...seat, request: { mode: 'advantage', reason: 'wait', status: 'pending' } }] })
    const statuses: unknown[] = []
    const wrapper = mount(CheckModePanel, { global: { plugins: [i18n], stubs: { Teleport: true } }, props: {
      gameKey: 'web|room|bot', runId: 'run', actorId: 'a', isGm: true, preview: false, delegate: false,
      onStatus: (value: unknown) => statuses.push(value),
    } })
    await flushPromises(); const before = mocked.api.mock.calls.length
    ;(wrapper.vm as unknown as { open: () => void }).open(); await wrapper.vm.$nextTick()
    expect(mocked.api.mock.calls.length).toBe(before)
    expect(wrapper.find('[data-testid="check-mode-close"]').exists()).toBe(true)
    expect(statuses.some(value => (value as { pendingCount?: number }).pendingCount === 1)).toBe(true)
    wrapper.unmount()
  })
})
