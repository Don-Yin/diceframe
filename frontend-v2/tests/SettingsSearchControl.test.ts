import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import SettingsSearch from '../src/features/admin/settings/SettingsSearch.vue'

vi.mock('../src/composables/useLocale', () => ({ useLocale: () => ({ locale: ref('zh-CN') }) }))

describe('settings search control', () => {
  it('selects with the keyboard and closes results without clearing the query', async () => {
    const wrapper = mount(SettingsSearch, { attachTo: document.body })
    const input = wrapper.get('input')
    await input.setValue('Token')
    const options = wrapper.findAll('[role="option"]')
    for (const option of options) (option.element as HTMLElement).scrollIntoView = vi.fn()
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ id: 'generation' })
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    expect((input.element as HTMLInputElement).value).toBe('Token')
    await input.trigger('keydown', { key: 'Escape' })
    expect((input.element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it('announces missing results and uses the active interface language', async () => {
    const wrapper = mount(SettingsSearch)
    await wrapper.get('input').setValue('no-such-setting')
    expect(wrapper.get('[role="status"]').text()).toBe('没有找到相关设置')
    await wrapper.get('input').setValue('API key')
    expect(wrapper.get('[role="option"] strong').text()).toBe('AI 服务商')
    await wrapper.get('[role="option"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ section: 'api' })
    wrapper.unmount()
  })
})
