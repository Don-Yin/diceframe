import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import { api } from '../src/api/client'
import type { GameDetail, Player } from '../src/api/types'
import PartyActions from '../src/features/play/party/PartyActions.vue'

vi.mock('../src/api/client', () => ({ api: vi.fn(), apiBlob: vi.fn() }))
const player = { user_id: 'p1', character_name: 'Ari' } as Player
const detail = (runtime = 'core:dnd2024') => ({ run_id: 'run-1', ruleset_runtime: { id: runtime, capabilities: { character_lifecycle: 'rules_aware' } } }) as GameDetail
const props = { gameKey: 'web|room|bot', actorId: 'p1', isGm: false, player, players: [player] }

describe('direct party operations', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    vi.mocked(api).mockReset().mockResolvedValue({ ok: true, run_id: 'run-1', requests: [] })
  })

  it('keeps listening when no actions are available and hides empty controls', async () => {
    const wrapper = mount(PartyActions, { props: { ...props, detail: detail('unregistered:rules') }, global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()
    expect(wrapper.isVisible()).toBe(false)
    expect(wrapper.find('[data-testid="party-rest"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="manual-roll-history"]').exists()).toBe(false)
    expect(api).toHaveBeenCalledWith('/games/web%7Croom%7Cbot/roll-requests')
    wrapper.unmount()
  })

  it('opens the registered rest center without submitting a rest', async () => {
    const wrapper = mount(PartyActions, { props: { ...props, detail: detail() }, global: { plugins: [i18n] } })
    await flushPromises()
    await wrapper.get('[data-testid="party-rest"]').trigger('click')
    expect(wrapper.emitted('rest')).toHaveLength(1)
    expect(vi.mocked(api).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
    wrapper.unmount()
  })

  it('shows readiness and changes from participation to viewing after the player is ready', async () => {
    const session = { active: true, status: 'collecting', rest: 'short', ready_count: 1, active_count: 2, participants: [{ user_id: 'p1', character_name: 'Ari', status: 'waiting' }] }
    const wrapper = mount(PartyActions, { props: { ...props, detail: { ...detail(), rest_session: session } as GameDetail }, global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.text()).toContain('1/2')
    expect(wrapper.get('[data-testid="party-rest"]').text()).toBe('参与休息')
    await wrapper.setProps({ detail: { ...detail(), rest_session: { ...session, participants: [{ ...session.participants[0], status: 'submitted' }] } } as GameDetail })
    expect(wrapper.get('[data-testid="party-rest"]').text()).toBe('查看队伍休息')
    wrapper.unmount()
  })

  it('hides rest for another actor or an owner preview without delegation', async () => {
    for (const extra of [{ actorId: 'another-player' }, { preview: true }]) {
      const wrapper = mount(PartyActions, { props: { ...props, detail: detail(), ...extra }, global: { plugins: [i18n] } })
      await flushPromises()
      expect(wrapper.find('[data-testid="party-rest"]').exists()).toBe(false)
      wrapper.unmount()
    }
  })
})
