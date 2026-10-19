import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScriptImportDialog from '../src/features/adventures/ScriptImportDialog.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/client', async original => ({ ...await original<typeof import('../src/api/client')>(), api: mocks.api }))

function payload(blockers: string[] = []) {
  return { ok: true, plan_digest: 'sha256:test', blockers, warnings: ['scriptDefaultGm'],
    commit_plan: { unresolved_references: blockers.length ? [{ kind: 'npc', id: 'guard' }] : [] },
    draft: { directory_id: 'demo', references: blockers.length ? [{ kind: 'npc', id: 'guard' }] : [], files: {
      'manifest.json': { adventure_id: 'user:demo', version: '1.0.0', world_policy: 'portable', recommended_world_id: '' },
      'adventure.json': { id: 'demo', name: '雾港', start_node_ids: ['a'], chapters: [{ id: 'ch', name: '开场' }], nodes: [{ id: 'a', chapter_id: 'ch', type: 'scene', name: '抵达', description: '原文', visibility: 'gm', transitions: [] }] },
    } },
  }
}

async function upload(wrapper: ReturnType<typeof mount>) {
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['# 雾港'], 'demo.md')] })
  await input.trigger('change')
  await wrapper.get('[data-testid=script-preview]').trigger('click')
  await flushPromises()
}

describe('script review and publish interaction', () => {
  beforeEach(() => { i18n.global.locale.value = 'zh-CN'; mocks.api.mockReset(); mocks.api.mockResolvedValue(payload()) })

  it('opens a prepared story plan in the same editable review flow without publishing it', async () => {
    const wrapper = mount(ScriptImportDialog, { props: { initialPreview: payload() as any }, global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /></div>' } } } })
    expect(wrapper.find('[data-testid=graph-name]').exists()).toBe(true)
    expect(wrapper.get('[data-testid=script-publish]').attributes('disabled')).toBeDefined()
    expect(mocks.api).not.toHaveBeenCalled()
    await wrapper.get('[data-testid=script-reviewed]').setValue(true)
    expect(wrapper.get('[data-testid=script-publish]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('requires explicit review and another validation after an edit', async () => {
    const wrapper = mount(ScriptImportDialog, { global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /></div>' } } } })
    await upload(wrapper)
    expect(wrapper.find('.script-safety-callout').text()).toContain('导入的场景默认仅 GM 可见')
    expect(wrapper.find('.script-safety-callout').text()).toContain('不会自动生成战斗、伤害或奖励')
    expect(wrapper.find('[data-testid="review-plan"]').exists()).toBe(true)
    expect((wrapper.get('[data-testid=graph-name]').element as HTMLInputElement).value).toBe('雾港')
    const publish = wrapper.get('[data-testid=script-publish]')
    const status = () => wrapper.get('[data-testid=script-publish-status]').text()
    expect(publish.attributes('disabled')).toBeDefined()
    expect(status()).toContain('请勾选“我已检查内容、分支、规则需求和 GM 私密信息”')
    expect(publish.attributes('aria-describedby')).toBe(wrapper.get('[data-testid=script-publish-status]').attributes('id'))
    await wrapper.get('[data-testid=script-reviewed]').setValue(true)
    expect(publish.attributes('disabled')).toBeUndefined()
    expect(status()).toContain('检查已通过，可以保存到你的冒险库')
    await wrapper.get('[data-testid=graph-node-description]').setValue('修改后的场景')
    expect(publish.attributes('disabled')).toBeDefined()
    expect(status()).toContain('请点击“重新校验”')
    mocks.api.mockImplementationOnce(async (_url, options) => ({ ...payload(), draft: JSON.parse(options.body) }))
    await wrapper.get('[data-testid=script-validate]').trigger('click')
    await flushPromises()
    expect(status()).toContain('请勾选')
    expect(mocks.api.mock.calls.at(-1)?.[0]).toBe('/adventures/script/review')
    expect(JSON.parse(mocks.api.mock.calls.at(-1)?.[1].body).files['adventure.json'].nodes[0].description).toBe('修改后的场景')
    mocks.api.mockResolvedValue({ ok: true, adventure_id: 'user:demo' })
    await wrapper.get('[data-testid=script-reviewed]').setValue(true)
    await publish.trigger('click')
    await flushPromises()
    expect(JSON.parse(mocks.api.mock.calls.at(-1)?.[1].body)).toMatchObject({ reviewed: true, plan_digest: 'sha256:test', files: { 'adventure.json': { nodes: [{ description: '修改后的场景' }] } } })
    expect(wrapper.emitted('published')?.[0]).toEqual(['user:demo'])
  })

  it('shows unresolved refs and blocks publishing until they are handled', async () => {
    mocks.api.mockResolvedValue(payload(['scriptUnresolvedReferences']))
    const wrapper = mount(ScriptImportDialog, { global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /></div>' } } } })
    await upload(wrapper)
    expect(wrapper.text()).toContain('npc:guard')
    await wrapper.get('[data-testid=script-reviewed]').setValue(true)
    expect(wrapper.get('[data-testid=script-publish]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid=script-publish-status]').text()).toContain('尚有未解析的资源引用')
    await wrapper.get('[data-testid=script-reference-prose]').trigger('click')
    expect(wrapper.get('[data-testid=script-publish]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid=script-publish-status]').text()).toContain('请点击“重新校验”')
    expect(wrapper.get('[data-testid=script-publish-status]').text()).not.toContain('尚有未解析的资源引用')
  })

  it('explains pending resource edits before another validation can run', async () => {
    const wrapper = mount(ScriptImportDialog, { global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /></div>' } } } })
    await upload(wrapper)
    await wrapper.get('[data-testid=resource-add]').trigger('click')
    await wrapper.get('[data-testid=resource-json]').setValue('{unfinished')
    await wrapper.get('[data-testid=script-reviewed]').setValue(true)
    expect(wrapper.get('[data-testid=script-publish-status]').text()).toContain('资源数据有未应用的编辑，或条件值格式有误')
    expect(wrapper.get('[data-testid=script-publish]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid=script-validate]').attributes('disabled')).toBeDefined()
  })

  it('explains why publishing is disabled while validation is running', async () => {
    const wrapper = mount(ScriptImportDialog, { global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /></div>' } } } })
    await upload(wrapper)
    await wrapper.get('[data-testid=script-reviewed]').setValue(true)
    let resolve!: (value: ReturnType<typeof payload>) => void
    mocks.api.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    await wrapper.get('[data-testid=script-validate]').trigger('click')
    expect(wrapper.get('[data-testid=script-publish-status]').text()).toContain('正在处理，请稍候')
    expect(wrapper.get('[data-testid=script-publish]').attributes('disabled')).toBeDefined()
    resolve(payload())
    await flushPromises()
    expect(wrapper.get('[data-testid=script-publish-status]').text()).toContain('请勾选')
    expect(wrapper.get('[data-testid=script-publish-status]').text()).not.toContain('正在处理')
  })
})
