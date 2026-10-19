import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import ChoiceEditor from '../src/features/adventures/ChoiceEditor.vue'
import AdventureNodeActions from '../src/features/adventures/AdventureNodeActions.vue'

it('upgrades branch semantics explicitly, preserving condition identity and stable choice ids during label edits', async () => {
  const node = { id: 'gate', type: 'scene', choice_mode: undefined as string | undefined, transitions: [{ to: 'bridge', conditions: [{ type: 'world.fact_equals', key: 'key', value: true }], choice_id: undefined as string | undefined, choice_label: undefined as string | undefined }] }
  const wrapper = mount(ChoiceEditor, { props: { node }, global: { plugins: [i18n] } })
  await wrapper.get('[data-testid=graph-choice-mode]').setValue('exclusive')
  const id = node.transitions[0]!.choice_id
  expect(id).toMatch(/^choice_/); expect(wrapper.emitted('upgrade')).toEqual([[]])
  await wrapper.get('[data-testid=graph-choice-label]').setValue('Cross safely')
  expect(node.transitions[0]!.choice_id).toBe(id)
  expect(node.transitions[0]!.conditions[0]!.value).toBe(true)
  await wrapper.get('[data-testid=graph-choice-mode]').setValue('parallel')
  expect(node.transitions[0]!.choice_id).toBeUndefined()
})

it('offers player proposals and GM confirmation while a resolved node has no active buttons', async () => {
  const node = { id: 'gate', choice_mode: 'exclusive', transitions: [{ choice_id: 'bridge', choice_label: 'Cross bridge' }] }
  const wrapper = mount(AdventureNodeActions, { props: { node, isGm: false, active: true, busy: false }, global: { plugins: [i18n] } })
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('submit')).toEqual([['bridge']])
  expect(wrapper.get('button').text()).toContain('Propose')
  await wrapper.setProps({ isGm: true })
  expect(wrapper.get('button').text()).toContain('Confirm')
  await wrapper.setProps({ active: false, selected: 'bridge' })
  expect(wrapper.find('button').exists()).toBe(false)
  expect(wrapper.text()).toContain('Cross bridge')
})
