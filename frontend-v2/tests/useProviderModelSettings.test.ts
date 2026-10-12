import { describe, expect, it, vi } from 'vitest'
import {
  hydrateProviderDrafts,
  serializeProviderDrafts,
  useProviderModelSettings,
  type ProviderModelSettingsStore,
  type ProviderModelSettingsToast,
} from '../src/composables/useProviderModelSettings'
import type { AppConfig } from '../src/api/types'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function createToast(): ProviderModelSettingsToast {
  return {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }
}

function createStore(
  config: Partial<AppConfig>,
  overrides: Partial<ProviderModelSettingsStore> = {},
): ProviderModelSettingsStore {
  const store: ProviderModelSettingsStore = {
    config,
    secrets: {},
    saveProviders: vi.fn(async () => []),
    saveSection: vi.fn(async () => []),
    testProvider: vi.fn(async () => ({ ok: true })),
    fetchProviderModels: vi.fn(async () => ({ ok: true, models: [] })),
    setConfigField(key, value) {
      ;(store.config as Record<string, unknown>)[key] = value
    },
    ...overrides,
  }
  return store
}

const t = (key: string) => key

describe('provider draft boundary', () => {
  it('hydrates and serializes provider drafts without losing capability overrides or secrets metadata', () => {
    const source: NonNullable<AppConfig['ai_providers']> = [{
      id: 'provider-a',
      name: 'Provider A',
      base_url: 'https://example.test/v1',
      api_format: 'openai',
      models: [' chat-a ', 'chat-a', 'image-a'],
      model_capabilities: { 'image-a': 'image' },
      api_key: { configured: true, masked: 'sk-***' },
    }]

    const drafts = hydrateProviderDrafts(source)
    expect(drafts).toEqual([{
      id: 'provider-a',
      name: 'Provider A',
      base_url: 'https://example.test/v1',
      api_format: 'openai',
      models: ['chat-a', 'image-a'],
      model_capabilities: { 'image-a': 'image' },
      configuredMasked: 'sk-***',
    }])

    drafts[0].model_capabilities['chat-a'] = 'chat'
    const serialized = serializeProviderDrafts(drafts)
    expect(serialized[0]).toEqual({
      id: 'provider-a',
      name: 'Provider A',
      base_url: 'https://example.test/v1',
      api_format: 'openai',
      models: ['chat-a', 'image-a'],
      model_capabilities: { 'image-a': 'image', 'chat-a': 'chat' },
    })
    expect(source[0].model_capabilities).toEqual({ 'image-a': 'image' })
    expect(serialized[0]).not.toHaveProperty('configuredMasked')
  })
})

describe('useProviderModelSettings save contracts', () => {
  it('rolls a catalog assignment back completely when model routing persistence fails', async () => {
    const store = createStore({
      ai_providers: [{
        id: 'provider-b',
        name: 'Provider B',
        base_url: 'https://example.test/v1',
        api_format: 'openai',
        models: ['image-b'],
        model_capabilities: { 'image-b': 'image' },
      }],
      imagegen_provider_ref: 'provider-a',
      imagegen_model: 'image-a',
      imagegen_enabled: false,
    }, {
      saveSection: vi.fn(async () => { throw new Error('save failed') }),
    })
    const settings = useProviderModelSettings({ store, t, toast: createToast() })

    const saved = await settings.assignCatalogModelRole(
      settings.providerDrafts.value[0],
      'image-b',
      'imagegen',
    )

    expect(saved).toBe(false)
    expect(store.config.imagegen_provider_ref).toBe('provider-a')
    expect(store.config.imagegen_model).toBe('image-a')
    expect(store.config.imagegen_enabled).toBe(false)
    expect(settings.catalogAssignmentBusy.value).toBe('')
  })

  it('restores an immediately persisted toggle when saving fails', async () => {
    const store = createStore({ ai_providers: [], embedding_enabled: false }, {
      saveSection: vi.fn(async () => { throw new Error('save failed') }),
    })
    const settings = useProviderModelSettings({ store, t, toast: createToast() })

    expect(await settings.setModelRoutingBool('embedding_enabled', true)).toBe(false)
    expect(store.config.embedding_enabled).toBe(false)
  })

  it('keeps provider saves single-flight and exposes the busy state', async () => {
    const pending = deferred<string[]>()
    const saveProviders = vi.fn(() => pending.promise)
    const store = createStore({ ai_providers: [] }, { saveProviders })
    const settings = useProviderModelSettings({ store, t, toast: createToast() })

    const first = settings.saveProvidersList()
    expect(settings.providerSaving.value).toBe(true)
    await expect(settings.saveProvidersList()).resolves.toBe(false)
    expect(saveProviders).toHaveBeenCalledTimes(1)

    pending.resolve([])
    await expect(first).resolves.toBe(true)
    expect(settings.providerSaving.value).toBe(false)
  })

  it('refreshes TTS/ASR runtimes only after routing persistence succeeds', async () => {
    const order: string[] = []
    const store = createStore({ ai_providers: [] }, {
      saveSection: vi.fn(async () => {
        order.push('save')
        return []
      }),
    })
    const settings = useProviderModelSettings({
      store,
      t,
      toast: createToast(),
      refreshModelRuntimes: async () => { order.push('refresh') },
    })

    await expect(settings.saveModelRouting()).resolves.toBe(true)
    expect(order).toEqual(['save', 'refresh'])
  })
})
