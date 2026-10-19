import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import AdventureGraphForm from '../src/features/adventures/AdventureGraphForm.vue'
import GateEditor from '../src/features/adventures/GateEditor.vue'

it('offers narrative conditions and reference resources for a neutral profile', () => {
  const files = { 'manifest.json': { adventure_id: 'user:story', required_runtime: { id: 'core:adventure', minimum_version: 1 }, version: '1.0.0', world_policy: 'agnostic', recommended_world_id: '' }, 'adventure.json': { id: 'story', name: 'Story', chapters: [], start_node_ids: ['one'], nodes: [{ id: 'one', type: 'scene', transitions: [{ to: 'one', conditions: [{ type: 'world.fact_equals', key: 'door', value: true }] }] }] } }
  const wrapper = mount(AdventureGraphForm, { props: { files }, global: { plugins: [i18n] } })
  expect(wrapper.text()).toMatch(/通用剧情|Universal story/)
  expect(wrapper.findAll('.gate-row option').map(option => option.text())).not.toContain('rules.outcome')
  expect(wrapper.find('[data-testid=graph-encounter-ref]').exists()).toBe(false)
  expect(wrapper.get('[data-testid=resource-kind]').findAll('option').map(option => option.attributes('value'))).not.toContain('encounter_catalog')
  wrapper.unmount()
})

it('retains invalid gate text and blocks review until every edited value is valid or removed', async () => {
  const transition = { conditions: [{ type: 'world.fact_equals', key: 'door', value: true }, { type: 'world.fact_equals', key: 'key', value: false }] }
  const wrapper = mount(GateEditor, { props: { transition }, global: { plugins: [i18n] } })
  const values = () => wrapper.findAll('.gate-row input').filter(input => input.attributes('type') !== 'hidden').filter((_, index) => index % 2 === 1)
  await values()[0]!.setValue('broken JSON')
  await values()[1]!.setValue('true')
  expect((values()[0]!.element as HTMLInputElement).value).toBe('broken JSON')
  expect(wrapper.emitted('pending')?.at(-1)).toEqual([true])
  expect(transition.conditions[0]!.value).toBe(true)
  await wrapper.findAll('.gate-row button')[0]!.trigger('click')
  expect(wrapper.emitted('pending')?.at(-1)).toEqual([false])
})

it('connects only empty ordinary scene branches after an explicit author action', async () => {
  const files = { 'manifest.json': { adventure_id: 'user:pages', recommended_world_id: '', version: '1.0.0', world_policy: 'portable' }, 'adventure.json': { id: 'pages', schema_version: 1, name: 'Pages', chapters: [], start_node_ids: ['one'], nodes: [{ id: 'one', name: 'One', type: 'scene', transitions: [] }, { id: 'note', name: 'Note', type: 'reference', transitions: [] }, { id: 'two', name: 'Two', type: 'scene', transitions: [{ to: 'one' }] }, { id: 'three', name: 'Three', type: 'scene', transitions: [] }] } }
  const wrapper = mount(AdventureGraphForm, { props: { files }, global: { plugins: [i18n] } })
  await wrapper.get('[data-testid=graph-connect-order]').trigger('click')
  expect(files['adventure.json'].nodes.map(node => node.transitions)).toEqual([[{ to: 'two' }], [], [{ to: 'one' }], []])
})
