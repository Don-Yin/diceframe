import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WorldsView from '../src/features/worlds/WorldsView.vue'
import { i18n } from '../src/i18n'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  confirm: vi.fn(),
}))

vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api, errorMessage: (cause: unknown) => String((cause as Error)?.message || cause) }
})
vi.mock('../src/api/sceneImages', () => ({
  resolveSceneImageUrl: vi.fn(async () => 'blob:fake-cover'),
  revokeSceneImageUrl: vi.fn(),
  SCENE_IMAGE_ACCEPT: 'image/jpeg,image/png,image/webp',
  uploadSceneImage: vi.fn(async () => ({ kind: 'upload', asset_id: 'scene-test' })),
}))
vi.mock('../src/composables/useBackgroundImages', () => ({
  ruleSceneUrl: () => '',
  initializeBackgroundImages: async () => {},
}))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))
vi.mock('../src/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: mocks.confirm }),
}))

const templates = {
  templates: [
    {
      world_id: 'default_fantasy', world_name: '经典奇幻', description: '内置世界',
      language: 'zh-CN', default_rule: 'freeform_fantasy', lorebook_count: 3, source: 'builtin',
    },
    {
      world_id: 'plugin_world', world_name: '插件世界', description: '',
      language: 'zh-CN', lorebook_count: 1, source: 'plugin', plugin_id: 'demo',
    },
    {
      world_id: 'custom_book_game_copy_1', world_name: '对局临时（复制世界书）',
      language: 'zh-CN', source: 'user', game_scoped: true,
    },
    {
      // 仅存在于模板列表的用户世界：gm_style 必须随模板摘要下发，预览才能编辑。
      world_id: 'custom_book_style_only_1', world_name: '风格模板', description: '',
      language: 'zh-CN', source: 'user',
      gm_style: { tone: 'misty', verbosity: 'brief', custom_instructions: '' },
    },
  ],
}

const worlds = {
  worlds: [
    {
      id: 'default_fantasy', name: '经典奇幻', description: '重复，应被模板去重',
      language: 'zh-CN', entry_count: 3, gm_style: null,
    },
    {
      // 异语世界：zh 界面必须过滤掉。
      id: 'default_fantasy_en', name: 'Classic Fantasy Adventure', description: 'en world',
      language: 'en', entry_count: 3, gm_style: null,
    },
    {
      id: 'custom_book_demo_1', name: '我的世界', description: '自建',
      language: 'zh-CN', entry_count: 5,
      gm_style: { tone: 'noir', verbosity: 'normal', custom_instructions: '' },
    },
  ],
}

const adventures = {
  ok: true,
  adventures: [
    { adventure_id: 'core:lanterns_of_greymoor', name: '灰沼失灯记', recommended_world_id: 'default_fantasy' },
  ],
}

function apiByPath(path: string) {
  if (String(path).includes('/world-templates')) return templates
  if (String(path).includes('/adventures')) return adventures
  if (String(path).includes('/worlds')) return worlds
  throw new Error(`unexpected path ${path}`)
}

function findCardByTitle(wrapper: ReturnType<typeof mount>, name: string) {
  return wrapper.findAll('.world-card').find(card => card.find('h2').text() === name)
}

describe('WorldsView', () => {
  beforeEach(() => {
    push.mockReset()
    mocks.api.mockReset()
    mocks.confirm.mockReset()
    mocks.confirm.mockResolvedValue(true)
    mocks.api.mockImplementation(async (path: string, init?: RequestInit) => {
      const method = (init?.method || 'GET').toUpperCase()
      if (method === 'DELETE') return { ok: true }
      if (method === 'PUT') return { ok: true, gm_style: { tone: '', verbosity: 'normal', custom_instructions: '' } }
      if (method === 'POST' && String(path).includes('clone-from-template')) {
        return { ok: true, world_id: 'custom_book_new_1', name: '经典奇幻', language: 'zh-CN' }
      }
      return apiByPath(path)
    })
    i18n.global.locale.value = 'zh-CN'
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('merges sources, filters foreign-language worlds, and hides game-scoped templates', async () => {
    const wrapper = mount(WorldsView, { global: { plugins: [i18n] } })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('经典奇幻')
    expect(text).toContain('插件世界')
    expect(text).toContain('我的世界')
    expect(text).toContain('风格模板')
    expect(text).not.toContain('对局临时')
    expect(text).not.toContain('Classic Fantasy Adventure')
    expect(wrapper.findAll('.world-card')).toHaveLength(4)
    const badges = wrapper.findAll('.world-card-badge').map(badge => badge.text())
    expect(badges).toContain('内置')
    expect(badges).toContain('插件')
    expect(badges).toContain('自建')
  })

  it('shows the adventure pack badge for worlds bound to an adventure', async () => {
    const wrapper = mount(WorldsView, { global: { plugins: [i18n] } })
    await flushPromises()

    const card = findCardByTitle(wrapper, '经典奇幻')
    expect(card?.text()).toContain('冒险包：灰沼失灯记')
    const other = findCardByTitle(wrapper, '我的世界')
    expect(other?.text()).not.toContain('冒险包')
  })

  it('jumps to the create flow with the chosen world prefilled', async () => {
    const wrapper = mount(WorldsView, { global: { plugins: [i18n] } })
    await flushPromises()

    const card = findCardByTitle(wrapper, '经典奇幻')
    const useButton = card?.findAll('button').find(button => button.text() === '用它开团')
    await useButton?.trigger('click')

    expect(push).toHaveBeenCalledWith({ name: 'create', query: { world: 'default_fantasy' } })
  })

  it('clones a built-in world via the clone API and disables clone on user worlds', async () => {
    const wrapper = mount(WorldsView, { global: { plugins: [i18n] } })
    await flushPromises()

    const builtinCard = findCardByTitle(wrapper, '经典奇幻')
    const cloneButton = builtinCard?.findAll('button').find(button => button.text() === '克隆为我的世界')
    expect(cloneButton?.attributes('disabled')).toBeUndefined()
    await cloneButton?.trigger('click')
    await flushPromises()

    const cloneCall = mocks.api.mock.calls.find(([path, init]) =>
      String(path).includes('clone-from-template') && (init as RequestInit)?.method === 'POST')
    expect(cloneCall).toBeTruthy()
    expect(JSON.parse(String((cloneCall?.[1] as RequestInit).body))).toEqual({ template_id: 'default_fantasy' })

    const userCard = findCardByTitle(wrapper, '我的世界')
    const userClone = userCard?.findAll('button').find(button => button.text() === '克隆为我的世界')
    expect(userClone?.attributes('disabled')).toBeDefined()
  })

  it('edits GM style for user worlds from both template and world lists', async () => {
    const wrapper = mount(WorldsView, { global: { plugins: [i18n] } })
    await flushPromises()

    const builtinCard = findCardByTitle(wrapper, '经典奇幻')
    await builtinCard?.findAll('button').find(button => button.text() === '预览')?.trigger('click')
    await flushPromises()
    expect(document.querySelector('.dialog')?.textContent).toContain('内置或插件世界只读')
    document.querySelector<HTMLButtonElement>('.dialog .modal-x')?.click()
    await flushPromises()

    // 模板列表来源的用户世界：gm_style 随摘要下发，可直接编辑。
    const templateCard = findCardByTitle(wrapper, '风格模板')
    await templateCard?.findAll('button').find(button => button.text() === '预览')?.trigger('click')
    await flushPromises()
    let tone = document.querySelector<HTMLInputElement>('.world-style-editor input')
    expect(tone?.value).toBe('misty')
    document.querySelector<HTMLButtonElement>('.dialog .modal-x')?.click()
    await flushPromises()

    const userCard = findCardByTitle(wrapper, '我的世界')
    await userCard?.findAll('button').find(button => button.text() === '预览')?.trigger('click')
    await flushPromises()

    const dialog = document.querySelector('.dialog')
    expect(dialog?.textContent).toContain('GM 叙事风格')
    tone = dialog?.querySelector<HTMLInputElement>('.world-style-editor input') ?? null
    expect(tone?.value).toBe('noir')
    if (tone) {
      tone.value = 'gothic'
      tone.dispatchEvent(new Event('input'))
    }
    await flushPromises()
    const save = Array.from(document.querySelectorAll<HTMLButtonElement>('.dialog button'))
      .find(button => button.textContent?.includes('保存风格'))
    save?.click()
    await flushPromises()

    const saveCall = mocks.api.mock.calls.find(([path, init]) =>
      String(path).includes('/gm-style') && (init as RequestInit)?.method === 'PUT')
    expect(saveCall).toBeTruthy()
    expect(String(saveCall?.[0])).toContain('custom_book_demo_1')
    expect(JSON.parse(String((saveCall?.[1] as RequestInit).body)).gm_style.tone).toBe('gothic')
  })

  it('deletes user worlds through the confirm-guarded delete API', async () => {
    const wrapper = mount(WorldsView, { global: { plugins: [i18n] } })
    await flushPromises()

    const userCard = findCardByTitle(wrapper, '我的世界')
    await userCard?.findAll('button').find(button => button.text() === '预览')?.trigger('click')
    await flushPromises()

    const deleteButton = Array.from(document.querySelectorAll<HTMLButtonElement>('.dialog button'))
      .find(button => button.textContent?.includes('删除世界'))
    expect(deleteButton).toBeTruthy()
    deleteButton?.click()
    await flushPromises()

    expect(mocks.confirm).toHaveBeenCalled()
    expect(String(mocks.confirm.mock.calls[0]?.[0]?.content || '')).toContain('我的世界')
    const deleteCall = mocks.api.mock.calls.find(([path, init]) =>
      String(path).includes('/worlds/custom_book_demo_1') && (init as RequestInit)?.method === 'DELETE')
    expect(deleteCall).toBeTruthy()
    expect(document.querySelector('.dialog')).toBeNull()
  })
})
