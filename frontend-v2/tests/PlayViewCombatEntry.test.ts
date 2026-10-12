import { readFileSync } from 'node:fs'
import { join } from 'node:path'
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
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(false) }),
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

function combatExtensionDetail(overrides: Record<string, unknown> = {}): GameDetail {
  return {
    game_key: GAME_KEY,
    state: 'active_action',
    solo_mode: true,
    world_name: '测试世界',
    combat_extension: {
      scheduler: {
        kind: 'threshold',
        ready: ['player:ally'],
        gauges: { 'player:ally': 80, 'npc:boss': 100 },
      },
      entities: ['player:ally', 'npc:boss'],
      entity_names: { 'player:ally': '阿刃', 'npc:boss': '黑骑士' },
      pools: { 'player:ally': { hp: { current: 12, maximum: 12 } } },
      actions: [{ id: 'ability:qi_palm', kind: 'ability', name: '内力掌', costs: [] }],
    },
    ...overrides,
  } as unknown as GameDetail
}

async function mountPlayView(query: Record<string, string> = { game: GAME_KEY, user: 'ally' }) {
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

  const wrapper = mount(PlayView, {
    global: { plugins: [i18n, router], stubs: STUBS },
  })
  await flushPromises()
  return wrapper
}

describe('combat actions entry near the action composer', () => {
  const mockedApi = mocks.api as unknown as Mock
  const mockedAvailableActions = mocks.fetchRulesetAvailableActions as unknown as Mock

  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    gameState.detail.value = combatExtensionDetail()
    gameState.players.value = [{ user_id: 'ally', character_name: '阿刃' } as Player]
    gameState.isGm.value = false
    gameState.userId.value = 'ally'
    mockedApi.mockReset().mockResolvedValue({})
    mockedAvailableActions.mockReset().mockResolvedValue({})
    mocks.resolveGameSceneImageUrl.mockReset().mockResolvedValue('')
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('Case A: the ActionComposer tools bar shows 战斗动作 even without ruleset tools', async () => {
    // 自由规则只开启 combat_extension：没有专业工具、也不是 KP（不在名册里），
    // tools 栏仍必须因为 hasCombatExtension 出现。
    gameState.userId.value = ''
    gameState.players.value = []

    const wrapper = await mountPlayView()

    const tools = wrapper.get('.ruleset-context-tools')
    const trigger = tools.get('[data-testid="combat-extension-tool"]')
    expect(trigger.text()).toContain('战斗动作')
    // 名册为空 → 没有 KP 提问按钮；这条 tools 栏是 combat extension 单独撑起来的。
    expect(tools.find('.kp-question-tool-trigger').exists()).toBe(false)
    expect(wrapper.find('.composer').exists()).toBe(true)
    wrapper.unmount()
  })

  it('Case B: no combat_extension means no tools bar and no entry', async () => {
    gameState.userId.value = ''
    gameState.players.value = []
    gameState.detail.value = { game_key: GAME_KEY, state: 'active_action', solo_mode: true }

    const wrapper = await mountPlayView()

    expect(wrapper.find('[data-testid="combat-extension-tool"]').exists()).toBe(false)
    expect(wrapper.find('.ruleset-context-tools').exists()).toBe(false)
    wrapper.unmount()
  })

  it('Case C+D: a player opens the panel through the Modal and sees no GM controls', async () => {
    const wrapper = await mountPlayView()

    expect(wrapper.find('.combat-ext').exists()).toBe(false)
    await wrapper.get('[data-testid="combat-extension-tool"]').trigger('click')
    await flushPromises()

    // 真正挂载了 CombatExtensionPanel：行动按钮与池展示来自该组件。
    expect(wrapper.find('.combat-ext').exists()).toBe(true)
    expect(wrapper.get('.combat-ext').text()).toContain('内力掌')

    // 普通玩家：只看到自己的池，没有 actor selector，也没有推进调度器。
    expect(wrapper.get('.combat-ext').text()).toContain('12 / 12')
    expect(wrapper.find('.combat-ext-scheduler-head button').exists()).toBe(false)
    expect(wrapper.get('.combat-ext').text()).not.toContain('行动实体')
    // 目标选择器有且只有行动本身那一个（GM 会多出 actor selector）。
    expect(wrapper.findAll('.combat-ext-action select')).toHaveLength(1)
    wrapper.unmount()
  })

  it('Case E: a GM additionally sees the actor selector and the scheduler advance', async () => {
    gameState.isGm.value = true
    const wrapper = await mountPlayView()

    await wrapper.get('[data-testid="combat-extension-tool"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('.combat-ext').text()).toContain('行动实体')
    const advance = wrapper.get('.combat-ext-scheduler-head button')
    expect(advance.text()).toBe('推进时间')
    // actor selector + 行动目标 selector
    expect(wrapper.findAll('.combat-ext-action select')).toHaveLength(2)

    await advance.trigger('click')
    await flushPromises()
    expect(String(mockedApi.mock.calls.at(-1)?.[0])).toContain('/combat/scheduler/advance')
    wrapper.unmount()
  })

  it('Case F: the controls rail no longer renders CombatExtensionPanel persistently', async () => {
    gameState.isGm.value = true
    gameState.detail.value = combatExtensionDetail({ solo_mode: false })

    const wrapper = await mountPlayView()

    // GM controls rail 存在，但里面没有常驻的战斗扩展面板；面板只在入口打开后出现。
    expect(wrapper.find('.play-control-rail').exists()).toBe(true)
    expect(wrapper.find('.play-control-rail .combat-ext').exists()).toBe(false)
    expect(wrapper.findAll('.combat-ext')).toHaveLength(0)

    // 源码契约：右侧 controls rail 里不再直接渲染 CombatExtensionPanel。
    const source = readFileSync(join(process.cwd(), 'src/features/play/PlayView.vue'), 'utf8')
    const railStart = source.indexOf('class="play-control-rail"')
    const railSource = source.slice(railStart, source.indexOf('</aside>', railStart))
    expect(railSource).not.toContain('<CombatExtensionPanel')
    expect(railSource).toContain('<GmToolbar')
    wrapper.unmount()
  })

  it('Case G: the CombatMessageComposer tools slot has the same entry', async () => {
    gameState.detail.value = combatExtensionDetail({
      solo_mode: false,
      ruleset_runtime: {
        id: 'dnd2024',
        capabilities: { authoritative_intents: true, deterministic_combat: true },
      },
    })
    mockedAvailableActions.mockResolvedValue({
      gameplay: { state_version: 3, combat: { status: 'active' } },
    })

    const wrapper = await mountPlayView()

    expect(wrapper.find('.combat-message-composer').exists()).toBe(true)
    expect(wrapper.find('.composer').exists()).toBe(false)
    const trigger = wrapper.get('.combat-message-composer [data-testid="combat-extension-tool"]')
    expect(trigger.text()).toContain('战斗动作')

    // 该入口在战斗发言模式下同样真的能打开面板。
    await trigger.trigger('click')
    await flushPromises()
    expect(wrapper.get('.combat-ext').text()).toContain('内力掌')
    wrapper.unmount()
  })
})
