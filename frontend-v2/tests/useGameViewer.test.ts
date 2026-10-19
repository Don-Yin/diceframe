import { defineComponent } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { useGame } from '../src/composables/useGame'

const mocks = vi.hoisted(() => ({ route: { query: {} as Record<string, string> }, authenticated: true, api: vi.fn(), events: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => mocks.route }))
vi.mock('../src/api/client', () => ({ api: mocks.api, hasAccessToken: () => mocks.authenticated, isNotFoundError: () => false, isPlayerAccessClosedError: () => false, gameEventSource: mocks.events }))
beforeEach(() => {
  mocks.route.query = { game: 'web|viewer|bot' }; mocks.authenticated = true
  mocks.api.mockImplementation(async (path: string) => path.endsWith('/characters') ? { players: [{ user_id: 'gm', character_name: 'Keeper' }, { user_id: 'p1', character_name: 'Investigator' }] }
    : path.endsWith('/map') ? { locations: [] } : path.endsWith('/log') ? { log: [] }
    : path.endsWith('/private-log') ? { messages: [] } : path.endsWith('/table-talk') ? { exchanges: [] }
    : { gm_uid: 'gm', world_id: '', world_name: 'Viewer game' })
})
async function loaded() {
  let game!: ReturnType<typeof useGame>
  const wrapper = mount(defineComponent({ setup() { game = useGame(); return () => null } }))
  await game.refresh()
  return { game, wrapper }
}
it('an authenticated owner using a player preview has only the selected player role and identity', async () => {
  mocks.route.query = { ...mocks.route.query, user: 'p1', share: '1' }
  const { game, wrapper } = await loaded()
  expect(game.actorId.value).toBe('p1')
  expect(game.isGm.value).toBe(false)
  wrapper.unmount()
})
it('the authenticated owner without a player override retains the GM role', async () => {
  const { game, wrapper } = await loaded()
  expect(game.isGm.value).toBe(true)
  expect(game.actorId.value).toBe('gm')
  wrapper.unmount()
})
it('an ordinary shared player keeps its own actor and cannot inherit the saved GM role', async () => {
  mocks.authenticated = false; mocks.route.query.user = 'p1'
  const { game, wrapper } = await loaded()
  expect(game.isGm.value).toBe(false)
  expect(game.actorId.value).toBe('p1')
  wrapper.unmount()
})

it('ignores an older refresh response after the viewer changes', async () => {
  const firstDetail = deferred<Record<string, unknown>>()
  const secondDetail = deferred<Record<string, unknown>>()
  let detailCalls = 0
  mocks.route.query = { game: 'web|viewer|bot', user: 'p1', share: '1' }
  mocks.api.mockImplementation(async (path: string) => {
    if (path === '/games/web%7Cviewer%7Cbot') return (++detailCalls === 1 ? firstDetail.promise : secondDetail.promise)
    return path.endsWith('/characters') ? { players: [] }
      : path.endsWith('/map') ? { locations: [] }
        : path.endsWith('/log') ? { log: [] }
          : path.endsWith('/private-log') ? { messages: [] }
            : path.endsWith('/table-talk') ? { exchanges: [] }
              : { gm_uid: 'gm', world_id: '', world_name: 'fallback' }
  })
  let game!: ReturnType<typeof useGame>
  const wrapper = mount(defineComponent({ setup() { game = useGame(); return () => null } }))
  const oldRefresh = game.refresh()
  game.userId.value = 'p2'
  const newRefresh = game.refresh()
  await flushPromises()
  secondDetail.resolve({ gm_uid: 'gm', world_id: '', world_name: 'new viewer' })
  await flushPromises()
  firstDetail.resolve({ gm_uid: 'gm', world_id: '', world_name: 'old viewer' })
  expect(await newRefresh).toBe(true)
  expect(await oldRefresh).toBe(false)
  await flushPromises()
  expect(game.userId.value).toBe('p2')
  expect(game.detail.value?.world_name).toBe('new viewer')
  wrapper.unmount()
})

it('ignores an older refresh response after the game changes', async () => {
  const firstDetail = deferred<Record<string, unknown>>()
  const secondDetail = deferred<Record<string, unknown>>()
  let detailCalls = 0
  let game!: ReturnType<typeof useGame>
  mocks.api.mockImplementation(async (path: string) => {
    if (path.startsWith('/games/') && !path.endsWith('/characters') && !path.endsWith('/log') && !path.endsWith('/private-log') && !path.endsWith('/table-talk') && !path.endsWith('/map')) {
      return (++detailCalls === 1 ? firstDetail.promise : secondDetail.promise)
    }
    return path.endsWith('/characters') ? { players: [] }
      : path.endsWith('/map') ? { locations: [] }
        : path.endsWith('/log') ? { log: [] }
          : path.endsWith('/private-log') ? { messages: [] }
            : path.endsWith('/table-talk') ? { exchanges: [] }
              : { gm_uid: 'gm', world_id: '', world_name: 'fallback' }
  })
  const wrapper = mount(defineComponent({ setup() { game = useGame(); return () => null } }))
  const oldRefresh = game.refresh()
  game.currentGame.value = 'web|new-viewer|bot'
  const newRefresh = game.refresh()
  secondDetail.resolve({ gm_uid: 'gm', world_id: '', world_name: 'new game' })
  await flushPromises()
  firstDetail.resolve({ gm_uid: 'gm', world_id: '', world_name: 'old game' })
  expect(await newRefresh).toBe(true)
  expect(await oldRefresh).toBe(false)
  await flushPromises()
  expect(game.currentGame.value).toBe('web|new-viewer|bot')
  expect(game.detail.value?.world_name).toBe('new game')
  wrapper.unmount()
})

it('clears foreground loading when a newer silent refresh wins the same context', async () => {
  const firstDetail = deferred<Record<string, unknown>>()
  const secondDetail = deferred<Record<string, unknown>>()
  let detailCalls = 0
  mocks.api.mockImplementation(async (path: string) => {
    if (path === '/games/web%7Cviewer%7Cbot') return (++detailCalls === 1 ? firstDetail.promise : secondDetail.promise)
    return path.endsWith('/characters') ? { players: [] }
      : path.endsWith('/map') ? { locations: [] }
        : path.endsWith('/log') ? { log: [], check_reveals: {} }
          : path.endsWith('/private-log') ? { messages: [] }
            : path.endsWith('/table-talk') ? { exchanges: [] }
              : { gm_uid: 'gm', world_id: '', world_name: 'fallback' }
  })
  let game!: ReturnType<typeof useGame>
  const wrapper = mount(defineComponent({ setup() { game = useGame(); return () => null } }))
  const foreground = game.refresh()
  const silent = game.refresh(true)
  secondDetail.resolve({ gm_uid: 'gm', world_id: '', world_name: 'latest' })
  await silent
  firstDetail.resolve({ gm_uid: 'gm', world_id: '', world_name: 'stale' })
  await foreground
  expect(game.detail.value?.world_name).toBe('latest')
  expect(game.loading.value).toBe(false)
  wrapper.unmount()
})

it('returns false for a silent failure while preserving an existing error', async () => {
  let game!: ReturnType<typeof useGame>
  const wrapper = mount(defineComponent({ setup() { game = useGame(); return () => null } }))
  expect(await game.refresh()).toBe(true)
  game.error.value = 'previous error'
  mocks.api.mockRejectedValue(new Error('silent failure'))

  expect(await game.refresh(true)).toBe(false)
  expect(game.error.value).toBe('previous error')
  wrapper.unmount()
})

it('returns false when refresh starts without a current game', async () => {
  let game!: ReturnType<typeof useGame>
  const wrapper = mount(defineComponent({ setup() { game = useGame(); return () => null } }))
  mocks.api.mockClear()
  game.currentGame.value = ''

  expect(await game.refresh()).toBe(false)
  expect(mocks.api).not.toHaveBeenCalled()
  wrapper.unmount()
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

it('coalesces lifecycle notifications while a snapshot is loading instead of starving its publication', async () => {
  vi.useFakeTimers()
  const source = { onmessage: null as ((event: MessageEvent) => void) | null, onopen: null, onerror: null, close: vi.fn(), addEventListener: vi.fn() }
  mocks.events.mockResolvedValue(source)
  const { game, wrapper } = await loaded()
  try {
    await game.connect()
    const map = deferred<{ locations: never[] }>()
    let mapCalls = 0
    const original = mocks.api.getMockImplementation()!
    mocks.api.mockImplementation(async (path: string) => path.endsWith('/map') ? (++mapCalls === 1 ? map.promise : { locations: [] })
      : path === '/games/web%7Cviewer%7Cbot' ? { gm_uid: 'gm', world_id: '', world_name: 'Viewer game', state: 'ended' } : original(path))
    source.onmessage!(new MessageEvent('message', { data: '{"type":"run_story_changed"}' }))
    await vi.advanceTimersByTimeAsync(120)
    source.onmessage!(new MessageEvent('message', { data: '{"type":"refresh"}' }))
    await vi.advanceTimersByTimeAsync(120)
    expect(mapCalls).toBe(1)
    map.resolve({ locations: [] })
    await flushPromises()
    expect(game.detail.value?.state).toBe('ended')
    await vi.advanceTimersByTimeAsync(120)
    expect(mapCalls).toBe(2)
  } finally { wrapper.unmount(); vi.useRealTimers() }
})
