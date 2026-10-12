import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AdventuresView from '../src/features/admin/AdventuresView.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  apiBlob: vi.fn(),
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
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows worldbook separation and locks packages referenced by saves', async () => {
    const wrapper = mount(AdventuresView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.text()).toContain('世界书与冒险包各司其职')
    expect(wrapper.text()).toContain('灰沼失灯记')
    expect(wrapper.text()).toContain('长期战役')
    expect(wrapper.text()).toContain('该版本已被存档引用')
    const boundCard = articleByText(wrapper, '长期战役')
    const edit = boundCard.findAll('button').find(button => button.text() === '编辑')
    const remove = boundCard.findAll('button').find(button => button.text() === '删除')
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
})
