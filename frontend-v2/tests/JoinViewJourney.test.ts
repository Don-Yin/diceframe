import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({ api: vi.fn(), confirm: vi.fn(), remember: vi.fn() }))

vi.mock('../src/api/client', () => ({
  api: mocks.api,
  errorMessage: (error: unknown) => String(error),
  retryOnRateLimit: <T>(request: () => Promise<T>) => request(),
}))
vi.mock('../src/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: mocks.confirm }) }))
vi.mock('../src/stores/gameContext', () => ({ rememberCurrentGame: mocks.remember }))
vi.mock('../src/peer/game/bridge', () => ({ activePeerGameClient: () => null }))
vi.mock('../src/peer/store/peerSession', () => ({ usePeerSessionStore: () => ({ hasPersistedSession: () => false }) }))

import JoinView from '../src/features/player/JoinView.vue'

async function render(query: Record<string, string> = { game: 'web|resume|gm', seat: 'example-seat-token', share: '1' }) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/join', name: 'join', component: JoinView },
      { path: '/overview', name: 'overview', component: { template: '<div />' } },
      { path: '/play', name: 'play', component: { template: '<div />' } },
    ],
  })
  await router.push({ name: 'join', query })
  const wrapper = mount(JoinView, {
    attachTo: document.body,
    global: {
      plugins: [i18n, router],
      stubs: {
        BrandLogo: { template: '<span />' },
        PortraitPicker: {
          props: ['modelValue'],
          template: '<div data-testid="portrait-picker" :data-portrait="JSON.stringify(modelValue)" />',
        },
        RulesetExperienceHost: { template: '<div />' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('JoinView recovery journey', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    localStorage.clear()
    mocks.api.mockReset()
    mocks.confirm.mockReset()
    mocks.remember.mockReset()
  })

  it('does not replay identity recovery after an uncertain POST result', async () => {
    mocks.api.mockImplementation(async (path: string) => {
      if (path.endsWith('/players')) throw new Error('request lost after submit')
      if (path.endsWith('/characters')) return { players: [], rule_attrs: [], rule_meta: {} }
      if (path.endsWith('/character-cards')) return { cards: [] }
      return { world_name: 'Recovered table', scene: 'A quiet road', has_room_password: false }
    })

    const wrapper = await render()
    expect(wrapper.text()).toContain('request lost after submit')
    expect(wrapper.text()).toContain('Continue with a new identity')
    expect(mocks.api.mock.calls.filter(([path]) => String(path).includes('/players')).length).toBe(1)

    await wrapper.get('.join-error button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Create Your Character')
    expect(mocks.api.mock.calls.filter(([path]) => String(path).includes('/players')).length).toBe(1)
    expect(mocks.api.mock.calls.filter(([path]) => String(path).includes('/characters')).length).toBe(1)
    wrapper.unmount()
  })

  it('keeps the password gate as the current step and retries verification in place', async () => {
    let attempts = 0
    mocks.api.mockImplementation(async (path: string) => {
      if (path.endsWith('/verify-room-password')) {
        if (++attempts === 1) throw new Error('incorrect password')
        return { room_token: 'example-room-token' }
      }
      if (path.endsWith('/characters')) return { players: [], rule_attrs: [], rule_meta: {} }
      if (path.endsWith('/character-cards')) return { cards: [] }
      return { world_name: 'Locked table', has_room_password: true }
    })

    const wrapper = await render({ game: 'web|password|gm', share: '1' })
    expect(wrapper.find('.join-progress li.active').text()).toContain('Access')
    await wrapper.get('input[type="password"]').setValue('wrong')
    await wrapper.get('.room-gate button.primary').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('incorrect password')
    expect(wrapper.find('.join-progress li.active').text()).toContain('Access')

    await wrapper.get('.join-error button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Create Your Character')
    expect(mocks.api.mock.calls.filter(([path]) => String(path).includes('verify-room-password')).length).toBe(2)
    wrapper.unmount()
  })

  it('offers a read-only retry when character rules fail to load', async () => {
    let attempts = 0
    mocks.api.mockImplementation(async (path: string) => {
      if (path.endsWith('/characters')) {
        if (++attempts === 1) throw new Error('rules offline')
        return { players: [], rule_attrs: [], rule_meta: {} }
      }
      if (path.endsWith('/character-cards')) return { cards: [] }
      return { world_name: 'Rules table', has_room_password: false }
    })

    const wrapper = await render({ game: 'web|rules|gm', share: '1' })
    expect(wrapper.text()).toContain('rules offline')
    expect(wrapper.find('.join-progress li.active').text()).toContain('Identity')
    await wrapper.get('.join-error button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Create Your Character')
    expect(mocks.api.mock.calls.filter(([path]) => String(path).includes('/characters')).length).toBeGreaterThanOrEqual(1)
    wrapper.unmount()
  })

  it('rechecks a failed detail request and restores the password gate', async () => {
    mocks.api
      .mockRejectedValueOnce(new Error('detail offline'))
      .mockResolvedValueOnce({ world_name: 'Locked after retry', has_room_password: true })

    const wrapper = await render({ game: 'web|detail-retry|gm', share: '1' })
    expect(wrapper.text()).toContain('detail offline')
    await wrapper.get('.join-error button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('This room requires a password')
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps a filled form visible after create failure without offering replay', async () => {
    mocks.api
      .mockResolvedValueOnce({ world_name: 'Create table', has_room_password: false })
      .mockResolvedValueOnce({ players: [], rule_attrs: [], rule_meta: {} })
      .mockResolvedValueOnce({ cards: [] })
      .mockRejectedValueOnce(new Error('create result unknown'))

    const wrapper = await render({ game: 'web|create-error|gm', share: '1' })
    const name = wrapper.find('input[maxlength="40"]')
    await name.setValue('Keep this draft')
    await wrapper.get('.player-sheet-form button.primary.submit').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('create result unknown')
    expect((name.element as HTMLInputElement).value).toBe('Keep this draft')
    expect(wrapper.find('.player-sheet-form .join-error button').exists()).toBe(false)
    expect(mocks.api.mock.calls.filter(([path]) => String(path).includes('/players')).length).toBe(1)
    wrapper.unmount()
  })

  it('keeps the portrait picker mounted and bound while the compact summary is closed', async () => {
    mocks.api
      .mockResolvedValueOnce({ world_name: 'Portrait table', has_room_password: false })
      .mockResolvedValueOnce({ players: [], rule_attrs: [], rule_meta: {} })
      .mockResolvedValueOnce({ cards: [] })
    const wrapper = await render({ game: 'web|portrait|gm', share: '1' })
    const vm = wrapper.vm as unknown as { form: { portrait: { kind: string; id: string } } }
    vm.form.portrait = { kind: 'builtin', id: 'fantasy-0' }
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.join-avatar-details').attributes('open')).toBeUndefined()
    expect(wrapper.find('[data-testid="portrait-picker"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="portrait-picker"]').attributes('data-portrait')).toContain('fantasy-0')
    await wrapper.get('.join-avatar-details summary').trigger('click')
    expect(wrapper.find('.join-avatar-details').attributes('open')).toBeDefined()
    expect(wrapper.find('[data-testid="portrait-picker"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps the read-only party/status rail visible for a new empty room', async () => {
    mocks.api
      .mockResolvedValueOnce({ world_name: 'Empty table', has_room_password: false })
      .mockResolvedValueOnce({ players: [], rule_attrs: [], rule_meta: {} })
      .mockResolvedValueOnce({ cards: [] })

    const wrapper = await render({ game: 'web|empty|gm', share: '1' })
    await flushPromises()
    expect(wrapper.find('[data-testid="join-party-preview"]').exists()).toBe(true)
    expect(wrapper.find('.join-party-preview__empty').text()).toContain('没有队伍成员')
    wrapper.unmount()
  })

  it('explains that a generic invite creates a new bound character in both join forms', async () => {
    const help = String(i18n.global.t('joinCharacterHelp'))
    mocks.api.mockImplementation(async (path: string) => {
      if (path.endsWith('/characters')) return { players: [], rule_attrs: [], rule_meta: {} }
      if (path.endsWith('/character-cards')) return { cards: [] }
      return { world_name: 'Generic invite table', has_room_password: false }
    })

    const ordinary = await render({ game: 'web|generic|gm', share: '1' })
    expect(ordinary.find('.player-sheet-form .sheet-head p').text()).toBe(help)
    ordinary.unmount()

    mocks.api.mockImplementation(async (path: string) => {
      if (path.endsWith('/characters')) {
        return {
          players: [],
          rule_attrs: [],
          rule_meta: {},
          ruleset_runtime: { capabilities: { character_builder: 'professional' } },
        }
      }
      if (path.endsWith('/character-cards')) return { cards: [] }
      return { world_name: 'Professional invite table', has_room_password: false }
    })
    const professional = await render({ game: 'web|professional|gm', share: '1' })
    expect(professional.find('.professional-join-form .sheet-head p').text()).toBe(help)
    professional.unmount()
  })
})
