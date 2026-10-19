import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import { readCurrentGame, rememberCurrentGame } from '../src/stores/gameContext'
import MemoryView from '../src/features/admin/MemoryView.vue'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))

vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api }
})
vi.mock('../src/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: vi.fn() }) }))
vi.mock('../src/composables/useToast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))

describe('MemoryView', () => {
  beforeEach(() => {
    const store = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value) },
      removeItem: (key: string) => { store.delete(key) },
      clear: () => { store.clear() },
    })
    mocks.api.mockReset()
    i18n.global.locale.value = 'zh-CN'
  })

  it('shows a direct exit when no game is selected', async () => {
    expect(readCurrentGame()).toBe('')
    const wrapper = mount(MemoryView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="memory-no-game"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('查看存档')
  })

  it('clears the previous search scope while a new search is unavailable', async () => {
    rememberCurrentGame('memory-scope-game')
    mocks.api.mockResolvedValueOnce({ memories: [{ id: 'm1', entity: 'Old scope', value: 'old marker' }], total: 1 })
    const wrapper = mount(MemoryView, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.text()).toContain('old marker')

    mocks.api.mockRejectedValue(new Error('search unavailable'))
    const input = wrapper.find('.memory-search input')
    await input.setValue('new scope')
    await input.trigger('keyup.enter')
    await flushPromises()
    expect(wrapper.text()).not.toContain('old marker')
    expect(wrapper.text()).toContain('search unavailable')
    expect(wrapper.find('.empty-panel').exists()).toBe(false)
  })

  it('ignores an older search response that finishes after the latest search', async () => {
    rememberCurrentGame('memory-race-game')
    mocks.api.mockResolvedValueOnce({ memories: [], total: 0 })
    const wrapper = mount(MemoryView, { global: { plugins: [i18n] } })
    await flushPromises()

    let resolveOld!: (value: unknown) => void
    const oldSearch = new Promise(resolve => { resolveOld = resolve })
    mocks.api.mockImplementation((url: string) => url.includes('keyword=first')
      ? oldSearch
      : Promise.resolve({ memories: [{ id: 'new', entity: 'Newest search', value: 'new marker' }], total: 1 }))
    const input = wrapper.find('.memory-search input')
    await input.setValue('first')
    await input.trigger('keyup.enter')
    await input.setValue('second')
    await input.trigger('keyup.enter')
    await flushPromises()
    expect(wrapper.text()).toContain('new marker')
    resolveOld({ memories: [{ id: 'old', entity: 'Old search', value: 'old marker' }], total: 1 })
    await flushPromises()
    expect(wrapper.text()).toContain('new marker')
    expect(wrapper.text()).not.toContain('old marker')
  })
})
