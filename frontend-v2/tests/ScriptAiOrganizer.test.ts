import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import type { ScriptDraft, ScriptPreview } from '../src/features/adventures/scriptTypes'

const mocks = vi.hoisted(() => ({ organize: vi.fn() }))
vi.mock('../src/features/adventures/scriptAi', () => ({ organizeScript: mocks.organize }))
import ScriptAiOrganizer from '../src/features/adventures/ScriptAiOrganizer.vue'

function source(): ScriptDraft {
  return { directory_id: 'demo', references: [], files: {
    'manifest.json': { adventure_id: 'user:demo', version: '1.0.0', world_policy: 'portable', recommended_world_id: '' },
    'adventure.json': { id: 'demo', name: 'Original', start_node_ids: ['a'], chapters: [], nodes: [{ id: 'a', type: 'scene', name: 'Page 1', description: 'Original text', transitions: [] }] },
  } }
}
function result(): ScriptPreview {
  const draft = source()
  draft.files['adventure.json'].nodes[0].name = 'AI scene'
  return { ok: true, draft, warnings: [], blockers: [], plan_digest: 'digest', commit_plan: {} }
}
function render() {
  return mount(ScriptAiOrganizer, { props: { draft: source() }, global: { plugins: [i18n] } })
}
async function start(wrapper: ReturnType<typeof render>) {
  await wrapper.get('[data-testid=script-ai-consent]').setValue(true)
  await wrapper.get('[data-testid=script-ai-start]').trigger('click')
}

describe('AI import organization', () => {
  beforeEach(() => { i18n.global.locale.value = 'zh-CN'; mocks.organize.mockReset(); mocks.organize.mockResolvedValue(result()) })

  it('requires token consent, previews the result, and applies only when requested', async () => {
    const wrapper = render()
    expect(wrapper.text()).toContain('消耗模型 token')
    expect(wrapper.text()).toContain('取消前已产生的用量仍可能计费')
    expect(wrapper.get('[data-testid=script-ai-start]').attributes('disabled')).toBeDefined()
    expect(mocks.organize).not.toHaveBeenCalled()
    await start(wrapper)
    await flushPromises()
    expect(wrapper.text()).toContain('AI scene')
    expect(wrapper.props('draft').files['adventure.json'].name).toBe('Original')
    expect(wrapper.emitted('apply')).toBeUndefined()
    await wrapper.get('[data-testid=script-ai-apply]').trigger('click')
    expect(wrapper.emitted('apply')?.[0][0]).toEqual(result())
    wrapper.unmount()
  })

  it('shows actual work progress and ignores late results after cancellation', async () => {
    let resolve!: (value: ScriptPreview) => void
    mocks.organize.mockImplementationOnce((_draft, _instructions, _language, _signal, progress) => {
      progress({ stage: 'organizing', completed: 1, total: 4, current: 2, chunks: 2 })
      return new Promise(done => { resolve = done })
    })
    const wrapper = render()
    await start(wrapper)
    expect(wrapper.get('progress').attributes('value')).toBe('1')
    expect(wrapper.get('progress').attributes('max')).toBe('4')
    expect(wrapper.text()).toContain('正在整理第 2 / 2 段')
    const signal = mocks.organize.mock.calls[0][3] as AbortSignal
    await wrapper.get('[data-testid=script-ai-cancel]').trigger('click')
    expect(signal.aborted).toBe(true)
    expect(wrapper.text()).toContain('已取消，原草稿未被替换')
    resolve(result())
    await flushPromises()
    expect(wrapper.find('[data-testid=script-ai-apply]').exists()).toBe(false)
    expect(wrapper.emitted('apply')).toBeUndefined()
    wrapper.unmount()
  })

  it('aborts the request when the import dialog closes', async () => {
    mocks.organize.mockImplementationOnce(() => new Promise(() => {}))
    const wrapper = render()
    await start(wrapper)
    const signal = mocks.organize.mock.calls[0][3] as AbortSignal
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
  })

  it('keeps the original draft after a model or validation error', async () => {
    mocks.organize.mockRejectedValueOnce(new Error('AI returned invalid JSON'))
    const wrapper = render()
    await start(wrapper)
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('AI returned invalid JSON')
    expect(wrapper.props('draft').files['adventure.json'].name).toBe('Original')
    expect(wrapper.find('[data-testid=script-ai-apply]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not apply an AI result over later manual edits', async () => {
    const wrapper = render()
    await start(wrapper)
    await flushPromises()
    const changed = source()
    changed.files['adventure.json'].nodes[0].description = 'Later manual edit'
    await wrapper.setProps({ draft: changed })
    expect(wrapper.text()).toContain('原草稿已改变')
    expect(wrapper.get('[data-testid=script-ai-apply]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid=script-ai-apply]').trigger('click')
    expect(wrapper.emitted('apply')).toBeUndefined()
    wrapper.unmount()
  })
})
