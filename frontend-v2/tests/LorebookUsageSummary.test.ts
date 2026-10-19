import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LorebookUsageSummary from '../src/features/lorebook/LorebookUsageSummary.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api, errorMessage: (cause: unknown) => String((cause as Error)?.message || cause) }
})

function book(id: string, enabled = true) {
  return { id, name: id, enabled, scope: 'world', entry_count: 2 }
}
function response(status: 'none' | 'ready' | 'unavailable' = 'ready') {
  return {
    ok: true,
    library: { total: 4, enabled: 3, disabled: 1, books: [book('enabled-a'), book('enabled-b'), book('enabled-c'), book('disabled-d', false)] },
    game: { status, game_key: status === 'none' ? '' : 'g1', world_id: 'w1', world_name: '活动世界', count: status === 'ready' ? 1 : null, books: status === 'ready' ? [book('enabled-a')] : [] },
  }
}

describe('LorebookUsageSummary', () => {
  beforeEach(() => {
    mocks.api.mockReset()
    mocks.api.mockResolvedValue(response())
    i18n.global.locale.value = 'zh-CN'
  })

  it('renders library enabled count separately from actual game book count and lists source books', async () => {
    const wrapper = mount(LorebookUsageSummary, { props: { gameKey: 'g1', viewer: 'gm' }, global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.text()).toContain('资料库已启用 3 / 4 本')
    expect(wrapper.text()).toContain('本局使用 1 本')
    expect(wrapper.text()).toContain('活动世界')
    expect(wrapper.text()).toContain('enabled-a')
    expect(wrapper.text()).toContain('disabled-d')
    // The library contains all worlds: its scope labels cannot imply the current world.
    expect(wrapper.text()).toContain('范围: 世界')
    expect(wrapper.text()).not.toContain('范围: 当前世界')
    expect(String(mocks.api.mock.calls[0]?.[0])).toContain('game_key=g1')
    expect(String(mocks.api.mock.calls[0]?.[0])).toContain('viewer=gm')
  })

  it('distinguishes no selected game from unavailable game without showing zero', async () => {
    mocks.api.mockResolvedValueOnce(response('none'))
    const none = mount(LorebookUsageSummary, { props: { gameKey: '' }, global: { plugins: [i18n] } })
    await flushPromises()
    expect(none.text()).toContain('未选择对局')
    expect(none.text()).not.toContain('本局使用 0 本')

    mocks.api.mockResolvedValueOnce(response('unavailable'))
    const unavailable = mount(LorebookUsageSummary, { props: { gameKey: 'g1' }, global: { plugins: [i18n] } })
    await flushPromises()
    expect(unavailable.text()).toContain('无法确认本局资料')
    expect(unavailable.text()).not.toContain('本局使用 0 本')
  })

  it('shows retry on transport failure and fences late identity responses', async () => {
    let rejectFirst!: (cause: unknown) => void
    let resolveSecond!: (value: unknown) => void
    mocks.api.mockImplementationOnce(() => new Promise((_, reject) => { rejectFirst = reject }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))
    const wrapper = mount(LorebookUsageSummary, { props: { gameKey: 'g1' }, global: { plugins: [i18n] } })
    rejectFirst(new Error('offline'))
    await flushPromises()
    expect(wrapper.text()).toContain('offline')
    await wrapper.get('button').trigger('click')
    resolveSecond(response())
    await flushPromises()
    expect(wrapper.text()).toContain('资料库已启用 3 / 4 本')

    let resolveA!: (value: unknown) => void
    let resolveB!: (value: unknown) => void
    mocks.api.mockReset()
    mocks.api.mockImplementation((path: string) => new Promise(resolve => {
      if (String(path).includes('game_key=a')) resolveA = resolve
      else resolveB = resolve
    }))
    await wrapper.setProps({ gameKey: 'a', refreshToken: 1 })
    await wrapper.setProps({ gameKey: 'b', refreshToken: 2 })
    expect(wrapper.text()).not.toContain('资料库已启用 3 / 4 本')
    resolveA(response())
    await flushPromises()
    expect(wrapper.find('.lorebook-usage-card').exists()).toBe(false)
    resolveB(response())
    await flushPromises()
    expect(wrapper.find('.lorebook-usage-card').exists()).toBe(true)
  })
})
