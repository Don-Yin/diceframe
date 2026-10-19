import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App.vue'
import { isPublicRoute } from '../src/router'
import { i18n } from '../src/i18n'
import { useAssistant } from '../src/composables/useAssistant'
import { useAssistantPreferences } from '../src/composables/useAssistantPreferences'

vi.mock('../src/composables/useTheme', () => ({
  useTheme: () => ({
    naiveTheme: null,
    overrides: {},
    loadPluginThemes: vi.fn().mockResolvedValue(undefined),
    suspendPluginTheme: vi.fn(),
    restorePluginTheme: vi.fn(),
  }),
}))
vi.mock('../src/composables/useBackgroundImages', () => ({
  initializeBackgroundImages: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('../src/composables/useUpdateCheck', () => ({
  useUpdateCheck: () => ({ updateAvailable: ref(false) }),
}))
vi.mock('../src/composables/useAnnouncements', () => ({
  useAnnouncements: () => ({
    hasUnread: ref(false),
    load: vi.fn().mockResolvedValue(undefined),
    markRead: vi.fn(),
  }),
}))

const routeComponent = (name: string) => ({ template: `<div data-route="${name}" />` })

function makeRouter() {
  const names = [
    'overview', 'play', 'characters', 'creator', 'library', 'worlds', 'adventures',
    'modules', 'module-detail', 'lorebook', 'rules', 'memory', 'logs', 'plugins', 'settings',
    'login', 'join', 'peer', 'legal-terms', 'legal-privacy',
  ]
  return createRouter({
    history: createMemoryHistory(),
    routes: names.map(name => ({
      path: name === 'overview' ? '/overview' : `/${name}`,
      name,
      component: routeComponent(name),
    })),
  })
}

async function mountApp(router: ReturnType<typeof makeRouter>) {
  await router.push({ name: 'overview' })
  await router.isReady()
  const wrapper = mount(App, {
    global: {
      plugins: [router, i18n],
      stubs: {
        AssistantPanel: { template: '<div data-testid="assistant-panel" />' },
        NDrawer: { template: '<div><slot /></div>' },
        NDrawerContent: { template: '<div><slot /></div>' },
        NIcon: { template: '<span />' },
        ThemeToggle: { template: '<span />' },
        AnnouncementButton: { template: '<span />' },
        AnnouncementPanel: { template: '<span />' },
        DevicePairingButton: { template: '<span />' },
        BrandLogo: { template: '<span />' },
        StartupPrivacyChoice: { template: '<span />' },
        StartupUpdateCheck: { template: '<span />' },
        SectionWorkspaceShell: { template: '<div><slot /></div>' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('App DF Agent route boundary', () => {
  beforeEach(() => {
    localStorage.clear()
    useAssistantPreferences().setEnabled(true)
    const assistant = useAssistant()
    assistant.messages.value = []
    assistant.streaming.value = false
    i18n.global.locale.value = 'en'
  })

  it('shows one owner entry and hides it on every public/player route', async () => {
    const router = makeRouter()
    const wrapper = await mountApp(router)

    const ownerPaths = [
      { name: 'overview' },
      { name: 'play' },
      { name: 'settings' },
    ] as const
    for (const location of ownerPaths) {
      await router.push(location)
      await flushPromises()
      expect(isPublicRoute(router.currentRoute.value)).toBe(false)
      expect(wrapper.findAll('[data-testid="assistant-shell"]')).toHaveLength(1)
    }

    const publicPaths = [
      { name: 'play', query: { user: 'player-1' } },
      { name: 'play', query: { share: 'share-token' } },
      { name: 'login' },
      { name: 'join' },
      { name: 'legal-terms' },
      { name: 'legal-privacy' },
      { name: 'peer' },
    ] as const
    for (const location of publicPaths) {
      await router.push(location)
      await flushPromises()
      expect(isPublicRoute(router.currentRoute.value)).toBe(true)
      expect(wrapper.find('[data-testid="assistant-shell"]').exists()).toBe(false)
    }
    wrapper.unmount()
  })

  it('reopens from Appearance and preserves the shared conversation task across owner routes', async () => {
    const router = makeRouter()
    const wrapper = await mountApp(router)
    const assistant = useAssistant()
    assistant.messages.value = [{ role: 'user', content: 'keep this conversation' }]
    assistant.streaming.value = true

    useAssistantPreferences().setEnabled(false)
    await nextTick()
    expect(wrapper.find('[data-testid="assistant-shell"]').exists()).toBe(false)

    useAssistantPreferences().setEnabled(true)
    await nextTick()
    expect(wrapper.find('[data-testid="assistant-shell"]').exists()).toBe(true)
    const shellElement = wrapper.get('[data-testid="assistant-shell"]').element

    await router.push({ name: 'settings' })
    await flushPromises()
    expect(wrapper.get('[data-testid="assistant-shell"]').element).toBe(shellElement)
    expect(assistant.messages.value[0]?.content).toBe('keep this conversation')
    expect(assistant.streaming.value).toBe(true)

    assistant.streaming.value = false
    wrapper.unmount()
  })
})
