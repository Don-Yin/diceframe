import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import RuleResourcesEditor from '../src/features/admin/RuleResourcesEditor.vue'
import type { RuleSpecialStat } from '../src/api/types'

it('edits resources without losing opaque metadata and permits clearing the initial override', async () => {
  i18n.global.locale.value = 'zh-CN'
  const original: RuleSpecialStat[] = [{ key: 'mp', name: '魔力', max: 20, initial: 15, aliases: ['Mana'], triggers: [{ type: 'custom' }] }]
  const wrapper = mount(RuleResourcesEditor, { props: { modelValue: original }, global: { plugins: [i18n] } })
  await wrapper.findAll('input')[2]!.setValue(30)
  const next = wrapper.emitted('update:modelValue')![0]![0] as RuleSpecialStat[]
  expect(next[0]).toEqual({ ...original[0], max: 30 })
  expect(original[0]!.max).toBe(20)
  await wrapper.setProps({ modelValue: next })
  await wrapper.findAll('input')[3]!.setValue('')
  const cleared = wrapper.emitted('update:modelValue')![1]![0] as RuleSpecialStat[]
  expect(cleared[0]).not.toHaveProperty('initial')
  expect(cleared[0]!.triggers).toEqual(original[0]!.triggers)
  wrapper.unmount()
})
