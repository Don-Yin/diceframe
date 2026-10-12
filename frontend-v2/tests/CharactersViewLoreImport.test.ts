import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CharactersView from '../src/features/admin/CharactersView.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  apiBlob: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
  confirm: vi.fn(async () => true),
}))

vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return {
    ...actual,
    api: mocks.api,
    apiBlob: mocks.apiBlob,
    errorMessage: (cause: unknown) => String((cause as Error)?.message || cause),
  }
})
vi.mock('../src/stores/gameContext', () => ({ readCurrentGame: () => '' }))
vi.mock('../src/composables/useToast', () => ({ useToast: () => mocks.toast }))
vi.mock('../src/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: mocks.confirm }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))

function tavernCardFile() {
  const payload = {
    spec: 'chara_card_v2',
    data: { name: 'Alice', description: 'Scout', character_book: { name: 'Alice lore', entries: [{ keys: ['gate'], content: 'gate lore' }] } },
  }
  return new File([JSON.stringify(payload)], 'alice.json', { type: 'application/json' })
}

async function openImportModal(includeLore: boolean) {
  const wrapper = mount(CharactersView, { global: { plugins: [i18n], stubs: { teleport: true } } })
  await flushPromises()
  await flushPromises()

  const openButton = wrapper.findAll('button').find(item => item.text() === '导入酒馆卡')
  expect(openButton).toBeTruthy()
  await openButton!.trigger('click')
  await flushPromises()

  await wrapper.get('.check-row input[value=character_card]').setValue(true)
  const checkbox = wrapper.get('.tavern-include-lore')
  await checkbox.setValue(includeLore)
  return wrapper
}

async function importFile(wrapper: ReturnType<typeof mount>) {
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { value: [tavernCardFile()], configurable: true })
  await input.trigger('change')
  // FileReader 完成时机晚于一次 microtask flush，等真正的请求出现再断言。
  await vi.waitFor(() => {
    expect(mocks.api.mock.calls.some(([path]) => String(path) === '/character-cards/import')).toBe(true)
  })
  await flushPromises()
}

function importBody() {
  const call = mocks.api.mock.calls.find(([path]) => String(path) === '/character-cards/import')
  expect(call, 'character card import request').toBeTruthy()
  return JSON.parse(String((call![1] as { body: string }).body)) as Record<string, unknown>
}

describe('CharactersView character card lore import', () => {
  beforeEach(() => {
    localStorage.clear()
    i18n.global.locale.value = 'zh-CN'
    mocks.api.mockReset()
    Object.values(mocks.toast).forEach(fn => fn.mockReset())
    mocks.api.mockImplementation(async (path: string) => {
      const p = String(path)
      if (p === '/character-cards') return { cards: [] }
      if (p === '/rules') return { rules: [] }
      if (p === '/worlds') return { worlds: [] }
      if (p === '/character-cards/import') {
        return { ok: true, card: { id: 'c1', character_name: 'Alice' }, lorebook: { book_id: 'character_card:c1', name: 'Alice', entries: 3 } }
      }
      return { ok: true }
    })
  })

  it('sends include_character_book=false only when the checkbox is cleared', async () => {
    const wrapper = await openImportModal(false)
    await importFile(wrapper)

    expect(importBody().include_character_book).toBe(false)
    expect(importBody().target).toBe('character_card')
  })

  it('keeps the embedded lore by default', async () => {
    const wrapper = await openImportModal(true)
    await importFile(wrapper)

    expect(importBody().include_character_book).toBe(true)
  })

  it('surfaces the committed lorebook name and entry count', async () => {
    const wrapper = await openImportModal(true)
    await importFile(wrapper)

    await vi.waitFor(() => {
      expect(mocks.toast.success.mock.calls.map(([value]) => String(value)).join(' | ')).toContain('Alice')
    })
    const message = mocks.toast.success.mock.calls.map(([value]) => String(value)).join(' | ')
    expect(message).toContain('3')
  })

  it('does not offer the toggle when importing as an NPC', async () => {
    const wrapper = mount(CharactersView, { global: { plugins: [i18n], stubs: { teleport: true } } })
    await flushPromises()
    await flushPromises()
    const openButton = wrapper.findAll('button').find(item => item.text() === '导入酒馆卡')
    await openButton!.trigger('click')
    await flushPromises()

    expect(wrapper.find('.tavern-include-lore').exists()).toBe(false)
  })
})
