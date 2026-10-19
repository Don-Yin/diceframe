import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LorebookView from '../src/features/lorebook/LorebookView.vue'
import LorebookCreateDialog from '../src/features/lorebook/LorebookCreateDialog.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api, errorMessage: (cause: unknown) => String((cause as Error)?.message || cause) }
})
vi.mock('../src/peer/game/bridge', () => ({ activePeerGameClient: () => null, setActivePeerGameClient: vi.fn() }))
vi.mock('../src/composables/useToast', () => ({ useToast: () => mocks.toast }))
vi.mock('../src/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true) }) }))

const worlds = { worlds: [{ id: 'w1', name: '测试世界', language: 'zh-CN', entry_count: 3 }] }
const games = { games: [{ game_key: 'g1', world_id: 'w1', language: 'zh-CN' }] }
const books = {
  books: [
    { id: 'world:w1', name: '主世界书', primary: true, scope: 'world', enabled: true, entry_count: 3 },
    { id: 'book:other', name: '另一册', scope: '', enabled: true, entry_count: 1 },
  ],
}
const singleBook = {
  books: [books.books[0]],
}

function mountView() {
  return mount(LorebookView, { global: { plugins: [i18n], stubs: { teleport: true } } })
}

async function mountLoaded() {
  const wrapper = mountView()
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('Lorebook Book creation and target selection', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('currentGame', 'g1')
    i18n.global.locale.value = 'zh-CN'
    mocks.api.mockReset()
    Object.values(mocks.toast).forEach(fn => fn.mockReset())
    mocks.api.mockImplementation(async (path: string, init?: { method?: string; body?: string }) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return books
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/preview')) return { ok: true, projections: {}, summary: { total: 0, visible: 0 } }
      if (p.includes('/worlds')) return worlds
      if (p === '/lorebooks' && init?.method === 'POST') return { ok: true, book: { id: 'book:new', name: '新册' } }
      if (p.includes('/bindings') && init?.method === 'POST') return { ok: true }
      if (p.includes('/lorebook/w1/generate')) return { ok: true, entries: [], count: 0 }
      throw new Error(`unexpected path ${p}`)
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('falls back to an available world when the saved world is missing', async () => {
    const load = mocks.api.getMockImplementation()!
    mocks.api.mockImplementation((path: string, init?: { method?: string; body?: string }) => {
      if (path === '/games') return Promise.resolve({ games: [{ game_key: 'g1', world_id: 'missing-world', language: 'zh-CN' }] })
      return load(path, init)
    })
    const wrapper = await mountLoaded()
    const select = wrapper.findAll('.lore-context-select')[0].element as HTMLSelectElement
    expect(select.value).toBe('w1')
    const book = wrapper.get('.lore-context-select[aria-label="当前资料册"]').element as HTMLSelectElement
    expect(book.value).toBe('world:w1')
  })

  it('opens a real modal with current world as the default binding', async () => {
    const wrapper = await mountLoaded()
    await wrapper.get('.lore-context-bar button.success').trigger('click')

    expect(wrapper.find('.lore-book-create-dialog').exists()).toBe(true)
    expect((wrapper.get('.lore-book-create-name').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('.lore-book-create-scope').element as HTMLSelectElement).value).toBe('world')
    expect(wrapper.get('.lore-book-create-scope').text()).toContain('测试世界')
  })

  it('keeps the create dialog world option stable when scope changes directly', async () => {
    const wrapper = mount(LorebookCreateDialog, {
      props: { open: true, worldId: 'w1', worldName: '测试世界', gameKey: 'g1' },
      global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /><slot name="actions" /></div>' } } },
    })
    const scope = wrapper.get('.lore-book-create-scope')
    expect(scope.get('option[value="world"]').text()).toBe('当前世界（测试世界）')
    await scope.setValue('global')
    expect(scope.get('option[value="world"]').text()).toBe('当前世界（测试世界）')
  })

  it('collapses the Book selector when the current world has one Book', async () => {
    mocks.api.mockImplementation(async (path: string) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return singleBook
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/preview')) return { ok: true, projections: {}, summary: { total: 0, visible: 0 } }
      if (p.includes('/worlds')) return worlds
      throw new Error(`unexpected path ${p}`)
    })
    const wrapper = await mountLoaded()

    expect(wrapper.findAll('.lore-context-select')).toHaveLength(1)
    expect(wrapper.get('.lore-book-static').text()).toContain('主世界书')
    expect(wrapper.findAll('.lore-context-row')[1].find('.lore-context-label').text()).toContain('当前浏览世界')
    expect(wrapper.get('.lore-context-row--book .lore-book-meta').text()).toContain('3')
  })

  it('shows each Book scope in the selector option', async () => {
    const wrapper = await mountLoaded()
    const bookSelect = wrapper.findAll('.lore-context-select')[1]

    expect(bookSelect.text()).toContain('当前世界')
    expect(bookSelect.text()).toContain('未绑定')
  })

  it('hides delete for a primary Book even when its canonical id belongs to another world', async () => {
    mocks.api.mockImplementation(async (path: string) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return {
        books: [
          { id: 'world:w1', name: '主世界书', primary: true, scope: 'world', enabled: true, entry_count: 3 },
          { id: 'world:foreign', name: '另一世界主册', primary: true, scope: 'world', enabled: true, entry_count: 1 },
        ],
      }
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/preview')) return { ok: true, projections: {}, summary: { total: 0, visible: 0 } }
      if (p.includes('/worlds')) return worlds
      throw new Error(`unexpected path ${p}`)
    })
    const wrapper = await mountLoaded()
    await wrapper.findAll('.lore-context-select')[1].setValue('world:foreign')
    const menus = wrapper.findAll('details.lore-menu')
    await menus[1].get('summary').trigger('click')

    expect(menus[1].find('button.danger').exists()).toBe(false)
  })

  it('does not let a late import response override a newer Book selection', async () => {
    let resolveImport!: (value: { ok: boolean; book_id: string }) => void
    let importCompleted = false
    const importCommit = new Promise<{ ok: boolean; book_id: string }>(resolve => { resolveImport = resolve })
    mocks.api.mockImplementation(async (path: string, init?: { method?: string; body?: string }) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return importCompleted
        ? { books: [...books.books, { id: 'book:imported', name: '导入册', scope: '', enabled: true, entry_count: 0 }] }
        : books
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/preview')) return { format: 'lorebook_v3', counts: { entries: 0, mapped: 0, warnings: 0, unsupported: 0 }, warnings: [] }
      if (p.includes('/worlds')) return worlds
      if (p === '/lorebooks/import' && init?.method === 'POST') return importCommit
      throw new Error(`unexpected path ${p}`)
    })
    const wrapper = await mountLoaded()
    const file = new File(['{"entries":[]}'], 'deferred.json', { type: 'application/json' })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { configurable: true, value: [file] })
    await fileInput.trigger('change')
    await flushPromises()
    const importButton = wrapper.findAll('.lore-import-dialog button').find(button => button.text() === '导入')
    expect(importButton).toBeTruthy()
    await importButton!.trigger('click')
    await wrapper.findAll('.lore-context-select')[1].setValue('book:other')
    importCompleted = true
    resolveImport({ ok: true, book_id: 'book:imported' })
    await flushPromises()
    await flushPromises()

    expect((wrapper.findAll('.lore-context-select')[1].element as HTMLSelectElement).value).toBe('book:other')
  })

  it('keeps a newer world selection when the import refresh completes late', async () => {
    let resolveImport!: (value: { ok: boolean; book_id: string }) => void
    const importCommit = new Promise<{ ok: boolean; book_id: string }>(resolve => { resolveImport = resolve })
    const twoWorlds = { worlds: [
      { id: 'w1', name: '测试世界', language: 'zh-CN', entry_count: 3 },
      { id: 'w2', name: '第二世界', language: 'zh-CN', entry_count: 1 },
    ] }
    mocks.api.mockImplementation(async (path: string, init?: { method?: string; body?: string }) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return books
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/preview')) return { format: 'lorebook_v3', counts: { entries: 0, mapped: 0, warnings: 0, unsupported: 0 }, warnings: [] }
      if (p.includes('/worlds')) return twoWorlds
      if (p === '/lorebooks/import' && init?.method === 'POST') return importCommit
      throw new Error(`unexpected path ${p}`)
    })
    const wrapper = await mountLoaded()
    const file = new File(['{"entries":[]}'], 'deferred-world.json', { type: 'application/json' })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { configurable: true, value: [file] })
    await fileInput.trigger('change')
    await flushPromises()
    const importButton = wrapper.findAll('.lore-import-dialog button').find(button => button.text() === '导入')
    expect(importButton).toBeTruthy()
    await importButton!.trigger('click')
    await wrapper.findAll('.lore-context-select')[0].setValue('w2')
    resolveImport({ ok: true, book_id: 'book:imported' })
    await flushPromises()
    await flushPromises()

    expect((wrapper.findAll('.lore-context-select')[0].element as HTMLSelectElement).value).toBe('w2')
  })

  it('keeps an explicit world selection while the current game query is pending', async () => {
    let resolveGames!: (value: typeof games) => void
    const pendingGames = new Promise<typeof games>(resolve => { resolveGames = resolve })
    const twoWorlds = { worlds: [
      { id: 'w1', name: '测试世界', language: 'zh-CN', entry_count: 3 },
      { id: 'w2', name: '第二世界', language: 'zh-CN', entry_count: 1 },
    ] }
    const w2Books = { books: [{ id: 'world:w2', name: '第二世界资料册', primary: true, scope: 'world', enabled: true, entry_count: 1 }] }
    mocks.api.mockImplementation(async (path: string) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return pendingGames
      if (p.startsWith('/lorebooks?')) return p.includes('world_id=w2') ? w2Books : books
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/worlds')) return twoWorlds
      throw new Error(`unexpected path ${p}`)
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('.lore-context-select').setValue('w2')
    await flushPromises()

    resolveGames(games)
    await flushPromises()
    await flushPromises()

    expect((wrapper.get('.lore-context-select').element as HTMLSelectElement).value).toBe('w2')
    expect(wrapper.get('.lore-book-static').text()).toContain('第二世界资料册')
  })

  it('creates the book and posts the explicitly selected world binding', async () => {
    const wrapper = await mountLoaded()
    await wrapper.get('.lore-context-bar button.success').trigger('click')
    await wrapper.get('.lore-book-create-name').setValue('新册')
    await wrapper.get('.lore-book-create-dialog .actions button.primary').trigger('click')
    await flushPromises()

    const binding = mocks.api.mock.calls.find(([path, init]) => String(path).includes('/bindings') && (init as { method?: string })?.method === 'POST')
    expect(binding).toBeTruthy()
    expect(JSON.parse(String((binding![1] as { body: string }).body))).toEqual(expect.objectContaining({
      scope_kind: 'world', scope_id: 'w1',
    }))
  })

  it('keeps an unbound book visible and offers binding retry when binding fails', async () => {
    mocks.api.mockImplementation(async (path: string, init?: { method?: string; body?: string }) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return books
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/preview')) return { ok: true, projections: {}, summary: { total: 0, visible: 0 } }
      if (p.includes('/worlds')) return worlds
      if (p === '/lorebooks' && init?.method === 'POST') return { ok: true, book: { id: 'book:new', name: '新册' } }
      if (p.includes('/bindings') && init?.method === 'POST') throw new Error('binding denied')
      throw new Error(`unexpected path ${p}`)
    })
    const wrapper = await mountLoaded()
    await wrapper.get('.lore-context-bar button.success').trigger('click')
    await wrapper.get('.lore-book-create-name').setValue('新册')
    await wrapper.get('.lore-book-create-dialog .actions button.primary').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('未绑定')
    expect(wrapper.find('.lore-book-binding-retry').exists()).toBe(true)
  })

  it('keeps create errors inside the create dialog', async () => {
    mocks.api.mockImplementation(async (path: string, init?: { method?: string; body?: string }) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return books
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/preview')) return { ok: true, projections: {}, summary: { total: 0, visible: 0 } }
      if (p.includes('/worlds')) return worlds
      if (p === '/lorebooks' && init?.method === 'POST') throw new Error('create denied')
      throw new Error(`unexpected path ${p}`)
    })
    const wrapper = await mountLoaded()
    await wrapper.get('.lore-context-bar button.success').trigger('click')
    await wrapper.get('.lore-book-create-name').setValue('新册')
    await wrapper.get('.lore-book-create-dialog .actions button.primary').trigger('click')
    await flushPromises()

    expect(wrapper.get('.lore-book-create-dialog').text()).toContain('create denied')
    expect(wrapper.get('.lore-book-create-dialog [role="alert"]').text()).toContain('create denied')
  })

  it('retries a failed binding with the same id and does not create another Book', async () => {
    let bindingAttempts = 0
    mocks.api.mockImplementation(async (path: string, init?: { method?: string; body?: string }) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return books
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/preview')) return { ok: true, projections: {}, summary: { total: 0, visible: 0 } }
      if (p.includes('/worlds')) return worlds
      if (p === '/lorebooks' && init?.method === 'POST') return { ok: true, book: { id: 'book:new', name: '新册' } }
      if (p.includes('/bindings') && init?.method === 'POST') {
        bindingAttempts += 1
        if (bindingAttempts === 1) throw new Error('binding response lost')
        return { ok: true }
      }
      throw new Error(`unexpected path ${p}`)
    })
    const wrapper = await mountLoaded()
    await wrapper.get('.lore-context-bar button.success').trigger('click')
    await wrapper.get('.lore-book-create-name').setValue('新册')
    await wrapper.get('.lore-book-create-dialog .actions button.primary').trigger('click')
    await flushPromises()
    await wrapper.get('.lore-book-binding-retry').trigger('click')
    await flushPromises()

    const creates = mocks.api.mock.calls.filter(([path, init]) => String(path) === '/lorebooks' && (init as { method?: string })?.method === 'POST')
    const bindings = mocks.api.mock.calls.filter(([path, init]) => String(path).includes('/bindings') && (init as { method?: string })?.method === 'POST')
    expect(creates).toHaveLength(1)
    expect(bindings).toHaveLength(2)
    expect(JSON.parse(String((bindings[0][1] as { body: string }).body)).id)
      .toBe(JSON.parse(String((bindings[1][1] as { body: string }).body)).id)
  })

  it('treats an explicit binding error response as a failed binding', async () => {
    mocks.api.mockImplementation(async (path: string, init?: { method?: string; body?: string }) => {
      const p = String(path)
      if (p.includes('/characters')) return { players: [], rule_meta: {} }
      if (p.includes('/games')) return games
      if (p.startsWith('/lorebooks?')) return books
      if (p.includes('/entries')) return { ok: true, entries: [] }
      if (p.includes('/preview')) return { ok: true, projections: {}, summary: { total: 0, visible: 0 } }
      if (p.includes('/worlds')) return worlds
      if (p === '/lorebooks' && init?.method === 'POST') return { ok: true, book: { id: 'book:new', name: '新册' } }
      if (p.includes('/bindings') && init?.method === 'POST') return { ok: false, error: 'binding denied' }
      throw new Error(`unexpected path ${p}`)
    })
    const wrapper = await mountLoaded()
    await wrapper.get('.lore-context-bar button.success').trigger('click')
    await wrapper.get('.lore-book-create-name').setValue('新册')
    await wrapper.get('.lore-book-create-dialog .actions button.primary').trigger('click')
    await flushPromises()

    expect(wrapper.find('.lore-book-binding-retry').exists()).toBe(true)
    expect(wrapper.text()).toContain('binding denied')
  })

  it('sends the selected Book as the bounded AI generation target', async () => {
    const wrapper = await mountLoaded()
    await wrapper.findAll('.lore-context-select')[1].setValue('book:other')
    await wrapper.get('.lore-tools input').setValue('港口与商会')
    await wrapper.get('.lore-tools button:not(.success)').trigger('click')
    await flushPromises()

    const call = mocks.api.mock.calls.find(([path, init]) => String(path).includes('/lorebook/w1/generate') && (init as { method?: string })?.method === 'POST')
    expect(call).toBeTruthy()
    expect(JSON.parse(String((call![1] as { body: string }).body))).toEqual(expect.objectContaining({ book_id: 'book:other' }))
  })
})
