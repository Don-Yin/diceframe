import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import GamePreferenceFields from '../src/features/game-preferences/GamePreferenceFields.vue'
import GameSessionPreferences from '../src/features/play/preferences/GameSessionPreferences.vue'
import GameDefaultsSettings from '../src/features/admin/settings/GameDefaultsSettings.vue'
import { defaultGamePreferences } from '../src/features/game-preferences/model'

const mocks = vi.hoisted(() => ({ api: vi.fn(), store: { config: {} as Record<string, unknown>, loading: false, setConfigField: vi.fn(), saveSection: vi.fn() } }))
vi.mock('../src/api/client', () => ({ api: mocks.api, errorMessage: (error: Error) => error.message }))
vi.mock('../src/composables/useLocale', () => ({ useLocale: () => ({ locale: ref('zh-CN') }) }))
vi.mock('../src/stores/useSettingsStore', () => ({ useSettingsStore: () => mocks.store }))

beforeEach(() => { mocks.api.mockReset(); mocks.store.setConfigField.mockReset(); mocks.store.saveSection.mockReset(); mocks.store.config = {} })

describe('game preferences', () => {
  it('does not submit the new visibility preference to a backend that does not advertise it', async () => {
    const older = { ...defaultGamePreferences() } as Partial<ReturnType<typeof defaultGamePreferences>>
    delete older.quick_actions_enabled
    mocks.api.mockResolvedValue({ ok: true, push_supported: true, preferences: older })
    const wrapper = shallowMount(GameSessionPreferences, { props: { gameKey: 'web|table|bot', revision: 0, section: 'actions' } })
    await flushPromises()
    const fields = wrapper.findComponent(GamePreferenceFields)
    expect(fields.props('quickActionsSupported')).toBe(false)
    fields.vm.$emit('update', { quick_actions_enabled: false })
    await flushPromises()
    expect(mocks.api.mock.calls.filter(([, options]) => options?.method === 'POST')).toEqual([])
    expect(wrapper.text()).not.toContain('unknown game preference fields')
    wrapper.unmount()
  })

  it('explains the server restart instead of offering an unsupported switch', () => {
    const wrapper = mount(GamePreferenceFields, { props: { value: defaultGamePreferences(), scope: 'actions', quickActionsSupported: false } })
    expect(wrapper.findComponent({ name: 'Switch' }).props('disabled')).toBe(true)
    expect(wrapper.text()).toContain('重启服务')
    wrapper.unmount()
  })

  it('can save existing defaults without injecting an unsupported visibility field', async () => {
    const older = { ...defaultGamePreferences() } as Partial<ReturnType<typeof defaultGamePreferences>>
    delete older.quick_actions_enabled
    mocks.store.config.game_defaults = older
    mocks.store.saveSection.mockResolvedValue(undefined)
    const wrapper = mount(GameDefaultsSettings)
    await wrapper.get('[data-testid="save-game-defaults"]').trigger('click')
    await flushPromises()
    const saved = mocks.store.setConfigField.mock.calls.at(-1)
    expect(saved).toEqual(['game_defaults', older])
    expect(saved![1]).not.toHaveProperty('quick_actions_enabled')
    expect(mocks.store.saveSection).toHaveBeenCalledWith(['game_defaults'])
    wrapper.unmount()
  })
  it('uses the same padded card groups and row primitives as General settings', () => {
    const wrapper = shallowMount(GamePreferenceFields, { props: { value: defaultGamePreferences(), settingsLayout: true } })
    expect(wrapper.findAll('.advanced-section')).toHaveLength(4)
    expect(wrapper.findAll('.advanced-section-head')).toHaveLength(4)
    expect(wrapper.findAll('.advanced-row').length).toBeGreaterThanOrEqual(8)
    expect(wrapper.findAll('.preference-row')).toHaveLength(0)
  })
  it('shows the enabled Push default but hides it for an unsupported ruleset', async () => {
    const wrapper = shallowMount(GamePreferenceFields, { props: { value: defaultGamePreferences() } })
    expect(wrapper.findComponent({ name: 'Switch' }).exists()).toBe(true)
    expect(wrapper.text()).toContain('允许孤注一掷')
    await wrapper.setProps({ pushSupported: false, scope: 'checks' })
    expect(wrapper.text()).not.toContain('允许孤注一掷')
    expect(wrapper.text()).not.toContain('成长偏好')
    expect(wrapper.text()).toContain('骰子揭示方式')
  })

  it('emits only the changed preference and preserves world-following as null', async () => {
    const original = defaultGamePreferences()
    const wrapper = mount(GamePreferenceFields, { props: { value: original } })
    const style = wrapper.findAll('select').find(select => select.find('option[value="world"]').exists())!
    await style.setValue('custom')
    expect(wrapper.emitted('update')?.at(-1)).toEqual([{ gm_style_override: {} }])
    await style.setValue('world')
    expect(wrapper.emitted('update')?.at(-1)).toEqual([{ gm_style_override: null }])
    expect(original).toEqual(defaultGamePreferences())
  })

  it('updates a controlled switch immediately and rolls back a rejected save', async () => {
    let rejectSave!: (reason: Error) => void
    mocks.api.mockResolvedValueOnce({ ok: true, push_supported: true, preferences: defaultGamePreferences() })
    mocks.api.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectSave = reject }))
    const wrapper = shallowMount(GameSessionPreferences, { props: { gameKey: 'web|table|bot', revision: 0 } })
    await flushPromises()
    const fields = wrapper.findComponent(GamePreferenceFields)
    fields.vm.$emit('update', { push_enabled: false })
    await wrapper.vm.$nextTick()
    expect(fields.props('value').push_enabled).toBe(false)
    expect(fields.props('disabled')).toBe(true)
    rejectSave(new Error('Save failed'))
    await flushPromises()
    expect(fields.props('value').push_enabled).toBe(true)
    expect(fields.props('disabled')).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('Save failed')
  })
})
