import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import { ApiError } from '../src/api/client'
import { readCurrentGame, rememberCurrentGame } from '../src/stores/gameContext'
import LogsView from '../src/features/admin/LogsView.vue'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
}))

vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api }
})

describe('LogsView', () => {
  beforeEach(() => {
    const store = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, String(value)) },
      removeItem: (key: string) => { store.delete(key) },
      clear: () => { store.clear() },
    })
    mocks.api.mockReset()
    i18n.global.locale.value = 'zh-CN'
  })

  it('clears a stale save and shows a friendly empty state', async () => {
    rememberCurrentGame('missing-game')
    mocks.api.mockRejectedValue(new ApiError('not found', 404))

    const wrapper = mount(LogsView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(readCurrentGame()).toBe('')
    expect(wrapper.text()).toContain('还没有冒险记录')
    expect(wrapper.text().toLowerCase()).not.toContain('not found')
  })

  it('keeps a failed load recoverable with an explicit retry action', async () => {
    rememberCurrentGame('broken-game')
    mocks.api.mockRejectedValue(new Error('temporary outage'))

    const wrapper = mount(LogsView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find('.logs-error').exists()).toBe(true)
    expect(wrapper.find('.logs-error button').text()).toBe('重试')
  })

  it('ignores an older same-game page response that finishes after the latest request', async () => {
    rememberCurrentGame('race-game')
    let resolveOld!: (value: unknown) => void
    const oldPage = new Promise(resolve => { resolveOld = resolve })
    mocks.api.mockImplementation((url: string) => {
      const match = url.match(/per_page=(\d+)/)
      const size = Number(match?.[1] || 10)
      if (size === 20) return oldPage
      if (url.includes('/log?')) return Promise.resolve({ log: [{ round: 50, gm_response: 'latest page' }], total: 1 })
      if (url.includes('/games/') && !url.includes('/health') && !url.includes('/private-log')) return Promise.resolve({ world_id: '' })
      return Promise.resolve(url.includes('/health') ? {} : { messages: [] })
    })

    const wrapper = mount(LogsView, { global: { plugins: [i18n] } })
    await flushPromises()
    const selector = wrapper.find('.log-toolbar select')
    await selector.setValue('20')
    await selector.setValue('50')
    await flushPromises()
    expect(wrapper.text()).toContain('latest page')
    resolveOld({ log: [{ round: 20, gm_response: 'stale page' }], total: 1 })
    await flushPromises()
    expect(wrapper.text()).toContain('latest page')
    expect(wrapper.text()).not.toContain('stale page')
  })

  it('does not label a previous page log as the newly requested page after failure', async () => {
    rememberCurrentGame('page-scope-game')
    mocks.api.mockImplementation((url: string) => {
      if (url.includes('per_page=20')) return Promise.reject(new Error('page unavailable'))
      if (url.includes('/log?')) return Promise.resolve({ log: [{ round: 1, gm_response: 'page one marker' }], total: 1 })
      if (url.includes('/games/') && !url.includes('/health') && !url.includes('/private-log')) return Promise.resolve({ world_id: '' })
      return Promise.resolve(url.includes('/health') ? {} : { messages: [] })
    })

    const wrapper = mount(LogsView, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.text()).toContain('page one marker')
    await wrapper.find('.log-toolbar select').setValue('20')
    await flushPromises()
    expect(wrapper.text()).not.toContain('page one marker')
    expect(wrapper.text()).toContain('page unavailable')
  })
})
