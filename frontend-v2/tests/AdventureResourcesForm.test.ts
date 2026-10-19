import { flushPromises, mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import AdventureResourcesForm from '../src/features/adventures/AdventureResourcesForm.vue'
const files = () => ({ 'manifest.json': { adventure_id: 'user:quest' }, 'adventure.json': { id: 'quest', source_ref: 'user:quest', chapters: [], nodes: [], start_node_ids: [] }, 'content/npc/guard.json': { schema_version: 1, kind: 'npc', id: 'guard', source_ref: 'user:quest', automation_level: 'reference', name: 'Guard', description: 'A keeper' } })
it('edits native resource prose and keeps source identity independent from its name', async () => {
  const data = files()
  const wrapper = mount(AdventureResourcesForm, { props: { files: data }, global: { plugins: [i18n] } })
  await wrapper.get('[data-testid=resource-edit]').trigger('click')
  await wrapper.get('[data-testid=resource-name]').setValue('Edited keeper')
  await wrapper.get('[data-testid=resource-description]').setValue('Edited prose')
  expect(data['content/npc/guard.json']).toMatchObject({ id: 'guard', name: 'Edited keeper', description: 'Edited prose' })
})
it('adds a typed native resource and validates full JSON edits without replacing the document on error', async () => {
  const data = files()
  const wrapper = mount(AdventureResourcesForm, { props: { files: data }, global: { plugins: [i18n] } })
  await wrapper.get('[data-testid=resource-kind]').setValue('item')
  await wrapper.get('[data-testid=resource-add]').trigger('click')
  expect(Object.values(data).some(value => 'kind' in value && value.kind === 'item')).toBe(true)
  await wrapper.get('[data-testid=resource-json]').setValue('[]')
  await wrapper.get('[data-testid=resource-json-apply]').trigger('click'); await flushPromises()
  expect(wrapper.find('[role=alert]').exists()).toBe(true)
  expect(Object.values(data).some(value => 'kind' in value && value.kind === 'item')).toBe(true)
})
