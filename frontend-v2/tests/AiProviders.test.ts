import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../src/api/client', () => {
  class ApiError extends Error {
    constructor(message: string, public status: number, public code?: string, public retryAfter?: number) { super(message) }
  }
  return { api: vi.fn(), apiBlob: vi.fn(), errorMessage: (e: unknown) => String(e), ApiError }
})

import { ApiError, api } from '../src/api/client'
import { providerSecretKey, useSettingsStore } from '../src/stores/useSettingsStore'
import { modelCapability, providerTestKind } from '../src/utils/providerModels'

const mockedApi = vi.mocked(api)

describe('AI provider library settings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockedApi.mockReset()
  })

  it('saves the provider list together with non-empty provider secrets only', async () => {
    const store = useSettingsStore()
    store.secrets[providerSecretKey('sf')] = '  sk-new  '
    store.secrets[providerSecretKey('empty')] = '   '
    mockedApi.mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({
      ai_providers: [
        { id: 'sf', name: '硅基流动', base_url: 'https://api.siliconflow.cn/v1', api_format: 'openai', models: [] },
        { id: 'empty', name: '空', base_url: 'https://e.example', api_format: 'openai', models: [] },
      ],
    })

    await store.saveProviders([
      { id: 'sf', name: '硅基流动', base_url: 'https://api.siliconflow.cn/v1', api_format: 'openai' },
      { id: 'empty', name: '空', base_url: 'https://e.example', api_format: 'openai' },
    ])

    const payload = JSON.parse(mockedApi.mock.calls[0][1]!.body as string)
    expect(payload.ai_providers).toEqual([
      { id: 'sf', name: '硅基流动', base_url: 'https://api.siliconflow.cn/v1', api_format: 'openai', models: [] },
      { id: 'empty', name: '空', base_url: 'https://e.example', api_format: 'openai', models: [] },
    ])
    expect(payload[providerSecretKey('sf')]).toBe('sk-new')
    expect(payload[providerSecretKey('empty')]).toBeUndefined()
    // 保存后清空已提交的 secret 输入
    expect(store.secrets[providerSecretKey('sf')]).toBe('')
  })

  it('rejects a legacy backend response without clearing provider secrets', async () => {
    const store = useSettingsStore()
    store.secrets[providerSecretKey('sf')] = 'sk-still-needed'
    mockedApi.mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({})

    const saving = store.saveProviders([
      {
        id: 'sf',
        name: 'SiliconFlow',
        base_url: 'https://api.siliconflow.cn/v1',
        api_format: 'openai',
        models: ['deepseek-ai/DeepSeek-V3'],
      },
    ])

    const error = await saving.catch(cause => cause)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toEqual(expect.objectContaining({
      status: 409,
      code: 'provider_library_unsupported',
    }))
    expect(store.secrets[providerSecretKey('sf')]).toBe('sk-still-needed')
  })

  it('sends provider_id for the model/embedding test when a provider is referenced', async () => {
    const store = useSettingsStore()
    store.config = {
      llm_provider_ref: 'sf',
      embedding_provider_ref: 'sf',
      embedding_model: 'bge-m3',
    } as never
    mockedApi.mockResolvedValue({ ok: true })

    await store.test('model')
    await store.test('embedding')

    const modelBody = JSON.parse(mockedApi.mock.calls[0][1]!.body as string)
    expect(modelBody.provider_id).toBe('sf')
    const embeddingBody = JSON.parse(mockedApi.mock.calls[1][1]!.body as string)
    expect(embeddingBody.provider_id).toBe('sf')
    expect(embeddingBody.model).toBe('bge-m3')
  })

  it('passes explicit credentials through when testing an unsaved provider draft', async () => {
    const store = useSettingsStore()
    mockedApi.mockResolvedValue({ ok: true })

    await store.testProvider({
      baseUrl: 'https://draft.example/v1',
      apiKey: 'sk-draft',
      apiFormat: 'anthropic',
      model: 'claude-x',
    })

    expect(mockedApi.mock.calls[0][0]).toBe('/test-connection')
    const body = JSON.parse(mockedApi.mock.calls[0][1]!.body as string)
    expect(body).toEqual({
      base_url: 'https://draft.example/v1',
      api_format: 'anthropic',
      model: 'claude-x',
      api_key: 'sk-draft',
    })
  })

  it('routes provider embedding tests through the embedding endpoint', async () => {
    const store = useSettingsStore()
    mockedApi.mockResolvedValue({ ok: true, dimension: 1024 })

    await store.testProvider({
      providerId: 'sf',
      baseUrl: 'https://api.siliconflow.cn/v1',
      apiKey: '',
      apiFormat: 'openai',
      model: 'BAAI/bge-m3',
      kind: 'embedding',
    })

    expect(mockedApi.mock.calls[0][0]).toBe('/test-embedding')
    expect(JSON.parse(mockedApi.mock.calls[0][1]!.body as string)).toEqual({
      provider_id: 'sf',
      base_url: 'https://api.siliconflow.cn/v1',
      api_format: 'openai',
      model: 'BAAI/bge-m3',
    })
  })

  it('auto-selects a compatible provider test endpoint and allows manual overrides', () => {
    expect(providerTestKind('BAAI/bge-m3')).toBe('embedding')
    expect(providerTestKind('Qwen/Qwen3-8B')).toBe('model')
    expect(providerTestKind('BAAI/bge-reranker-v2-m3')).toBeNull()
    expect(providerTestKind('Qwen/Qwen-Image')).toBeNull()
    expect(providerTestKind('custom-vector-model', 'embedding')).toBe('embedding')
  })

  it('uses and persists a manual capability when automatic detection is wrong', async () => {
    expect(modelCapability('custom-painter')).toBe('chat')
    expect(modelCapability('custom-painter', 'image')).toBe('image')
    expect(providerTestKind('custom-painter', 'auto', 'image')).toBeNull()

    const store = useSettingsStore()
    mockedApi.mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({
      ai_providers: [{
        id: 'custom', name: 'Custom', base_url: 'https://example.test/v1', api_format: 'openai',
        models: ['custom-painter'], model_capabilities: { 'custom-painter': 'image' },
      }],
    })

    await store.saveProviders([{
      id: 'custom', name: 'Custom', base_url: 'https://example.test/v1', api_format: 'openai',
      models: ['custom-painter'], model_capabilities: { 'custom-painter': 'image' },
    }])

    const payload = JSON.parse(mockedApi.mock.calls[0][1]!.body as string)
    expect(payload.ai_providers[0].model_capabilities).toEqual({ 'custom-painter': 'image' })
  })

  it('omits capability overrides when a model is restored to automatic detection', async () => {
    const store = useSettingsStore()
    mockedApi.mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({
      ai_providers: [{
        id: 'custom', name: 'Custom', base_url: 'https://example.test/v1', api_format: 'openai',
        models: ['custom-painter'],
      }],
    })

    await store.saveProviders([{
      id: 'custom', name: 'Custom', base_url: 'https://example.test/v1', api_format: 'openai',
      models: ['custom-painter'], model_capabilities: {},
    }])

    const payload = JSON.parse(mockedApi.mock.calls[0][1]!.body as string)
    expect(payload.ai_providers[0].model_capabilities).toBeUndefined()
  })

  it('requests a model catalog with saved provider credentials by id', async () => {
    const store = useSettingsStore()
    mockedApi.mockResolvedValue({ ok: true, models: ['model-b', 'model-a'], count: 2 })

    const result = await store.fetchProviderModels({
      providerId: 'sf',
      baseUrl: 'https://api.example/v1',
      apiKey: '',
      apiFormat: 'openai',
    })

    expect(result.models).toEqual(['model-b', 'model-a'])
    expect(mockedApi.mock.calls[0][0]).toBe('/config/providers/models')
    expect(JSON.parse(mockedApi.mock.calls[0][1]!.body as string)).toEqual({
      provider_id: 'sf',
      base_url: 'https://api.example/v1',
      api_format: 'openai',
    })
  })
})
