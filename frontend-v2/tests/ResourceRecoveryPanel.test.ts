import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../src/api/client'
import { i18n } from '../src/i18n'
import ResourceRecoveryPanel from '../src/features/play/recovery/ResourceRecoveryPanel.vue'

vi.mock('../src/api/client', () => ({ api: vi.fn(), errorMessage: (error: unknown) => error instanceof Error ? error.message : String(error) }))

function snapshot(extra: Record<string, unknown> = {}) {
  return {
    ok: true, supported: true, run_id: 'run-1', revision: 7, is_gm: false,
    policy: { version: 1, policy: 'coc_light', luck_recovery: 'check' },
    actions: [{ id: 'overnight', resource_key: 'sanity', amount: '1d6', duration_minutes: 480 }, { id: 'therapy', resource_key: 'sanity', amount: '1d3', duration_minutes: 0 }],
    actors: [{ uid: 'p1', name: 'Ari', eligible: true, skills: [{ id: 'psychology', name: '心理学' }] }, { uid: 'p2', name: 'Bea', eligible: true, skills: [{ id: 'psychoanalysis', name: '精神分析' }] }],
    sources: [], receipts: [], intermissions: [{ id: 'intermission-1', round: 8 }], ...extra,
  }
}

function render(props: Record<string, unknown> = {}) {
  return mount(ResourceRecoveryPanel, { props: { gameKey: 'web|room|gm', actorId: 'p1', isGm: false, ...props }, global: { plugins: [i18n], stubs: { Teleport: true } } })
}

async function open(wrapper: ReturnType<typeof render>) {
  await flushPromises()
  await wrapper.get('[data-testid="resource-recovery-open"]').trigger('click')
  await flushPromises()
}

describe('resource recovery authority', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    vi.mocked(api).mockReset().mockResolvedValue(snapshot())
  })

  it('hides the entry for unsupported rules without submitting anything', async () => {
    vi.mocked(api).mockResolvedValue({ ok: true, supported: false })
    const wrapper = render()
    await flushPromises()
    expect(wrapper.find('[data-testid="resource-recovery-open"]').exists()).toBe(false)
    expect(api).toHaveBeenCalledWith('/games/web%7Croom%7Cgm/recovery')
    wrapper.unmount()
  })

  it('opens a dialog and explains that overnight recovery requires GM approval', async () => {
    const wrapper = render()
    await open(wrapper)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('DiceFrame 轻量房规')
    expect(wrapper.text()).toContain('申请')
    expect(vi.mocked(api).mock.calls.every(([, init]) => !init?.method)).toBe(true)
    wrapper.unmount()
  })

  it('sends a server-authorized request for the player without rolling or choosing rewards', async () => {
    const wrapper = render()
    await open(wrapper)
    await wrapper.get('[data-testid="recovery-request-overnight"]').trigger('click')
    await flushPromises()
    const [path, init] = vi.mocked(api).mock.calls.find(([, options]) => options?.method === 'POST')!
    expect(path).toBe('/games/web%7Croom%7Cgm/recovery/request')
    expect(JSON.parse(String(init?.body))).toEqual({ kind: 'overnight', actor_uid: 'p1', run_id: 'run-1', expected_revision: 7, operation_id: expect.any(String) })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    wrapper.unmount()
  })

  it('preserves the same operation id when an uncertain request is retried', async () => {
    vi.mocked(api).mockImplementation(async (_path, init) => {
      if (init?.method === 'POST') throw new Error('connection lost')
      return snapshot()
    })
    const wrapper = render()
    await open(wrapper)
    await wrapper.get('[data-testid="recovery-request-overnight"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('connection lost')
    expect(wrapper.get('[data-testid="recovery-request-overnight"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="recovery-retry"]').trigger('click')
    await flushPromises()
    const posts = vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(posts).toHaveLength(2)
    expect(posts[1]![1]?.body).toBe(posts[0]![1]?.body)
    wrapper.unmount()
  })

  it('uses the selected healer and canonical skill id for therapy', async () => {
    const wrapper = render()
    await open(wrapper)
    await wrapper.get('[data-testid="recovery-healer"]').setValue('p2')
    await wrapper.get('[data-testid="recovery-request-therapy"]').trigger('click')
    await flushPromises()
    const post = vi.mocked(api).mock.calls.find(([, options]) => options?.method === 'POST')!
    expect(JSON.parse(String(post[1]?.body))).toMatchObject({ actor_uid: 'p1', healer_uid: 'p2', skill_id: 'psychoanalysis', kind: 'therapy' })
    wrapper.unmount()
  })

  it('can request recovery on LAN HTTP clients without randomUUID', async () => {
    vi.stubGlobal('crypto', {})
    const wrapper = render()
    try {
      await open(wrapper)
      await wrapper.get('[data-testid="recovery-request-overnight"]').trigger('click')
      await flushPromises()
      const post = vi.mocked(api).mock.calls.find(([, options]) => options?.method === 'POST')!
      expect(JSON.parse(String(post[1]?.body)).operation_id).toMatch(/^recovery-/)
    } finally {
      wrapper.unmount()
      vi.unstubAllGlobals()
    }
  })

  it('shows authoritative before/after receipts including failed luck recovery', async () => {
    vi.mocked(api).mockResolvedValue(snapshot({ receipts: [{ source_id: 'luck1', operation_id: 'op1', actor_uid: 'p1', kind: 'luck', resource_key: 'luck', before: 63, after: 63, resource_delta: 0, rolls: { check: 12 } }] }))
    const wrapper = render()
    await open(wrapper)
    expect(wrapper.text()).toContain('63 → 63')
    expect(wrapper.text()).toContain('未恢复')
    expect(wrapper.text()).toContain('d100: 12')
    wrapper.unmount()
  })

  it('keeps GM approval and rewards out of the player dialog', async () => {
    vi.mocked(api).mockResolvedValue(snapshot({ sources: [{ source_id: 's1', kind: 'overnight', actor_uid: 'p1', status: 'pending' }] }))
    const wrapper = render()
    await open(wrapper)
    expect(wrapper.find('[data-testid="recovery-gm-tools"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recovery-approve-s1"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('待 GM 批准')
    wrapper.unmount()
  })

  it('reports a server-resolved therapy fumble and SAN loss without recomputing the check', async () => {
    vi.mocked(api).mockResolvedValue(snapshot({ receipts: [{ source_id: 'therapy1', operation_id: 'op1', actor_uid: 'p1', kind: 'therapy', resource_key: 'sanity', before: 63, after: 59, resource_delta: -4, success: false, fumble: true, rolls: { check: 100, threshold: 40, loss: 4 } }] }))
    const wrapper = render()
    await open(wrapper)
    expect(wrapper.text()).toContain('大失败')
    expect(wrapper.text()).toContain('63 → 59')
    expect(wrapper.text()).toContain('损失骰: 4')
    wrapper.unmount()
  })

  it('lets the GM approve an existing source without client reward amounts', async () => {
    vi.mocked(api).mockResolvedValue(snapshot({ is_gm: true, sources: [{ source_id: 's1', kind: 'overnight', actor_uid: 'p2', status: 'pending' }] }))
    const wrapper = render({ isGm: true })
    await open(wrapper)
    await wrapper.get('[data-testid="recovery-approve-s1"]').trigger('click')
    await flushPromises()
    const post = vi.mocked(api).mock.calls.find(([, options]) => options?.method === 'POST')!
    expect(post[0]).toContain('/recovery/approve')
    expect(JSON.parse(String(post[1]?.body))).toEqual({ source_id: 's1', run_id: 'run-1', expected_revision: 7, operation_id: expect.any(String) })
    wrapper.unmount()
  })

  it('disables recovery for permanent madness and explains the server reason', async () => {
    vi.mocked(api).mockResolvedValue(snapshot({ actors: [{ uid: 'p1', name: 'Ari', eligible: false, reason: '永久疯狂不能通过普通休息恢复', skills: [] }] }))
    const wrapper = render()
    await open(wrapper)
    expect(wrapper.text()).toContain('永久疯狂不能通过普通休息恢复')
    expect(wrapper.get('[data-testid="recovery-request-overnight"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('falls back to English for a community locale and explains the strict therapy policy', async () => {
    i18n.global.locale.value = 'de'
    vi.mocked(api).mockResolvedValue(snapshot({ policy: { version: 1, policy: 'coc7e_style', luck_recovery: 'off' } }))
    const wrapper = render()
    await open(wrapper)
    expect(wrapper.text()).toContain('30 days')
    expect(wrapper.text()).toContain('Psychoanalysis')
    wrapper.unmount()
  })

  it('hides all write controls during an owner preview without delegation', async () => {
    const wrapper = render({ readonly: true })
    await open(wrapper)
    expect(wrapper.find('[data-testid="recovery-request-overnight"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('claims only the current player approved source and never sends a client amount', async () => {
    vi.mocked(api).mockResolvedValue(snapshot({ sources: [
      { source_id: 'own', kind: 'luck', actor_uid: 'p1', status: 'approved' },
      { source_id: 'other', kind: 'reward', actor_uid: 'p2', status: 'approved' },
    ] }))
    const wrapper = render()
    await open(wrapper)
    expect(wrapper.find('[data-testid="recovery-claim-other"]').exists()).toBe(false)
    await wrapper.get('[data-testid="recovery-claim-own"]').trigger('click')
    await flushPromises()
    const post = vi.mocked(api).mock.calls.find(([, options]) => options?.method === 'POST')!
    expect(JSON.parse(String(post[1]?.body))).toEqual({ source_id: 'own', run_id: 'run-1', expected_revision: 7, operation_id: expect.any(String) })
    wrapper.unmount()
  })

  it('refreshes a definite stale revision and uses a new operation id for a new request', async () => {
    let posts = 0
    vi.mocked(api).mockImplementation(async (_path, init) => {
      if (init?.method === 'POST') {
        posts++
        if (posts === 1) return { ok: false, code: 'STALE_REVISION', error: '状态已变化，请重试' }
        return { ok: true }
      }
      return snapshot({ revision: posts ? 9 : 7 })
    })
    const wrapper = render()
    await open(wrapper)
    await wrapper.get('[data-testid="recovery-request-overnight"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('状态已变化，请重试')
    expect(wrapper.find('[data-testid="recovery-retry"]').exists()).toBe(false)
    await wrapper.get('[data-testid="recovery-request-overnight"]').trigger('click')
    await flushPromises()
    const bodies = vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'POST').map(([, options]) => JSON.parse(String(options?.body)))
    expect(bodies[0].expected_revision).toBe(7)
    expect(bodies[1].expected_revision).toBe(9)
    expect(bodies[0].operation_id).not.toBe(bodies[1].operation_id)
    wrapper.unmount()
  })

  it('blocks recovery while the server reports battle or processing restrictions', async () => {
    vi.mocked(api).mockResolvedValue(snapshot({ blockers: ['COMBAT_ACTIVE'], message: '战斗中不能休整' }))
    const wrapper = render()
    await open(wrapper)
    expect(wrapper.text()).toContain('战斗中不能休整')
    expect(wrapper.get('[data-testid="recovery-request-overnight"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('discards a late response for a different game', async () => {
    let resolveOld: (value: unknown) => void = () => {}
    vi.mocked(api).mockImplementation(async path => path.includes('old') ? await new Promise(resolve => { resolveOld = resolve }) : snapshot({ actors: [{ uid: 'p1', name: 'Current', eligible: true, skills: [] }] }))
    const wrapper = render({ gameKey: 'old' })
    await wrapper.setProps({ gameKey: 'new' })
    await flushPromises()
    resolveOld(snapshot({ actors: [{ uid: 'p1', name: 'Old private name', eligible: true, skills: [] }] }))
    await open(wrapper)
    expect(wrapper.text()).not.toContain('Old private name')
    expect(vi.mocked(api).mock.calls.at(-1)?.[0]).toBe('/games/new/recovery')
    wrapper.unmount()
  })

  it('closes and clears GM state when the viewer changes', async () => {
    vi.mocked(api).mockResolvedValue(snapshot({ is_gm: true }))
    const wrapper = render({ isGm: true })
    await open(wrapper)
    expect(wrapper.find('[data-testid="recovery-gm-tools"]').exists()).toBe(true)
    vi.mocked(api).mockResolvedValue(snapshot())
    await wrapper.setProps({ actorId: 'p2', isGm: false })
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await open(wrapper)
    expect(wrapper.find('[data-testid="recovery-gm-tools"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
