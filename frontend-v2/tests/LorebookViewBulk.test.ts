import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LorebookView from '../src/features/lorebook/LorebookView.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  confirm: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api, errorMessage: (cause: unknown) => String((cause as Error)?.message || cause) }
})
vi.mock('../src/peer/game/bridge', () => ({
  activePeerGameClient: () => null,
  setActivePeerGameClient: vi.fn(),
}))
vi.mock('../src/composables/useToast', () => ({ useToast: () => mocks.toast }))
vi.mock('../src/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: mocks.confirm }) }))

const worlds = { worlds: [{ id: 'w1', name: '测试世界', language: 'zh-CN', entry_count: 3 }] }
const games = { games: [{ game_key: 'g1', world_id: 'w1', language: 'zh-CN' }] }
const characters = { players: [{ user_id: 'u1', character_name: '莱拉' }], rule_meta: {} }
const books = {
  books: [
    { id: 'world:w1', name: '主世界书', primary: true, scope: 'world', enabled: true, scan_depth: 4, token_budget: 2000, recursive_scanning: false },
    { id: 'book:other', name: '别处', scope: 'world', enabled: true },
  ],
}
const lorebook = {
  // 触发方式按产品口径（is_constant + vector_activation）区分，legacy match_mode 不参与筛选。
  entries: [
    { id: 'a', world_id: 'w1', name: '城门守卫', type: 'npc', content: '公开背景', keywords: ['城门'], visible_to: ['*'], enabled: 1, match_mode: 'any', is_constant: false, vector_activation: 'off' },
    { id: 'b', world_id: 'w1', name: '秘血教派', type: 'faction', content: '莱拉的私人线索', keywords: ['血'], visible_to: ['u1'], enabled: 0, match_mode: 'all', is_constant: false, vector_activation: 'hybrid' },
    { id: 'c', world_id: 'w1', name: '幕后黑手', type: 'npc', content: 'GM 秘密', visible_to: [], match_mode: 'not_any', is_constant: true, vector_activation: 'off' },
  ],
}

function previewFor(path: string) {
  const params = new URLSearchParams(path.split('?')[1] || '')
  const viewer = params.get('viewer') || 'gm'
  const projections = {
    a: { visible: true, audience: 'public', subjects: [] },
    b: { visible: viewer === 'gm' || viewer === 'u1', audience: 'character', subjects: ['莱拉'] },
    c: { visible: viewer === 'gm', audience: 'gm', subjects: [] },
  }
  return { ok: true, world_id: 'w1', projections, summary: { total: 3, visible: 3, public: 1, character_only: 1, gm_secret: 1 } }
}

function mutationCalls(fragment: string) {
  return mocks.api.mock.calls.filter(([path]) => String(path).includes(fragment))
}

function mountView() {
  // Modal 走 Teleport；stub 掉才能在同一棵树上断言模态框内容。
  return mount(LorebookView, { global: { plugins: [i18n], stubs: { teleport: true } } })
}

async function mountLoaded() {
  const wrapper = mountView()
  await flushPromises()
  await flushPromises()
  return wrapper
}

function bulkButton(wrapper: ReturnType<typeof mountView>, label: string) {
  const button = wrapper.findAll('.lore-entry-bulk button').find(item => item.text() === label)
  expect(button, `bulk button ${label}`).toBeTruthy()
  return button!
}

/** 行按 canonical 类型分区渲染，索引不稳定；按名称定位。 */
function rowFor(wrapper: ReturnType<typeof mountView>, name: string) {
  const row = wrapper.findAll('.lore-row').find(item => item.text().includes(name))
  expect(row, `row ${name}`).toBeTruthy()
  return row!
}

describe('LorebookView entry search, filters and bulk actions', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('currentGame', 'g1')
    i18n.global.locale.value = 'zh-CN'
    mocks.api.mockReset()
    mocks.confirm.mockReset()
    mocks.confirm.mockResolvedValue(true)
    Object.values(mocks.toast).forEach(fn => fn.mockReset())
    mocks.api.mockImplementation(async (path: string, init?: { method?: string }) => {
      const p = String(path)
      if (p.includes('/preview')) return previewFor(p)
      if (p.includes('/characters')) return characters
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return books
      if (p.includes('/move')) return { ok: true, entry_id: 'a', book_id: 'book:other' }
      if (p.includes('/entries/')) return { ok: true, entry: lorebook.entries[0] }
      if (p.includes('/entries')) return { ok: true, entries: lorebook.entries }
      if (p.includes('/lorebook/')) return lorebook
      if (p.includes('/worlds')) return worlds
      if (init?.method === 'PUT') return { ok: true }
      throw new Error(`unexpected path ${p}`)
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('lists every loaded entry and selects visible rows in bulk', async () => {
    const wrapper = await mountLoaded()
    expect(wrapper.findAll('.lore-row')).toHaveLength(3)

    await wrapper.get('.lore-bulk-select-all').setValue(true)
    expect(wrapper.get('.lore-entry-bulk').text()).toContain('已选 3 条')
    const disable = bulkButton(wrapper, '停用')
    expect((disable.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('searches name, content, and keywords locally without another request', async () => {
    const wrapper = await mountLoaded()
    const before = mocks.api.mock.calls.length

    await wrapper.get('.lore-entry-search').setValue('教派')
    expect(wrapper.findAll('.lore-row')).toHaveLength(1)
    expect(wrapper.get('.lore-row').text()).toContain('秘血教派')

    await wrapper.get('.lore-entry-search').setValue('城门')
    expect(wrapper.get('.lore-row').text()).toContain('城门守卫')

    await wrapper.get('.lore-entry-search').setValue('私人线索')
    expect(wrapper.get('.lore-row').text()).toContain('秘血教派')

    expect(mocks.api.mock.calls.length).toBe(before)
  })

  it('filters by type, visibility, state, activation, and source locally', async () => {
    const wrapper = await mountLoaded()
    const before = mocks.api.mock.calls.length

    await wrapper.get('.lore-filter-state').setValue('disabled')
    expect(wrapper.findAll('.lore-row')).toHaveLength(1)
    expect(wrapper.get('.lore-row').text()).toContain('秘血教派')

    await wrapper.get('.lore-entry-filter-reset').trigger('click')
    await wrapper.get('.lore-filter-visibility').setValue('public')
    expect(wrapper.findAll('.lore-row')).toHaveLength(1)
    expect(wrapper.get('.lore-row').text()).toContain('城门守卫')

    await wrapper.get('.lore-entry-filter-reset').trigger('click')
    await wrapper.get('.lore-filter-activation').setValue('always')
    expect(wrapper.findAll('.lore-row')).toHaveLength(1)
    expect(wrapper.get('.lore-row').text()).toContain('幕后黑手')

    await wrapper.get('.lore-entry-filter-reset').trigger('click')
    await wrapper.get('.lore-filter-type').setValue('faction')
    expect(wrapper.findAll('.lore-row')).toHaveLength(1)
    expect(wrapper.get('.lore-row').text()).toContain('秘血教派')

    expect(mocks.api.mock.calls.length).toBe(before)
  })

  it('shows an explicit empty state when nothing matches and can reset', async () => {
    const wrapper = await mountLoaded()
    await wrapper.get('.lore-entry-search').setValue('不存在的条目')
    expect(wrapper.find('.lore-no-matches').exists()).toBe(true)
    expect(wrapper.findAll('.lore-row')).toHaveLength(0)

    await wrapper.get('.lore-no-matches button').trigger('click')
    expect(wrapper.findAll('.lore-row')).toHaveLength(3)
  })

  it('disables every selected entry through the per-entry endpoint', async () => {
    const wrapper = await mountLoaded()
    await rowFor(wrapper, '城门守卫').get('input.lore-row-select').setValue(true)
    await rowFor(wrapper, '秘血教派').get('input.lore-row-select').setValue(true)

    await bulkButton(wrapper, '停用').trigger('click')
    await flushPromises()

    const calls = mutationCalls('/entries/').filter(([, init]) => (init as { method?: string })?.method === 'PUT')
    expect(calls.map(([path]) => String(path)).sort()).toEqual([
      '/lorebooks/world%3Aw1/entries/a',
      '/lorebooks/world%3Aw1/entries/b',
    ])
    calls.forEach(([, init]) => {
      expect(JSON.parse(String((init as { body: string }).body))).toEqual({ enabled: false })
    })
  })

  it('changes visibility in bulk with the canonical marker', async () => {
    const wrapper = await mountLoaded()
    await rowFor(wrapper, '幕后黑手').get('input.lore-row-select').setValue(true)

    await bulkButton(wrapper, '设为公开').trigger('click')
    await flushPromises()

    const call = mutationCalls('/entries/').find(([, init]) => (init as { method?: string })?.method === 'PUT')!
    expect(String(call[0])).toBe('/lorebooks/world%3Aw1/entries/c')
    expect(JSON.parse(String((call[1] as { body: string }).body))).toEqual({ visible_to: ['*'] })
  })

  it('deletes selected entries only after confirmation', async () => {
    const wrapper = await mountLoaded()
    await rowFor(wrapper, '秘血教派').get('input.lore-row-select').setValue(true)

    await bulkButton(wrapper, '删除所选').trigger('click')
    await flushPromises()

    expect(mocks.confirm).toHaveBeenCalled()
    const calls = mutationCalls('/entries/').filter(([, init]) => (init as { method?: string })?.method === 'DELETE')
    expect(calls).toHaveLength(1)
    expect(String(calls[0][0])).toBe('/lorebooks/world%3Aw1/entries/b')
  })

  it('moves selected entries with the canonical target book id', async () => {
    const wrapper = await mountLoaded()
    await rowFor(wrapper, '城门守卫').get('input.lore-row-select').setValue(true)

    await bulkButton(wrapper, '移动到世界书').trigger('click')
    await flushPromises()
    await wrapper.get('.lore-bulk-move-target').setValue('book:other')

    const moveAction = wrapper.findAll('.actions button').find(item => item.text() === '移动到世界书')
    expect(moveAction).toBeTruthy()
    await moveAction!.trigger('click')
    await flushPromises()

    const call = mutationCalls('/move')[0]
    expect(call).toBeTruthy()
    expect(String(call[0])).toBe('/lorebooks/world%3Aw1/entries/a/move')
    expect((call[1] as { method?: string }).method).toBe('POST')
    expect(JSON.parse(String((call[1] as { body: string }).body))).toEqual({ target_book_id: 'book:other' })
  })

  it('saves book settings through the book endpoint', async () => {
    const wrapper = await mountLoaded()
    const settingsButton = wrapper.findAll('.lore-header-actions button').find(item => item.text() === '世界书设置')
    expect(settingsButton).toBeTruthy()
    await settingsButton!.trigger('click')
    await flushPromises()

    expect((wrapper.get('.lore-book-scan-depth').element as HTMLInputElement).value).toBe('4')
    await wrapper.get('.lore-book-scan-depth').setValue(8)
    await wrapper.get('.lore-book-token-budget').setValue(4096)
    await wrapper.get('.lore-book-recursive-scanning').setValue(true)

    const save = wrapper.findAll('.actions button').find(item => item.text() === '保存')
    expect(save).toBeTruthy()
    await save!.trigger('click')
    await flushPromises()

    const call = mutationCalls('/lorebooks/world%3Aw1').find(([, init]) => (init as { method?: string })?.method === 'PUT')!
    expect(call).toBeTruthy()
    expect(JSON.parse(String((call[1] as { body: string }).body))).toEqual({
      scan_depth: 8, token_budget: 4096, recursive_scanning: true,
    })
  })
})
