import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import { ApiError } from '../src/api/client'

const GAME_KEY = 'web|closed|web'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  gameEventSource: vi.fn(),
  peer: vi.fn(),
}))

vi.mock('../src/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/api/client')>()),
  api: mocks.api,
  gameEventSource: mocks.gameEventSource,
  hasAccessToken: () => false,
}))
vi.mock('../src/peer/game/bridge', () => ({ activePeerGameClient: mocks.peer }))
vi.mock('../src/api/mapBackgrounds', () => ({
  resolveMapBackgroundAsset: async (map: unknown) => map,
  revokeMapBackgroundAsset: () => undefined,
}))

import { useGame } from '../src/composables/useGame'

class FakeEventSource {
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {}
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    (this.listeners[type] ||= []).push(listener)
  }
  emit(type: string, data: unknown) {
    for (const listener of this.listeners[type] || []) {
      listener(new MessageEvent(type, { data: JSON.stringify(data) }))
    }
  }
  close() { this.closed = true }
}

function closedError() {
  return new ApiError('本局玩家入口已关闭', 403, 'PLAYER_ACCESS_CLOSED')
}

function okApi(path: string) {
  if (path.endsWith('/characters')) return Promise.resolve({ players: [] })
  if (path.endsWith('/log')) return Promise.resolve({ log: [] })
  if (path.endsWith('/private-log')) return Promise.resolve({ messages: [] })
  if (path.endsWith('/table-talk')) return Promise.resolve({ exchanges: [] })
  if (path.endsWith('/map')) return Promise.resolve({ locations: [] })
  return Promise.resolve({ game_key: GAME_KEY, gm_uid: 'gm' })
}

async function mountGame() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/play', component: { template: '<div />' } }],
  })
  await router.push(`/play?game=${encodeURIComponent(GAME_KEY)}&user=p1&share=1`)
  let game!: ReturnType<typeof useGame>
  const Host = defineComponent({
    setup() {
      game = useGame()
      return () => null
    },
  })
  const wrapper = mount(Host, { global: { plugins: [router, i18n] } })
  return { wrapper, game: () => game }
}

describe('useGame with a closed player entrance', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    i18n.global.locale.value = 'en'
    mocks.api.mockReset()
    mocks.gameEventSource.mockReset()
    mocks.peer.mockReset()
    mocks.peer.mockReturnValue(null)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the closed-entrance notice and stops reconnecting until retried', async () => {
    mocks.api.mockImplementation(() => Promise.reject(closedError()))
    mocks.gameEventSource.mockImplementation(() => Promise.reject(closedError()))
    const { wrapper, game } = await mountGame()

    await game().refresh()
    await game().connect()
    await flushPromises()

    expect(game().accessClosed.value).toBe(true)
    expect(game().error.value).toBe(i18n.global.t('apiErrors.PLAYER_ACCESS_CLOSED'))
    const apiCalls = mocks.api.mock.calls.length
    const sseCalls = mocks.gameEventSource.mock.calls.length

    await vi.advanceTimersByTimeAsync(120_000)
    expect(mocks.api.mock.calls.length).toBe(apiCalls)
    expect(mocks.gameEventSource.mock.calls.length).toBe(sseCalls)

    // The GM reopened the entrance; the player's retry resumes the table.
    mocks.api.mockImplementation(okApi)
    mocks.gameEventSource.mockImplementation(async () => new FakeEventSource())
    await game().retryAccess()
    await flushPromises()
    expect(game().accessClosed.value).toBe(false)
    expect(game().error.value).toBe('')
    expect(mocks.gameEventSource.mock.calls.length).toBe(sseCalls + 1)
    wrapper.unmount()
  })

  it('stops when an open stream is revoked because the entrance closed', async () => {
    mocks.api.mockImplementation(okApi)
    const stream = new FakeEventSource()
    mocks.gameEventSource.mockImplementation(async () => stream)
    const { wrapper, game } = await mountGame()
    await game().refresh()
    await game().connect()
    await flushPromises()

    stream.emit('revoked', { error_code: 'PLAYER_ACCESS_CLOSED', error: '本局玩家入口已关闭' })
    stream.onerror?.()
    await flushPromises()

    expect(stream.closed).toBe(true)
    expect(game().accessClosed.value).toBe(true)
    expect(game().error.value).toBe(i18n.global.t('apiErrors.PLAYER_ACCESS_CLOSED'))
    const apiCalls = mocks.api.mock.calls.length
    await vi.advanceTimersByTimeAsync(120_000)
    expect(mocks.gameEventSource).toHaveBeenCalledTimes(1)
    expect(mocks.api.mock.calls.length).toBe(apiCalls)
    wrapper.unmount()
  })

  it('stops polling a P2P table whose host closed the entrance', async () => {
    const unsubscribe = vi.fn()
    mocks.peer.mockReturnValue({ gameKey: GAME_KEY, subscribe: () => unsubscribe })
    // The bridge reports a closed entrance as a bare error code.
    mocks.api.mockImplementation(() => Promise.reject(new Error('player_access_closed')))
    const { wrapper, game } = await mountGame()

    await game().refresh()
    await game().connect()
    await flushPromises()

    expect(game().accessClosed.value).toBe(true)
    expect(game().error.value).toBe(i18n.global.t('apiErrors.PLAYER_ACCESS_CLOSED'))
    const apiCalls = mocks.api.mock.calls.length
    await vi.advanceTimersByTimeAsync(120_000)
    expect(mocks.api.mock.calls.length).toBe(apiCalls)
    wrapper.unmount()
  })
})
