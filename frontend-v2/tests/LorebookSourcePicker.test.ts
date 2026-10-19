import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LorebookSourcePicker from '../src/features/create/LorebookSourcePicker.vue'
import { i18n } from '../src/i18n'

const worlds = [
  { id: 'world:harbor', name: '雾港', language: '简体中文' },
  { id: 'world:forest', name: '雾港', language: '简体中文' },
]

describe('LorebookSourcePicker', () => {
  it('selects reference sources by canonical id even when display names match', async () => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = mount(LorebookSourcePicker, { props: { modelValue: '__builtin__', worlds }, global: { plugins: [i18n] } })
    expect(wrapper.findAll('option')).toHaveLength(3)
    await wrapper.get('[data-testid=lore-source-mode]').setValue('reference')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['copy:world:harbor'])
    await wrapper.setProps({ modelValue: 'copy:world:harbor' })
    await wrapper.get('[data-testid=lore-source-world]').setValue('world:forest')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['copy:world:forest'])
    await wrapper.setProps({ modelValue: 'copy:world:forest' })
    expect((wrapper.get('[data-testid=lore-source-world]').element as HTMLSelectElement).value).toBe('world:forest')
    await wrapper.get('[data-testid=lore-source-mode]').setValue('__blank__')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['__blank__'])
    await wrapper.setProps({ modelValue: '__blank__' })
    expect(wrapper.find('[data-testid=lore-source-world]').exists()).toBe(false)
    await wrapper.get('[data-testid=lore-source-mode]').setValue('__builtin__')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['__builtin__'])
    wrapper.unmount()
  })

  it('does not manufacture a reference when no source world is available', async () => {
    const wrapper = mount(LorebookSourcePicker, { props: { modelValue: '__builtin__', worlds: [] }, global: { plugins: [i18n] } })
    expect(wrapper.get('option[value=reference]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid=lore-source-mode]').setValue('reference')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.unmount()
  })
})
