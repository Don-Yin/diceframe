import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import { ROOM_TOKEN_REJECTED_EVENT, readRoomToken, readSeatToken, storeRoomToken } from '../src/utils/seatToken'

const GAME = 'web|room|bot'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))

vi.mock('../src/api/client', () => ({
  api: mocks.api,
  errorMessage: (error: unknown) => String((error as Error)?.message || error),
  retryOnRateLimit: <T>(request: () => Promise<T>) => request(),
}))
vi.mock('../src/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import JoinView from '../src/features/player/JoinView.vue'

const Blank = { template: '<div />' }

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/join', name: 'join', component: JoinView },
      { path: '/play', name: 'play', component: Blank },
      { path: '/', name: 'overview', component: Blank },
    ],
  })
}

function apiByPath(created: Record<string, unknown> = {}) {
  mocks.api.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path === `/games/${encodeURIComponent(GAME)}`) {
      return { game_key: GAME, world_name: 'World', multiplayer: { ready_players: [], waiting_players: [], away_players: [] } }
    }
    if (path.endsWith('/characters')) return { rule_attrs: [], rule_meta: {} }
    if (path.endsWith('/character-cards')) return { cards: [] }
    if (path.endsWith('/players') && init?.method === 'POST') return { ok: true, ...created }
    throw new Error(`unexpected ${path}`)
  })
}

async function mountAt(router: Router, query: Record<string, string>) {
  await router.push({ name: 'join', query })
  await router.isReady()
  const wrapper = mount(JoinView, {
    global: {
      plugins: [i18n, router],
      stubs: { PortraitPicker: true, BrandLogo: true, RulesetExperienceHost: true },
    },
  })
  await flushPromises()
  return wrapper
}

function playersCalls() {
  return mocks.api.mock.calls.filter(([path, init]) => String(path).endsWith('/players') && init?.method === 'POST')
}

describe('JoinView seat token', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    mocks.api.mockReset()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('stores a takeover link token, strips it from the URL, and rejoins with it', async () => {
    apiByPath({ user_id: 'p2', reused: true })
    const router = makeRouter()

    await mountAt(router, { game: GAME, share: '1', seat: 'tok-p2' })

    expect(readSeatToken(GAME)).toBe('tok-p2')
    const [call] = playersCalls()
    expect(call).toBeTruthy()
    expect(JSON.parse(String(call[1].body))).toEqual({ join_as_new: false })
    expect((call[1].headers as Record<string, string>)['X-Seat-Token']).toBe('tok-p2')
    expect(router.currentRoute.value.name).toBe('play')
    expect(router.currentRoute.value.query).toMatchObject({ game: GAME, user: 'p2', share: '1' })
    expect(JSON.stringify(router.currentRoute.value.query)).not.toContain('tok-p2')
    expect(localStorage.getItem('trpg_play_user_' + GAME)).toBe('p2')
  })

  it('treats an old uid-only takeover link as expired instead of rejoining that seat', async () => {
    apiByPath()
    const router = makeRouter()

    const wrapper = await mountAt(router, { game: GAME, share: '1', user: 'p2' })

    expect(playersCalls()).toHaveLength(0)
    expect(wrapper.text()).toContain(String(i18n.global.t('seatLinkExpired')))
    expect(readSeatToken(GAME)).toBe('')
  })

  it('stores the seat token returned for a newly created character', async () => {
    apiByPath({ user_id: 'p9', seat_token: 'tok-new' })
    const router = makeRouter()
    const wrapper = await mountAt(router, { game: GAME, share: '1' })

    await wrapper.get('.player-sheet-form input[maxlength="40"]').setValue('Aria')
    await wrapper.get('.player-sheet-form button.submit').trigger('click')
    await flushPromises()

    expect(readSeatToken(GAME)).toBe('tok-new')
    expect(router.currentRoute.value.query).toMatchObject({ user: 'p9' })
  })

  it('explains a missing seat credential when sent back from the play page', async () => {
    apiByPath()
    const router = makeRouter()

    const wrapper = await mountAt(router, { game: GAME, share: '1', notice: 'seat' })

    expect(wrapper.text()).toContain(String(i18n.global.t('seatTokenMissing')))
  })

  it('never rejoins without a seat token (e.g. storage blocked), so no new seat is created', async () => {
    apiByPath({ user_id: 'p-new' })
    // A browser that refuses to persist the seat token (private mode, quota).
    const values = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        if (key.startsWith('trpg_seat_token_')) throw new Error('blocked')
        values.set(key, String(value))
      },
      removeItem: (key: string) => { values.delete(key) },
      clear: () => values.clear(),
      key: () => null,
      length: 0,
    })
    const router = makeRouter()

    const wrapper = await mountAt(router, { game: GAME, share: '1', seat: 'tok-lost' })
    vi.unstubAllGlobals()

    expect(playersCalls()).toHaveLength(0)
    expect(wrapper.text()).toContain(String(i18n.global.t('seatTokenMissing')))
    expect(router.currentRoute.value.name).toBe('join')
  })

  it('shows the scene once the room password is verified', async () => {
    let verified = false
    mocks.api.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === `/games/${encodeURIComponent(GAME)}`) {
        return verified
          ? { game_key: GAME, world_name: 'World', has_room_password: true, scene: 'Harbor at midnight' }
          : { game_key: GAME, world_name: 'World', has_room_password: true }
      }
      if (path.endsWith('/verify-room-password') && init?.method === 'POST') {
        verified = true
        return { room_token: 'rt' }
      }
      if (path.endsWith('/characters')) return { rule_attrs: [], rule_meta: {} }
      if (path.endsWith('/character-cards')) return { cards: [] }
      throw new Error(`unexpected ${path}`)
    })
    const router = makeRouter()
    const wrapper = await mountAt(router, { game: GAME, share: '1' })
    expect(wrapper.text()).not.toContain('Harbor at midnight')

    await wrapper.get('.room-gate input[type="password"]').setValue('secret')
    await wrapper.get('.room-gate button.submit').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Harbor at midnight')
  })

  it('asks a returning member for the room password first, then enters play', async () => {
    localStorage.setItem('trpg_play_user_' + GAME, 'p1')
    let verified = false
    mocks.api.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === `/games/${encodeURIComponent(GAME)}`) {
        return { game_key: GAME, world_name: 'World', has_room_password: true, viewer: { kind: 'seat', uid: 'p1' } }
      }
      if (path.endsWith('/verify-room-password') && init?.method === 'POST') {
        verified = true
        return { room_token: 'rt-new', expires_at: '2099-01-01T00:00:00+00:00' }
      }
      throw new Error(`unexpected ${path}`)
    })
    const router = makeRouter()
    const wrapper = await mountAt(router, { game: GAME, share: '1', notice: 'room' })

    expect(router.currentRoute.value.name).toBe('join')
    expect(wrapper.find('.room-gate').exists()).toBe(true)
    expect(wrapper.text()).toContain(String(i18n.global.t('roomAccessExpired')))

    await wrapper.get('.room-gate input[type="password"]').setValue('secret')
    await wrapper.get('.room-gate button.submit').trigger('click')
    await flushPromises()

    expect(verified).toBe(true)
    expect(readRoomToken(GAME)).toBe('rt-new')
    expect(router.currentRoute.value.name).toBe('play')
    expect(router.currentRoute.value.query).toMatchObject({ game: GAME, user: 'p1', share: '1' })
    expect(localStorage.getItem('trpg_play_user_' + GAME)).toBe('p1')
  })

  it('re-opens the password prompt when the held room token is refused mid-join', async () => {
    storeRoomToken(GAME, 'rt-stale')
    apiByPath()
    const router = makeRouter()
    const wrapper = await mountAt(router, { game: GAME, share: '1' })
    expect(wrapper.find('.room-gate').exists()).toBe(false)

    window.dispatchEvent(new CustomEvent(ROOM_TOKEN_REJECTED_EVENT, { detail: { gameKey: 'web|other|bot' } }))
    await flushPromises()
    expect(wrapper.find('.room-gate').exists()).toBe(false)

    window.dispatchEvent(new CustomEvent(ROOM_TOKEN_REJECTED_EVENT, { detail: { gameKey: GAME } }))
    await flushPromises()
    expect(wrapper.find('.room-gate').exists()).toBe(true)
    expect(wrapper.text()).toContain(String(i18n.global.t('roomAccessExpired')))
    wrapper.unmount()
  })

  it('sends the room password exactly as typed (never trimmed)', async () => {
    const sent: string[] = []
    mocks.api.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === `/games/${encodeURIComponent(GAME)}`) return { game_key: GAME, world_name: 'World', has_room_password: true }
      if (path.endsWith('/verify-room-password') && init?.method === 'POST') {
        sent.push(JSON.parse(String(init.body)).password)
        throw new Error('wrong')
      }
      throw new Error(`unexpected ${path}`)
    })
    const router = makeRouter()
    const wrapper = await mountAt(router, { game: GAME, share: '1' })
    await wrapper.get('.room-gate input[type="password"]').setValue('  spaced pass  ')
    await wrapper.get('.room-gate button.submit').trigger('click')
    await flushPromises()
    expect(sent).toEqual(['  spaced pass  '])
  })
})
