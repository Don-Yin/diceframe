import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import ModelRoutingPane from '../src/features/admin/settings/ModelRoutingPane.vue'
import { useProviderModelSettings } from '../src/composables/useProviderModelSettings'
import { useSettingsStore } from '../src/stores/useSettingsStore'
import type { AppConfig } from '../src/api/types'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api }
})

beforeEach(() => {
  setActivePinia(createPinia())
  mocks.api.mockReset()
  i18n.global.locale.value = 'zh-CN'
})

function setup(config: Partial<AppConfig>, supported = true) {
  const store = useSettingsStore()
  store.config = structuredClone(config)
  let persisted = structuredClone(config)
  mocks.api.mockImplementation(async (_path: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      persisted = { ...persisted, ...JSON.parse(String(options.body)) }
      return {}
    }
    return structuredClone(persisted)
  })
  const settings = useProviderModelSettings({
    store,
    t: key => key,
    toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
  })
  const wrapper = mount(ModelRoutingPane, {
    props: {
      supported, saving: false, embeddingTesting: false, embeddingResult: null,
      onSave: () => { void settings.saveModelRouting() },
    },
    global: {
      plugins: [i18n],
      stubs: {
        HelpButton: true,
        TestResultCard: true,
        teleport: true,
      },
    },
  })
  return { wrapper, store }
}

it('allows Edge TTS with an empty provider catalog and persists its default voice', async () => {
  const { wrapper, store } = setup({
    ai_providers: [], tts_provider: 'browser', tts_provider_ref: '',
    tts_default_voice: 'alloy', asr_provider: 'disabled',
  })
  const ttsMode = wrapper.findAll('select').find(select => select.find('option[value="edge-tts"]').exists())
  expect(ttsMode).toBeDefined()
  await ttsMode!.setValue('edge-tts')
  await wrapper.get('.model-routing-save').trigger('click')
  await flushPromises()

  const post = mocks.api.mock.calls.find(([, options]) => options?.method === 'POST')
  expect(JSON.parse(post![1].body)).toMatchObject({
    tts_provider: 'edge-tts', tts_provider_ref: '', tts_default_voice: 'zh-CN-XiaoxiaoNeural',
  })
  expect(store.config.tts_provider).toBe('edge-tts')
  expect(store.config.tts_default_voice).toBe('zh-CN-XiaoxiaoNeural')
  expect(store.config.ai_providers).toEqual([])
  wrapper.unmount()
})

it('persists the OpenAI default voice after switching from Edge TTS', async () => {
  const { wrapper, store } = setup({
    ai_providers: [{ id: 'local', name: 'Local', base_url: 'http://localhost:8000/v1', api_format: 'openai', models: ['tts-1'] }],
    tts_provider: 'edge-tts', tts_provider_ref: 'local', tts_model: 'tts-1',
    tts_default_voice: 'zh-CN-XiaoxiaoNeural',
  })
  const ttsMode = wrapper.findAll('select').find(select => select.find('option[value="edge-tts"]').exists())!
  await ttsMode.setValue('openai-compatible')
  await wrapper.get('.model-routing-save').trigger('click')
  await flushPromises()

  const post = mocks.api.mock.calls.find(([, options]) => options?.method === 'POST')
  expect(JSON.parse(post![1].body)).toMatchObject({
    tts_provider: 'openai-compatible', tts_provider_ref: 'local', tts_default_voice: 'alloy',
  })
  expect(store.config.tts_default_voice).toBe('alloy')
  wrapper.unmount()
})

it('keeps routing unavailable when the backend does not support provider configuration', () => {
  const { wrapper } = setup({ ai_providers: [] }, false)
  expect(wrapper.findAll('select')).toHaveLength(0)
  expect(wrapper.get('.model-routing-save').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})

it('keeps image generation basics visible and exposes advanced fields on demand', async () => {
  const { wrapper } = setup({
    ai_providers: [{ id: 'image', name: 'Image', base_url: 'http://localhost:8000/v1', api_format: 'openai', models: ['image-1'] }],
    imagegen_enabled: true,
    imagegen_auto_scene: true,
    imagegen_manual_scene: false,
    imagegen_provider_ref: 'image',
    imagegen_model: 'image-1',
  })

  expect(wrapper.text()).toContain('自动生成场景图')
  expect(wrapper.text()).toContain('手动生成场景图')
  expect(wrapper.text()).toContain('统一风格前缀')
  expect(wrapper.text()).toContain('高级图像设置')
  expect(wrapper.text()).toContain('手动提示词模板')
  expect(wrapper.find('textarea').exists()).toBe(true)
  const advancedSettings = wrapper.get('.imagegen-advanced-settings')
  expect(advancedSettings.text()).toContain('高级图像设置')
  expect(advancedSettings.element).not.toHaveProperty('open', true)
  await advancedSettings.find('summary').trigger('click')
  await flushPromises()
  expect(advancedSettings.element).toHaveProperty('open', true)
  expect(wrapper.text()).toContain('留空使用默认尺寸')
  wrapper.unmount()
})

it('hides inactive automatic prompt fields while preserving their drafts', () => {
  const { wrapper, store } = setup({
    ai_providers: [],
    imagegen_enabled: true,
    imagegen_auto_use_manual_prompt: true,
    imagegen_manual_rules: 'manual rules',
    imagegen_manual_prompt: 'manual {scene}',
    imagegen_auto_rules: 'saved automatic rules',
    imagegen_auto_prompt: 'saved automatic {scene}',
  })

  expect(wrapper.text()).toContain('自动生成当前使用上方的手动规则和模板')
  expect(wrapper.text()).not.toContain('自动提示词规则')
  expect(wrapper.text()).not.toContain('自动提示词模板')
  expect(store.config.imagegen_auto_rules).toBe('saved automatic rules')
  expect(store.config.imagegen_auto_prompt).toBe('saved automatic {scene}')
  expect(wrapper.get('textarea[placeholder*="写实奇幻插画"]').attributes('placeholder')).toContain('写实奇幻插画')
  wrapper.unmount()
})

it('previews AI optimization and only updates the unsaved settings draft', async () => {
  const { wrapper, store } = setup({
    ai_providers: [],
    imagegen_enabled: true,
    imagegen_style_prefix: 'fantasy art',
    imagegen_auto_use_manual_prompt: true,
  })
  mocks.api.mockImplementation(async (path: string) => {
    if (path === '/image-prompts/optimize') {
      return { ok: true, text: 'cinematic grounded fantasy art' }
    }
    return {}
  })

  await wrapper.get('.imagegen-style-field button').trigger('click')
  await flushPromises()

  expect(wrapper.text()).toContain('cinematic grounded fantasy art')
  expect(store.config.imagegen_style_prefix).toBe('fantasy art')
  const buttons = wrapper.findAll('.imagegen-optimizer-preview button')
  await buttons[buttons.length - 1].trigger('click')
  expect(store.config.imagegen_style_prefix).toBe('cinematic grounded fantasy art')
  expect(mocks.api.mock.calls.some(([path]) => path === '/config')).toBe(false)
  wrapper.unmount()
})

it('shows the MiniMax budget and warns when static configuration uses over half', () => {
  const { wrapper } = setup({
    ai_providers: [{ id: 'minimax', name: 'MiniMax', base_url: 'https://api.minimax.cn/v1', api_format: 'openai', models: ['image-01'] }],
    imagegen_enabled: true,
    imagegen_provider_ref: 'minimax',
    imagegen_model: 'image-01',
    imagegen_style_prefix: 'x'.repeat(800),
    imagegen_auto_use_manual_prompt: true,
  })

  expect(wrapper.get('.imagegen-budget').text()).toContain('1500')
  expect(wrapper.get('.imagegen-budget').classes()).toContain('warning')
  wrapper.unmount()
})
