import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { NInputNumber } from 'naive-ui'
import SettingsView from '../src/features/admin/SettingsView.vue'

const mocks = vi.hoisted(() => {
  const config = {
    ai_providers: [], model: '', llm_provider_ref: '', embedding_provider_ref: '',
    tts_provider: 'browser', asr_provider: 'disabled', proxy_supported: true,
    bot_token: {}, access_password: {}, update_channel: 'stable',
  } as Record<string, any>
  return {
    store: {
      config, secrets: {}, loading: false, error: '', load: vi.fn(), saveSection: vi.fn(),
      setConfigField: vi.fn(), test: vi.fn(), saveAccessPassword: vi.fn(), clearProxy: vi.fn(), botToken: vi.fn(),
    },
    api: vi.fn().mockResolvedValue({}),
    security: {
      status: vi.fn().mockResolvedValue({ ok: true, tls_mode: 'off', scheme: 'http' }),
      prepare: vi.fn().mockResolvedValue({ ok: true, token: 'test-token', certificate: { fingerprint_sha256: 'AA:BB:CC' } }),
      activate: vi.fn(), disable: vi.fn(), regenerate: vi.fn(),
    },
    confirm: vi.fn().mockResolvedValue(false),
    replace: vi.fn(),
    updateStatus: null as Record<string, any> | null,
  }
})

vi.mock('../src/stores/useSettingsStore', () => ({ useSettingsStore: () => mocks.store }))
vi.mock('../src/composables/useToast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }) }))
vi.mock('../src/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: mocks.confirm }) }))
vi.mock('../src/composables/useLocale', () => ({ useLocale: () => ({ t: (key: string) => key, locale: ref('en') }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: { section: 'models' } }), useRouter: () => ({ push: vi.fn(), replace: mocks.replace }) }))
vi.mock('../src/composables/useUpdateCheck', () => ({ useUpdateCheck: () => ({ updateInfo: ref(null), updateChecking: ref(false), checkForUpdates: vi.fn() }) }))
vi.mock('../src/composables/useUpdater', () => ({
  shouldAutoDownloadUpdate: vi.fn(() => false), updateStateForVersion: vi.fn(),
  useUpdater: () => ({ updateStatus: ref(mocks.updateStatus), reloadCountdown: ref(0), downloadPercent: ref(0), startDownload: vi.fn(), applyUpdate: vi.fn(), refreshStatus: vi.fn(), isUpdateBusy: ref(false), restartApplication: vi.fn(), waitForApplicationRestart: vi.fn() }),
}))
vi.mock('../src/composables/useTheme', () => ({ useTheme: () => ({ current: ref('dark'), skin: ref('midnight'), builtinSkins: [], apply: vi.fn(), applySkin: vi.fn(), pluginThemes: ref([]), pluginThemeId: ref(''), loadPluginThemes: vi.fn(), applyPluginTheme: vi.fn(), clearPluginTheme: vi.fn() }) }))
vi.mock('../src/composables/useBackgroundImages', () => ({ useBackgroundImages: () => ({ options: [], previews: {}, custom: {}, loading: ref(false), initialize: vi.fn(), setBackground: vi.fn(), resetBackground: vi.fn(), resetAllBackgrounds: vi.fn() }) }))
vi.mock('../src/composables/useProviderModelSettings', () => ({ useProviderModelSettings: () => ({
  providerDrafts: ref([]), providerTestModels: {}, providerTestModes: {}, providerSearch: ref(''), providerSaving: ref(false), providerTestingId: ref(''), providerFetchingModelsId: ref(''), providerTestedId: ref(''), providerTestedKind: ref(''), providerTestResult: ref(null), providerCatalogOpen: ref(false), activeProviderId: ref(''), activeCatalogProvider: ref(null), providerCatalogSourceModels: ref([]), providerLibrarySupported: true, providerSecretValue: vi.fn(() => ''), providerById: vi.fn(), providerMark: vi.fn(() => 'P'), providerStyle: vi.fn(() => ({})), providerDraftReady: vi.fn(() => false), providerModelCapabilityOptions: [], providerTestModeOptions: [], providerTestActionLabel: vi.fn(() => 'test'), activeProvider: ref(null), activeProviderModelGroups: ref([]), readyProviderIds: [], modelRoutingSaving: ref(false), catalogAssignmentBusy: '', catalogModelAssignmentOptions: vi.fn(() => []), catalogModelAssignmentValue: vi.fn(() => ''), catalogModelCanAssign: vi.fn(() => true), addProviderDraft: vi.fn(), fetchProviderModels: vi.fn(), toggleCatalogModel: vi.fn(), addAllCatalogModels: vi.fn(), assignCatalogModelRole: vi.fn(), openProviderCatalog: vi.fn(), saveProviderDraft: vi.fn(), removeProviderDraft: vi.fn(), testProviderDraft: vi.fn(),
}) }))
vi.mock('../src/utils/tts', async () => {
  const { ref } = await import('vue')
  return { initializeTts: vi.fn(), ttsRate: vi.fn(() => 1), setTtsRate: vi.fn(), ttsRuntimeConfig: ref({ provider: 'browser' }), speakingKey: ref(''), stripHtml: (value: string) => value, ttsSpeak: vi.fn(), ttsStop: vi.fn(), ttsSupported: vi.fn(() => true) }
})
vi.mock('../src/utils/asr', () => ({ asrLanguageFor: vi.fn(), initializeAsr: vi.fn(), startRecording: vi.fn(), serverAsrReady: vi.fn(() => false) }))
vi.mock('../src/api/client', () => ({ api: mocks.api, apiBlob: mocks.api, errorMessage: (e: unknown) => String(e), ApiError: class extends Error {} }))
vi.mock('../src/api/speech', () => ({ speechApi: { voices: vi.fn().mockResolvedValue({ voices: [] }), test: vi.fn(), transcribeTest: vi.fn() } }))
vi.mock('../src/api/plugins', () => ({ pluginApi: { hubPreferences: vi.fn().mockResolvedValue(null), updateHubPreferences: vi.fn(), deleteHubIdentity: vi.fn() } }))
vi.mock('../src/api/security', () => ({ securityApi: mocks.security }))

describe('SettingsView management navigation', () => {
  it('places a separate Game page directly after General', async () => {
    const wrapper = shallowMount(SettingsView, { global: { stubs: { Spin: { template: '<div><slot /></div>' }, RouterLink: true } } })
    await flushPromises()
    const general = wrapper.get('.settings-nav [data-section="general"]')
    expect(general.element.nextElementSibling?.getAttribute('data-section')).toBe('game')
    await wrapper.get('.settings-nav [data-section="game"]').trigger('click')
    expect(wrapper.get('.settings-game-pane').isVisible()).toBe(true)
    expect(wrapper.get('#settings-language').isVisible()).toBe(false)
    expect(mocks.replace).toHaveBeenCalledWith({ query: { section: 'game', focus: undefined } })
    wrapper.unmount()
  })
  beforeEach(() => {
    mocks.store.load.mockReset()
    mocks.api.mockClear()
    mocks.confirm.mockClear()
    mocks.security.status.mockClear()
    mocks.security.prepare.mockClear()
    mocks.updateStatus = null
  })

  it('warns about self-signed TLS for plugin and internal clients', async () => {
    const wrapper = shallowMount(SettingsView, {
      global: {
        stubs: {
          Spin: { template: '<div><slot /></div>' },
          Button: { template: '<button @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
          NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
          RouterLink: true,
        },
      },
    })
    await flushPromises()
    await wrapper.get('.settings-nav [data-section="security"]').trigger('click')
    await flushPromises()

    const selfSignedRow = wrapper.findAll('.security-mode-row')[1]
    await selfSignedRow!.get('button').trigger('click')
    await flushPromises()

    expect(mocks.security.prepare).toHaveBeenCalledWith('self_signed')
    expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({
      dialogClass: 'security-confirm-dialog',
      contentClass: 'security-confirm-content',
    }))
    const options = mocks.confirm.mock.calls[0]![0]
    const content = options.content()
    expect(content.props.class).toBe('security-confirm-body')
    expect(content.children[1].children[2].children).toBe('securityEnableConfirmPlugin')
    wrapper.unmount()
  })

  it('lets the owner edit and save reply and task budgets independently', async () => {
    mocks.store.config.assistant_agent_max_tokens = 4096
    mocks.store.config.assistant_agent_task_max_tokens = 64000
    mocks.store.setConfigField.mockClear()
    mocks.store.saveSection.mockClear()
    const wrapper = shallowMount(SettingsView, { global: { stubs: { Spin: { template: '<div><slot /></div>' }, Button: { template: '<button @click="$emit(\'click\')"><slot /></button>', emits: ['click'] }, RouterLink: true } } })
    await flushPromises()
    const budgets = wrapper.get('#settings-agent-budget')
    expect(budgets.findAll('.token-row strong').map(row => row.text())).toEqual(['assistantAgentReplyBudget', 'assistantAgentTaskBudget'])
    const inputs = budgets.findAllComponents(NInputNumber)
    expect(inputs).toHaveLength(2)
    expect(inputs[0]!.props('value')).toBe(4096)
    expect(inputs[1]!.props('value')).toBe(64000)
    inputs[0]!.vm.$emit('update:value', 8192)
    inputs[1]!.vm.$emit('update:value', 128000)
    expect(mocks.store.setConfigField).toHaveBeenCalledWith('assistant_agent_max_tokens', 8192)
    expect(mocks.store.setConfigField).toHaveBeenCalledWith('assistant_agent_task_max_tokens', 128000)
    const saveButton = budgets.get('.advanced-save-row > *')
    await saveButton.trigger('click')
    expect(mocks.store.saveSection).toHaveBeenCalledWith(expect.arrayContaining(['assistant_agent_max_tokens', 'assistant_agent_task_max_tokens']), [])
    wrapper.unmount()
  })

  it('exposes the shared system language preference in general settings', async () => {
    const wrapper = shallowMount(SettingsView, { global: { stubs: { Spin: { template: '<div><slot /></div>' }, RouterLink: true } } })
    expect(wrapper.find('language-preferences-stub').exists()).toBe(true)
    wrapper.unmount()
  })

  it('selects a deep-linked section and keeps grouped navigation reachable', async () => {
    const wrapper = shallowMount(SettingsView, { global: { stubs: { ContentPageHeader: true, HelpButton: true, ProviderLibrary: true, ProviderCatalogModal: true, ModelRoutingPane: true, ProviderModelRow: true, ProviderTestSection: true, TestResultCard: true, TtsVoiceProfiles: true, BrandLogo: true } } })
    await flushPromises()
    expect(wrapper.find('.settings-nav-group-label').exists()).toBe(true)
    expect(wrapper.findAll('.settings-nav .nav-item').length).toBeGreaterThanOrEqual(9)
    expect(wrapper.find('.settings-nav .nav-item.active').text()).toContain('settingsSectionModels')
    await wrapper.findAll('.settings-nav .nav-item').find(button => button.text().includes('settingsSectionAppearance'))!.trigger('click')
    expect(mocks.replace).toHaveBeenCalledWith({ query: { section: 'appearance', focus: undefined } })
    expect(wrapper.find('.settings-nav .nav-item.active').text()).toContain('settingsSectionAppearance')
  })

  it('renders language, voice, Agent and maintenance together on one general page', async () => {
    const wrapper = shallowMount(SettingsView, { global: { stubs: { Spin: { template: '<div><slot /></div>' }, RouterLink: true } } })
    await flushPromises()
    await wrapper.get('.settings-nav [data-section="general"]').trigger('click')
    const pane = wrapper.get('#settings-language').element.closest('.settings-pane')!
    for (const id of ['settings-tts', 'settings-agent', 'settings-agent-budget', 'settings-runtime-logs', 'settings-test-timeout']) {
      expect(wrapper.get(`#${id}`).isVisible(), id).toBe(true)
      expect(wrapper.get(`#${id}`).element.closest('.settings-pane'), id).toBe(pane)
    }
    for (const id of ['voice', 'agent', 'system']) expect(wrapper.find(`.settings-nav [data-section="${id}"]`).exists()).toBe(false)
    expect(wrapper.findAll('.settings-nav-group-label').map(label => label.text())).toEqual(['Models and AI', 'Connection and integrations', 'Security and privacy', 'General'])
    wrapper.unmount()
  })

  it('keeps the status overview closed until the user opens it', async () => {
    const wrapper = shallowMount(SettingsView, { global: { stubs: { ContentPageHeader: true, HelpButton: true, ProviderLibrary: true, ProviderCatalogModal: true, ModelRoutingPane: true, ProviderModelRow: true, ProviderTestSection: true, TestResultCard: true, TtsVoiceProfiles: true, BrandLogo: true } } })
    await flushPromises()
    const details = wrapper.find('.settings-status-disclosure')
    expect(details.attributes('open')).toBeUndefined()
    await details.find('summary').trigger('click')
    expect(details.attributes('open')).toBeDefined()
  })

  it('keeps updates in About and only version rollback in General maintenance', async () => {
    mocks.updateStatus = { state: 'done', self_update: { supported: true }, rollback: { available: true, target_version: '3.0.0-beta.1' } }
    const wrapper = shallowMount(SettingsView, { attachTo: document.body, global: { stubs: { Spin: { template: '<div><slot /></div>' }, Button: { template: '<button><slot /></button>' }, RouterLink: true } } })
    await flushPromises()
    await wrapper.get('.settings-nav [data-section="about"]').trigger('click')
    expect(wrapper.get('#settings-update').isVisible()).toBe(true)
    expect(wrapper.get('#settings-update').element.closest('.about')).not.toBeNull()
    expect(wrapper.get('#settings-update').text()).toContain('checkUpdate')
    expect(wrapper.get('#settings-update').text()).not.toContain('rollbackAvailableHint')
    await wrapper.get('.settings-nav [data-section="general"]').trigger('click')
    expect(wrapper.get('#settings-update').isVisible()).toBe(false)
    const rollback = wrapper.get('#settings-rollback')
    expect(rollback.isVisible()).toBe(true)
    expect(rollback.element.closest('#settings-maintenance')).not.toBeNull()
    expect(rollback.text()).toContain('rollbackAvailableHint')
    expect(rollback.text()).not.toContain('updateApplied')
    expect(rollback.text()).not.toContain('checkUpdate')
    wrapper.unmount()
  })
})
