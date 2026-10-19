import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import ModuleForkDialog from '../src/features/modules/resources/ModuleForkDialog.vue'
import { i18n } from '../src/i18n'
const mocks = vi.hoisted(() => ({ preview: vi.fn(), review: vi.fn(), commit: vi.fn() }))
vi.mock('../src/api/moduleResources', async original => ({ ...await original<typeof import('../src/api/moduleResources')>(), resourceApi: mocks }))
const selector = { origin: 'contribution', kind: 'character_template', key: 'hero' }
const payload = () => ({ ok: true, target: 'character_template', blockers: [], plan_digest: 'sha256:review', commit_plan: { operations: [{ action: 'create', draft_ref: { kind: 'character_template', id: 'copy' } }] }, draft: { selector, copy_id: 'a'.repeat(32), source_digest: 'sha256:source', package_digest: 'sha256:package', language: 'zh-CN', payload: { character_name: 'Hero copy', background: 'Original background' } } })
const open = () => mount(ModuleForkDialog, { props: { moduleId: 'castle', selector }, global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /></div>' } } } })
beforeEach(() => { vi.resetAllMocks(); i18n.global.locale.value = 'zh-CN'; mocks.preview.mockResolvedValue(payload()); mocks.review.mockImplementation(async (_id, draft) => ({ ...payload(), draft: JSON.parse(JSON.stringify(draft)) })); mocks.commit.mockResolvedValue({ ok: true, result: {} }) })
it('saves an edited copy only after review and explicit confirmation', async () => {
  const wrapper = open(); await flushPromises()
  await wrapper.get('[data-testid=fork-text]').setValue('Edited background')
  await wrapper.get('[data-testid=fork-reviewed]').setValue(true)
  expect(wrapper.get('[data-testid=fork-save]').attributes('disabled')).toBeDefined()
  await wrapper.get('[data-testid=fork-review]').trigger('click'); await flushPromises()
  expect(mocks.review.mock.calls[0]?.[1].payload.background).toBe('Edited background')
  await wrapper.get('[data-testid=fork-reviewed]').setValue(true)
  await wrapper.get('[data-testid=fork-save]').trigger('click'); await flushPromises()
  expect(mocks.commit).toHaveBeenCalledWith('castle', expect.objectContaining({ payload: expect.objectContaining({ background: 'Edited background' }) }), 'sha256:review')
  expect(wrapper.emitted('saved')).toHaveLength(1)
})
it('blocks saving while advanced data edits have not been applied', async () => {
  const wrapper = open(); await flushPromises()
  await wrapper.get('[data-testid=fork-reviewed]').setValue(true)
  const advanced = wrapper.get('details textarea')
  await advanced.setValue('{"character_name":"Advanced copy","background":"Draft change"}')
  expect(wrapper.get('[data-testid=fork-save]').attributes('disabled')).toBeDefined()
})
it('does not retry an uncertain create and keeps review blockers visible', async () => {
  mocks.preview.mockResolvedValueOnce({ ...payload(), blockers: ['missing resource'] })
  const blocked = open(); await flushPromises(); await blocked.get('[data-testid=fork-reviewed]').setValue(true)
  expect(blocked.text()).toContain('missing resource'); expect(blocked.get('[data-testid=fork-save]').attributes('disabled')).toBeDefined()
  const wrapper = open(); await flushPromises(); await wrapper.get('[data-testid=fork-reviewed]').setValue(true)
  mocks.commit.mockRejectedValueOnce(new Error('Connection lost'))
  await wrapper.get('[data-testid=fork-save]').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('Connection lost'); expect(wrapper.text()).toContain('请先查看')
  expect(wrapper.get('[data-testid=fork-save]').attributes('disabled')).toBeDefined()
})
