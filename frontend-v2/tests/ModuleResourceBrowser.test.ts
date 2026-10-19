import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import ModuleResourceBrowser from '../src/features/modules/resources/ModuleResourceBrowser.vue'
import { i18n } from '../src/i18n'
const mocks = vi.hoisted(() => ({ list: vi.fn(), read: vi.fn() }))
vi.mock('../src/api/moduleResources', async original => ({ ...await original<typeof import('../src/api/moduleResources')>(), resourceApi: mocks }))
const row = { kind: 'npc', title: 'Himmel', description: '守门人', selector: { origin: 'contribution', kind: 'npc', key: 'himmel' } }
beforeEach(() => {
  i18n.global.locale.value = 'zh-CN'; mocks.list.mockReset(); mocks.read.mockReset()
  mocks.list.mockResolvedValue({ ok: true, resources: [row] })
  mocks.read.mockResolvedValue({ ok: true, resource: { ...row, payload: { name: 'Himmel', description: '只读原始资料' }, fork_target: 'lorebook', source_digest: 'sha256:test' } })
})
it('browses installed resources and opens their native readonly content', async () => {
  const wrapper = mount(ModuleResourceBrowser, { props: { moduleId: 'castle' }, global: { plugins: [i18n] } })
  await flushPromises()
  await wrapper.get('[data-testid=resource-open]').trigger('click'); await flushPromises()
  expect(mocks.read).toHaveBeenCalledWith('castle', row.selector, 'zh-CN')
  expect(wrapper.text()).toContain('只读原始资料')
  expect(wrapper.get('[data-testid=resource-fork]').text()).toContain('副本')
  await wrapper.get('[data-testid=resource-search]').setValue('no match')
  expect(wrapper.findAll('[data-testid=resource-open]')).toHaveLength(0)
})
it('discards a resource response after switching modules', async () => {
  let finish!: (value: unknown) => void
  mocks.read.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const wrapper = mount(ModuleResourceBrowser, { props: { moduleId: 'castle' }, global: { plugins: [i18n] } })
  await flushPromises(); await wrapper.get('[data-testid=resource-open]').trigger('click')
  await wrapper.setProps({ moduleId: 'other' }); await flushPromises()
  finish({ ok: true, resource: { ...row, payload: { description: 'OLD GM SECRET' } } }); await flushPromises()
  expect(wrapper.text()).not.toContain('OLD GM SECRET')
})
it('uses translated kinds for discovery while reading with the canonical selector', async () => {
  const material = { ...row, kind: 'world_template', selector: { origin: 'contribution', kind: 'world_template', key: 'castle' } }
  mocks.list.mockResolvedValue({ ok: true, resources: [material] })
  const wrapper = mount(ModuleResourceBrowser, { props: { moduleId: 'castle' }, global: { plugins: [i18n] } })
  await flushPromises()
  await wrapper.get('[data-testid=resource-search]').setValue('世界模板')
  expect(wrapper.get('select option[value="world_template"]').text()).toBe('世界模板')
  await wrapper.get('select').setValue('world_template')
  await wrapper.get('[data-testid=resource-open]').trigger('click')
  await flushPromises()
  expect(mocks.read).toHaveBeenCalledWith('castle', material.selector, 'zh-CN')
})
