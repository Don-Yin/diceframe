import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'
import { NInputNumber, NSwitch } from 'naive-ui'
import { i18n } from '../src/i18n'
import { useSettingsStore } from '../src/stores/useSettingsStore'
import GenerationTuning from '../src/features/admin/settings/GenerationTuning.vue'
import GenerationSettings from '../src/features/admin/settings/GenerationSettings.vue'
import CheckModelSettings from '../src/features/admin/settings/CheckModelSettings.vue'

vi.mock('../src/composables/useToast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
beforeEach(() => { setActivePinia(createPinia()); i18n.global.locale.value = 'zh-CN' })

it('clears explicit overrides to feature defaults and saves only its settings', async () => {
  const store = useSettingsStore()
  store.config = { llm_generation_options: { temperature: .6, top_p: .8 }, context_recent_rounds: 0 }
  const save = vi.spyOn(store, 'saveSection').mockResolvedValue([])
  const wrapper = mount(GenerationTuning, { global: { plugins: [i18n] } })
  const numbers = wrapper.findAllComponents(NInputNumber)
  numbers[0]!.vm.$emit('update:value', null)
  expect(store.config.llm_generation_options).toEqual({ top_p: .8 })
  numbers[4]!.vm.$emit('update:value', 10)
  await wrapper.get('footer button').trigger('click')
  await flushPromises()
  expect(save).toHaveBeenCalledWith(['llm_generation_options', 'context_recent_rounds'])
  expect(store.config.context_recent_rounds).toBe(10)
  wrapper.unmount()
})

it('uses only saved chat models and clears a stale model when changing providers', async () => {
  const store = useSettingsStore()
  store.config = { ai_providers: [{ id: 'local', name: 'Local', base_url: 'http://localhost:8000/v1', api_format: 'openai', models: ['chat', 'image-model'], model_capabilities: { chat: 'chat', 'image-model': 'image' } }], check_model_enabled: false, check_model: 'stale' }
  const wrapper = mount(CheckModelSettings, { global: { plugins: [i18n] } })
  wrapper.getComponent(NSwitch).vm.$emit('update:value', true)
  await wrapper.vm.$nextTick()
  await wrapper.findAll('select')[0]!.setValue('local')
  expect(store.config.check_model).toBe('')
  expect(wrapper.findAll('select')[1]!.find('option[value="image-model"]').exists()).toBe(false)
  await wrapper.findAll('select')[1]!.setValue('chat')
  expect(store.config.check_provider_ref).toBe('local')
  expect(store.config.check_model).toBe('chat')
  expect(store.config.check_model_enabled).toBe(true)
  wrapper.unmount()
})

it('saves the folded advanced generation group together while keeping the Agent budget separate', async () => {
  const store = useSettingsStore()
  store.config = { llm_generation_options: { temperature: .6 }, context_recent_rounds: 10, assistant_agent_max_tokens: 8192, text_gen_max_tokens: 4096 }
  const save = vi.spyOn(store, 'saveSection').mockResolvedValue([])
  const wrapper = mount(GenerationSettings, { global: { plugins: [i18n] } })
  expect(wrapper.get('details').attributes('open')).toBeUndefined()
  expect(wrapper.findAll('footer button')).toHaveLength(1)
  wrapper.findAllComponents(NInputNumber)[0]!.vm.$emit('update:value', .8)
  wrapper.get('#settings-text_gen_max_tokens').getComponent(NInputNumber).vm.$emit('update:value', 6144)
  await wrapper.get('footer button').trigger('click')
  await flushPromises()
  expect(save).toHaveBeenCalledWith(['llm_generation_options', 'context_recent_rounds', 'model_request_timeout_seconds', 'narrative_max_tokens', 'character_gen_max_tokens', 'summary_max_tokens', 'brief_max_tokens', 'analysis_max_tokens', 'text_gen_max_tokens'])
  expect(store.config.llm_generation_options).toEqual({ temperature: .8 })
  expect(store.config.text_gen_max_tokens).toBe(6144)
  expect(store.config.assistant_agent_max_tokens).toBe(8192)
  wrapper.unmount()
})
