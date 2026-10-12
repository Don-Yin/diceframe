import { flushPromises, mount } from '@vue/test-utils'
import type { Mock } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import type { GameDetail, Player } from '../src/api/types'
import { gameState } from './helpers/playViewGame'

const GAME_KEY = 'web|combat|bot'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  fetchRulesetAvailableActions: vi.fn(),
  confirm: vi.fn(),
  resolveGameSceneImageUrl: vi.fn(),
}))

vi.mock('../src/composables/useGame', async () => {
  const helper = await import('./helpers/playViewGame')
  return { useGame: helper.useGame }
})
vi.mock('../src/api/client', () => ({
  api: mocks.api,
  apiBlob: vi.fn(),
  hasAccessToken: () => false,
  isNotFoundError: (error: unknown) => Boolean((error as { status?: number })?.status === 404),
  retryOnRateLimit: <T>(request: () => Promise<T>) => request(),
}))
vi.mock('../src/api/rulesets', () => ({
  fetchRulesetAvailableActions: mocks.fetchRulesetAvailableActions,
}))
vi.mock('../src/api/sceneImages', () => ({
  fileToBase64: vi.fn(),
  resolveGameSceneImageUrl: mocks.resolveGameSceneImageUrl,
  revokeSceneImageUrl: vi.fn(),
  sceneImageStyle: () => ({}),
}))
vi.mock('../src/api/generatedImages', () => ({ generateCurrentRoundImage: vi.fn() }))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))
vi.mock('../src/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: mocks.confirm }),
}))
vi.mock('../src/stores/useSettingsStore', () => ({
  useSettingsStore: () => ({
    config: { public_base_url: '', imagegen_manual_scene: false, imagegen_auto_storyboard: false },
    loading: false,
    load: vi.fn(async () => undefined),
  }),
}))

import PlayView from '../src/features/play/PlayView.vue'

const STUBS = {
  Teleport: true,
  GameSidebar: true,
  KpQuestionDialog: true,
  MapBackgroundSettingsModal: true,
  RulesetPlayHost: true,
  DirectorProposalCard: true,
  GameTimeline: true,
  EconomyProposalCard: true,
  TableTalkFeed: true,
  GmToolbar: true,
  MultiplayerPanel: true,
  HealthPanel: true,
  ManualRollsPanel: true,
  MapWorkspace: true,
  SceneGalleryModal: true,
  CurrentRoundImageModal: true,
  PlayHelpCenter: true,
  InviteQrModal: true,
  GmChargeComposer: true,
  PortraitPicker: true,
  AdventureSceneImagePicker: true,
  RulesetCharacterCenterHost: true,
}

import { readSeatToken, storeSeatToken } from '../src/utils/seatToken'

async function mountPlayView(query: Record<string, string>) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'overview', component: { template: '<div />' } },
      { path: '/join', name: 'join', component: { template: '<div />' } },
      { path: '/characters', name: 'characters', component: { template: '<div />' } },
      { path: '/play', name: 'play', component: PlayView },
    ],
  })
  await router.push({ name: 'play', query })
  await router.isReady()
  const wrapper = mount(PlayView, { global: { plugins: [i18n, router], stubs: STUBS } })
  await flushPromises()
  return { wrapper, router }
}

const CLAIM_PATH = `/games/${encodeURIComponent(GAME_KEY)}/seat-token/claim`
const memberDetail = {
  game_key: GAME_KEY,
  state: 'active_action',
  multiplayer: { ready_players: [{ user_id: 'ally' }], waiting_players: [], away_players: [] },
} as unknown as GameDetail

function claimCalls() {
  return (mocks.api as unknown as Mock).mock.calls.filter(([path]) => path === CLAIM_PATH)
}

describe('PlayView seat token migration', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    gameState.detail.value = memberDetail
    gameState.players.value = [{ user_id: 'ally', character_name: 'Ally' } as Player]
    gameState.isGm.value = false
    gameState.userId.value = 'ally'
    gameState.currentGame.value = GAME_KEY
    ;(mocks.api as unknown as Mock).mockReset().mockImplementation(async (path: string) => {
      if (path === CLAIM_PATH) return { ok: true, user_id: 'ally', seat_token: 'tok-claimed' }
      if (path === `/games/${encodeURIComponent(GAME_KEY)}`) return memberDetail
      return {}
    })
    mocks.fetchRulesetAvailableActions.mockReset().mockResolvedValue({})
    mocks.resolveGameSceneImageUrl.mockReset().mockResolvedValue('')
  })

  afterEach(() => {
    localStorage.clear()
    document.body.innerHTML = ''
  })

  it('claims the seat token once for a player bound before seat tokens existed', async () => {
    const { wrapper, router } = await mountPlayView({ game: GAME_KEY, user: 'ally', share: '1' })

    expect(claimCalls()).toHaveLength(1)
    expect(readSeatToken(GAME_KEY)).toBe('tok-claimed')
    expect(router.currentRoute.value.name).toBe('play')
    wrapper.unmount()
  })

  it('does not claim again when this browser already holds the seat token', async () => {
    storeSeatToken(GAME_KEY, 'tok-existing')

    const { wrapper } = await mountPlayView({ game: GAME_KEY, user: 'ally', share: '1' })

    expect(claimCalls()).toHaveLength(0)
    expect(readSeatToken(GAME_KEY)).toBe('tok-existing')
    wrapper.unmount()
  })

  it('sends the player to join when the seat cannot be claimed here', async () => {
    localStorage.setItem('trpg_play_user_' + GAME_KEY, 'ally')
    ;(mocks.api as unknown as Mock).mockImplementation(async (path: string) => {
      if (path === CLAIM_PATH) throw Object.assign(new Error('exists'), { status: 409, code: 'SEAT_TOKEN_EXISTS' })
      if (path === `/games/${encodeURIComponent(GAME_KEY)}`) return memberDetail
      return {}
    })

    const { wrapper, router } = await mountPlayView({ game: GAME_KEY, user: 'ally', share: '1' })

    expect(router.currentRoute.value.name).toBe('join')
    expect(router.currentRoute.value.query).toMatchObject({ game: GAME_KEY, notice: 'seat' })
    expect(localStorage.getItem('trpg_play_user_' + GAME_KEY)).toBeNull()
    expect(readSeatToken(GAME_KEY)).toBe('')
    wrapper.unmount()
  })
})

describe('PlayView takeover link', () => {
  const issuePath = `/games/${encodeURIComponent(GAME_KEY)}/players/p2/seat-token`
  const api = mocks.api as unknown as Mock

  function issueCalls() {
    return api.mock.calls.filter(([path]) => path === issuePath)
  }

  async function openTakeover(wrapper: Awaited<ReturnType<typeof mountPlayView>>['wrapper']) {
    wrapper.findComponent({ name: 'MultiplayerPanel' }).vm.$emit('copy-link', 'p2')
    await flushPromises()
    return wrapper.findComponent({ name: 'InviteQrModal' })
  }

  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    gameState.detail.value = { ...memberDetail, solo_mode: false, gm_uid: 'gm' } as GameDetail
    gameState.isGm.value = true
    gameState.userId.value = ''
    gameState.currentGame.value = GAME_KEY
    mocks.confirm.mockReset().mockResolvedValue(false)
    mocks.fetchRulesetAvailableActions.mockReset().mockResolvedValue({})
    mocks.resolveGameSceneImageUrl.mockReset().mockResolvedValue('')
  })

  afterEach(() => {
    localStorage.clear()
    document.body.innerHTML = ''
  })

  it('re-validates the cached link and reuses it while it is still current', async () => {
    api.mockReset().mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === issuePath) {
        const body = JSON.parse(String(init?.body))
        if (body.check === 'tok-1') return { ok: true, user_id: 'p2', seat_token: 'tok-1', reused: true }
        return { ok: true, user_id: 'p2', seat_token: 'tok-1' }
      }
      return {}
    })
    const { wrapper } = await mountPlayView({ game: GAME_KEY })

    const first = await openTakeover(wrapper)
    expect(first.props('seatToken')).toBe('tok-1')
    wrapper.findComponent({ name: 'InviteQrModal' }).vm.$emit('close')
    await flushPromises()
    const second = await openTakeover(wrapper)

    expect(second.props('seatToken')).toBe('tok-1')
    expect(issueCalls().map(([, init]) => JSON.parse(String(init?.body)))).toEqual([
      { rotate: false },
      { rotate: false, check: 'tok-1' },
    ])
    expect(mocks.confirm).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('offers a confirmed reissue when the cached link went stale elsewhere', async () => {
    let current = 'tok-1'
    api.mockReset().mockImplementation(async (path: string, init?: RequestInit) => {
      if (path !== issuePath) return {}
      const body = JSON.parse(String(init?.body))
      if (body.rotate) { current = 'tok-new'; return { ok: true, user_id: 'p2', seat_token: current } }
      if (body.check === current) return { ok: true, user_id: 'p2', seat_token: current, reused: true }
      if (body.check) throw Object.assign(new Error('in use'), { status: 409, code: 'SEAT_TOKEN_EXISTS' })
      return { ok: true, user_id: 'p2', seat_token: current }
    })
    const { wrapper } = await mountPlayView({ game: GAME_KEY })
    await openTakeover(wrapper)
    wrapper.findComponent({ name: 'InviteQrModal' }).vm.$emit('close')
    await flushPromises()

    current = 'tok-other-device'  // another GM device reissued the link
    mocks.confirm.mockResolvedValueOnce(true)
    const reopened = await openTakeover(wrapper)

    expect(mocks.confirm).toHaveBeenCalledOnce()
    expect(reopened.props('seatToken')).toBe('tok-new')
    wrapper.unmount()
  })

  it('rotates an existing seat link only after the GM confirms', async () => {
    api.mockReset().mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === issuePath) {
        const rotate = JSON.parse(String(init?.body)).rotate
        if (!rotate) throw Object.assign(new Error('exists'), { status: 409, code: 'SEAT_TOKEN_EXISTS' })
        return { ok: true, user_id: 'p2', seat_token: 'tok-rotated' }
      }
      return {}
    })
    const { wrapper } = await mountPlayView({ game: GAME_KEY })

    mocks.confirm.mockResolvedValueOnce(false)
    const declined = await openTakeover(wrapper)
    expect(declined.exists()).toBe(false)
    expect(issueCalls().map(([, init]) => JSON.parse(String(init?.body)).rotate)).toEqual([false])

    mocks.confirm.mockResolvedValueOnce(true)
    const confirmed = await openTakeover(wrapper)
    expect(confirmed.props('seatToken')).toBe('tok-rotated')
    expect(issueCalls().map(([, init]) => JSON.parse(String(init?.body)).rotate)).toEqual([false, false, true])
    wrapper.unmount()
  })
})
