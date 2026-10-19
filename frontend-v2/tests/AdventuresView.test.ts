import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AdventuresView from '../src/features/admin/AdventuresView.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  apiBlob: vi.fn(),
  route: { query: {} as Record<string, string> },
  router: { replace: vi.fn().mockResolvedValue(undefined) },
}))

vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api, apiBlob: mocks.apiBlob }
})
vi.mock('../src/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => mocks.router,
}))

const packages = {
  ok: true,
  adventures: [
    {
      adventure_id: 'core:lanterns_of_greymoor', directory_id: 'lanterns_of_greymoor',
      name: '灰沼失灯记', summary: '内置短冒险', version: '1.0.0',
      format: 'diceframe:adventure-graph-v1', world_policy: 'portable',
      recommended_world_id: 'greymoor', compatibility: 'compatible',
      incompatibility_reasons: [], custom: false, editable: false, in_use: 0,
    },
    {
      adventure_id: 'user:bound_story', directory_id: 'bound_story',
      name: '长期战役', summary: '正在使用', version: '1.2.0',
      format: 'diceframe:adventure-graph-v1', world_policy: 'agnostic',
      recommended_world_id: '', compatibility: 'compatible',
      incompatibility_reasons: [], custom: true, editable: false, in_use: 2,
    },
  ],
}

function dialogByTitle(title: string): HTMLElement {
  const dialog = Array.from(document.body.querySelectorAll<HTMLElement>('section'))
    .find(section => section.querySelector('h2')?.textContent?.trim() === title)
  if (!dialog) throw new Error(`未找到对话框：${title}`)
  return dialog
}

function articleByText(wrapper: ReturnType<typeof mount>, text: string) {
  const article = wrapper.findAll('article').find(candidate => candidate.text().includes(text))
  if (!article) throw new Error(`未找到卡片：${text}`)
  return article
}

describe('AdventuresView', () => {
  beforeEach(() => {
    mocks.api.mockReset()
    mocks.apiBlob.mockReset()
    mocks.api.mockResolvedValue(packages)
    i18n.global.locale.value = 'zh-CN'
    mocks.route.query = {}
    mocks.router.replace.mockClear()
  })

  it('ignores unknown navigation intents and does not consume the query', async () => {
    mocks.route.query = { intent: 'delete-all', keep: '1' }
    const wrapper = mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.findAll('[role="dialog"]').length).toBe(0)
    expect(mocks.router.replace).not.toHaveBeenCalled()
    expect(mocks.route.query).toEqual({ intent: 'delete-all', keep: '1' })
  })

  it.each([
    ['new', '新建冒险包'],
    ['ai', 'AI 生成冒险草稿'],
  ] as const)('opens the existing owner modal for valid %s intent and consumes only intent', async (intent, title) => {
    mocks.route.query = { intent, keep: '1' }
    const wrapper = mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.text()).toContain(title)
    expect(mocks.router.replace).toHaveBeenCalledWith({ query: { keep: '1' } })
  })

  it.each([
    ['script-import', 'scriptImportOpen'],
    ['text-review', 'contentReviewOpen'],
  ] as const)('opens the existing review/import owner for %s intent', async (intent, stateKey) => {
    mocks.route.query = { intent }
    const wrapper = mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect((wrapper.vm as unknown as Record<string, unknown>)[stateKey]).toBe(true)
    expect(mocks.router.replace).toHaveBeenCalledWith({ query: {} })
  })

  it('opens the package file picker for package-import without submitting it', async () => {
    const click = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => undefined)
    mocks.route.query = { intent: 'package-import' }
    mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(click).toHaveBeenCalled()
    expect(mocks.api).not.toHaveBeenCalledWith('/adventures/import', expect.anything())
    expect(mocks.router.replace).toHaveBeenCalledWith({ query: {} })
    click.mockRestore()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows worldbook separation and locks packages referenced by saves', async () => {
    const wrapper = mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.text()).toContain('世界、资料册与冒险包各司其职')
    expect(wrapper.text()).toContain('灰沼失灯记')
    expect(wrapper.text()).toContain('长期战役')
    expect(wrapper.text()).toContain('该版本已被存档引用')
    const boundCard = articleByText(wrapper, '长期战役')
    const edit = boundCard.findAll('button').find(button => button.text() === '编辑')
    const remove = boundCard.findAll('button').find(button => button.text() === '删除')
    expect(edit?.attributes('disabled')).toBeDefined()
    expect(remove?.attributes('disabled')).toBeDefined()
  })

  it('locks direct edit and delete for a read-only plugin package', async () => {
    mocks.api.mockResolvedValue({
      ok: true,
      adventures: [...packages.adventures, {
        adventure_id: 'plugin:shared', source_kind: 'plugin', source_id: 'conflict-module',
        directory_id: 'shared', name: '插件只读冒险', summary: '由插件提供', version: '1.0.0',
        format: 'diceframe:adventure-graph-v1', world_policy: 'portable',
        recommended_world_id: '', compatibility: 'compatible',
        incompatibility_reasons: [], custom: true, editable: false, in_use: 0,
      }],
    })
    const wrapper = mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()

    const card = articleByText(wrapper, '插件只读冒险')
    const edit = card.findAll('button').find(button => button.text() === '编辑')
    const remove = card.findAll('button').find(button => button.text() === '删除')
    expect(edit?.attributes('disabled')).toBeDefined()
    expect(remove?.attributes('disabled')).toBeDefined()
  })

  it('opens a copy form with a new user identity', async () => {
    const wrapper = mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()

    const copy = articleByText(wrapper, '灰沼失灯记').findAll('button')
      .find(button => button.text() === '复制并编辑')
    expect(copy).toBeDefined()
    await copy!.trigger('click')

    const inputs = dialogByTitle('复制冒险包').querySelectorAll<HTMLInputElement>('input')
    expect(inputs[0]?.value).toBe('custom_lanterns_of_greymoor')
    expect(inputs[1]?.value).toBe('user:custom_lanterns_of_greymoor')
  })

  it('uses one staged modal for AI drafting instead of stacking create and AI dialogs', async () => {
    mocks.api.mockImplementation(async (path: string) => {
      if (path === '/worlds') return { ok: true, worlds: [] }
      if (path === '/generate-text') return {
        ok: true,
        text: JSON.stringify({
          name: '雾港失踪案', summary: '调查雾港的失踪者。',
          chapters: [{ name: '第一章', steps: [{ title: '抵达港口', choices: [] }] }],
        }),
      }
      return packages
    })
    const wrapper = mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()

    const aiButton = wrapper.findAll('button').find(button => button.text() === 'AI 生成冒险草稿')
    await aiButton?.trigger('click')
    const draftDialog = dialogByTitle('AI 生成冒险草稿')
    const prompt = draftDialog.querySelector<HTMLTextAreaElement>('textarea')
    expect(prompt).not.toBeNull()
    if (prompt) {
      prompt.value = '一个发生在雾港的三章调查冒险'
      prompt.dispatchEvent(new Event('input'))
    }
    await wrapper.vm.$nextTick()
    const generate = Array.from(draftDialog.querySelectorAll<HTMLButtonElement>('button'))
      .find(button => button.textContent?.includes('生成草稿'))
    generate?.click()
    await flushPromises()

    expect(dialogByTitle('AI 生成冒险草稿')).toBe(draftDialog)
    expect(draftDialog.textContent).toContain('雾港失踪案')
    expect(draftDialog.textContent).toContain('1 章 · 1 个步骤')
  })

  it('edits a v2 graph without converting it to v1 or discarding gates and resources', async () => {
    const item = { ...packages.adventures[1], adventure_id: 'user:graph', name: '图冒险', format: 'diceframe:adventure-graph-v2', editable: true, in_use: 0 }
    const files = {
      'manifest.json': { adventure_id: item.adventure_id, version: '1.0.0', format: item.format, world_policy: 'portable', recommended_world_id: '' },
      'adventure.json': {
        id: 'graph', name: item.name, format: item.format, chapters: [{ id: 'ch', name: '章节' }], start_node_ids: ['a'],
        nodes: [{ id: 'a', type: 'scene', chapter_id: 'ch', description: '原始场景', npc_refs: ['npc:guard'], transitions: [{ to: 'a', conditions: [{ type: 'world.fact_equals', key: 'gate.open', value: true }] }] }],
      },
      'npcs/guard.json': { id: 'guard', name: '守卫' },
    }
    mocks.api.mockImplementation(async (path: string, options?: RequestInit) => {
      if (options?.method === 'PUT') return { ok: true }
      if (path.startsWith('/adventures/user%3Agraph?')) return { ok: true, adventure: { files: structuredClone(files) } }
      return { ok: true, adventures: [item] }
    })
    const wrapper = mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()
    await articleByText(wrapper, '图冒险').findAll('button').find(button => button.text() === '编辑')!.trigger('click')
    await flushPromises()
    const dialog = dialogByTitle('编辑冒险包')
    const description = dialog.querySelector<HTMLTextAreaElement>('[data-testid=graph-node-description]')!
    description.value = '修改后的场景'
    description.dispatchEvent(new Event('input'))
    await wrapper.vm.$nextTick()
    Array.from(dialog.querySelectorAll<HTMLButtonElement>('button')).find(button => button.textContent === '保存配置')!.click()
    await flushPromises()
    const put = mocks.api.mock.calls.find(([, options]) => options?.method === 'PUT')!
    const saved = JSON.parse(put[1].body).files
    expect(saved['adventure.json'].nodes[0]).toEqual({ ...files['adventure.json'].nodes[0], description: '修改后的场景' })
    expect(saved['adventure.json'].format).toBe('diceframe:adventure-graph-v2')
    expect(saved['npcs/guard.json']).toEqual(files['npcs/guard.json'])
    expect(saved['adventure.json'].tutorial).toBeUndefined()
    wrapper.unmount()
  })
})
