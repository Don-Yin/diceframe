import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import ContentTextReviewDialog from '../src/features/content-review/ContentTextReviewDialog.vue'
import { i18n } from '../src/i18n'
const mocks = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/client', async original => ({ ...await original<typeof import('../src/api/client')>(), api: mocks.api }))
const payload = () => ({ ok: true, plan_digest: 'sha256:test', blockers: [], commit_plan: { operations: [{ action: 'create', draft_ref: { kind: 'lorebook', id: 'part_1' } }] },
  draft: { source_id: 'text-source', filename: 'notes.md', language: 'zh-CN', items: [{ id: 'part_1', name: '港口', text: '浓雾', target: 'lorebook', references: [] }] } })
beforeEach(() => { i18n.global.locale.value = 'zh-CN'; mocks.api.mockReset(); mocks.api.mockResolvedValue(payload()) })
const open = () => mount(ContentTextReviewDialog, { global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /></div>' } } } })
async function preview(wrapper: ReturnType<typeof open>) {
  await wrapper.get('[data-testid=text-source]').setValue('# 港口\n浓雾')
  await wrapper.get('[data-testid=text-preview]').trigger('click'); await flushPromises()
}
it('edits fragment destination and prose, requiring review of the changed draft', async () => {
  const wrapper = open(); await preview(wrapper)
  await wrapper.get('[data-testid=fragment-target]').setValue('character_template')
  await wrapper.get('[data-testid=fragment-text]').setValue('修改后的背景')
  await wrapper.get('[data-testid=text-reviewed]').setValue(true)
  expect(wrapper.get('[data-testid=text-commit]').attributes('disabled')).toBeDefined()
  mocks.api.mockImplementationOnce(async (_url, options) => ({ ...payload(), draft: JSON.parse(options.body) }))
  await wrapper.get('[data-testid=text-validate]').trigger('click'); await flushPromises()
  expect(JSON.parse(mocks.api.mock.calls.at(-1)?.[1].body).items[0]).toMatchObject({ target: 'character_template', text: '修改后的背景' })
  await wrapper.get('[data-testid=text-reviewed]').setValue(true)
  expect(wrapper.get('[data-testid=text-commit]').attributes('disabled')).toBeUndefined()
})
it('keeps the original reviewed request locked for retry after a partial failure', async () => {
  const wrapper = open(); await preview(wrapper)
  await wrapper.get('[data-testid=text-reviewed]').setValue(true)
  mocks.api.mockResolvedValueOnce({ ok: false, partial: true, results: [{ id: 'part_1', target: 'lorebook', ok: false, error: 'disk full' }] })
  await wrapper.get('[data-testid=text-commit]').trigger('click'); await flushPromises()
  const original = mocks.api.mock.calls.at(-1)?.[1].body
  expect(wrapper.text()).toContain('disk full')
  expect(wrapper.get('[data-testid=fragment-text]').attributes('disabled')).toBeDefined()
  mocks.api.mockResolvedValueOnce({ ok: true, results: [{ id: 'part_1', target: 'lorebook', ok: true, result: { book_id: 'saved' } }] })
  await wrapper.get('[data-testid=text-commit]').trigger('click'); await flushPromises()
  expect(mocks.api.mock.calls.at(-1)?.[1].body).toBe(original)
  expect(wrapper.emitted('saved')).toHaveLength(1)
})
it('requires inspection after a successful resource write with an unavailable receipt', async () => {
  const wrapper = open(); await preview(wrapper)
  await wrapper.get('[data-testid=text-reviewed]').setValue(true)
  mocks.api.mockResolvedValueOnce({ ok: false, recovery_required: true, error: 'Inspect saved library', results: [{ id: 'part_1', target: 'lorebook', ok: true }] })
  await wrapper.get('[data-testid=text-commit]').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('Inspect saved library')
  expect(wrapper.get('[data-testid=text-commit]').attributes('disabled')).toBeDefined()
  expect(wrapper.emitted('saved')).toBeUndefined()
})
