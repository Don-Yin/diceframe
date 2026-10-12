import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('../src/api/client', () => ({ api: mocks.api }))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: mocks.success, error: mocks.error, info: vi.fn(), warning: vi.fn() }),
}))

import CombatActionsTool from '../src/components/play/CombatActionsTool.vue'

const GAME_KEY = 'web|room|bot'

function detail(combatExtension: boolean, overrides: Record<string, unknown> = {}) {
  return {
    game_key: GAME_KEY,
    state: 'active_action',
    combat_extension: combatExtension
      ? {
          scheduler: {
            kind: 'threshold',
            ready: ['player:ally'],
            gauges: { 'player:ally': 80, 'npc:boss': 100 },
          },
          entities: ['player:ally', 'npc:boss'],
          entity_names: { 'player:ally': '阿刃', 'npc:boss': '黑骑士' },
          pools: { 'player:ally': { hp: { current: 12, maximum: 12 } } },
          actions: [{ id: 'ability:qi_palm', kind: 'ability', name: '内力掌', costs: [] }],
          ...overrides,
        }
      : undefined,
  }
}

function tool(detailValue: ReturnType<typeof detail>, isGm: boolean) {
  return mount(CombatActionsTool, {
    global: { plugins: [i18n], stubs: { Teleport: true } },
    props: {
      detail: detailValue as never,
      gameKey: GAME_KEY,
      selfUid: 'ally',
      isGm,
    },
  })
}

describe('CombatActionsTool entry', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    mocks.api.mockReset()
    mocks.success.mockReset()
    mocks.error.mockReset()
  })

  it('Case A: shows 战斗动作 when the game declares combat_extension', () => {
    const wrapper = tool(detail(true), false)

    const trigger = wrapper.get('[data-testid="combat-extension-tool"]')
    expect(trigger.text()).toContain('战斗动作')
    // 入口只是按钮，面板此时还没有被挂载。
    expect(wrapper.find('.combat-ext').exists()).toBe(false)
    wrapper.unmount()
  })

  it('Case B: hides the entry when combat_extension is absent', () => {
    const wrapper = tool(detail(false), false)

    expect(wrapper.find('[data-testid="combat-extension-tool"]').exists()).toBe(false)
    expect(wrapper.find('.combat-ext').exists()).toBe(false)
    wrapper.unmount()
  })

  it('Case C: clicking the entry really mounts CombatExtensionPanel inside a Modal', async () => {
    const wrapper = tool(detail(true), false)

    await wrapper.get('[data-testid="combat-extension-tool"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('.modal .dialog').exists()).toBe(true)
    expect(wrapper.find('.modal .dialog h2').text()).toBe('战斗动作')
    // 真实面板内容：调度器、实体名与行动按钮都来自 CombatExtensionPanel。
    const panel = wrapper.get('.combat-ext')
    expect(panel.text()).toContain('内力掌')
    expect(panel.text()).toContain('阿刃')
    expect(panel.text()).toContain('黑骑士')
    wrapper.unmount()
  })

  it('Case D: a player sees no actor selector and no scheduler advance', async () => {
    const wrapper = tool(detail(true), false)

    await wrapper.get('[data-testid="combat-extension-tool"]').trigger('click')
    await flushPromises()

    // 行动目标选择器仍然存在（这是玩家要用的），但没有 GM 的 actor selector。
    expect(wrapper.findAll('.combat-ext-action select')).toHaveLength(1)
    expect(wrapper.find('.combat-ext-scheduler-head button').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('行动实体')
    wrapper.unmount()
  })

  it('Case E: a GM still gets the actor selector and the scheduler advance', async () => {
    const wrapper = tool(detail(true), true)

    await wrapper.get('[data-testid="combat-extension-tool"]').trigger('click')
    await flushPromises()

    // actor selector + 每个行动的目标 selector
    expect(wrapper.findAll('.combat-ext-action select')).toHaveLength(2)
    expect(wrapper.text()).toContain('行动实体')
    const advance = wrapper.get('.combat-ext-scheduler-head button')
    expect(advance.text()).toBe('推进时间')

    mocks.api.mockResolvedValue({ ok: true })
    await advance.trigger('click')
    await flushPromises()
    expect(String(mocks.api.mock.calls[0][0])).toContain('/combat/scheduler/advance')
    expect(wrapper.emitted('changed')).toHaveLength(1)
    wrapper.unmount()
  })

  it('Case F: the panel is not part of the persistent tool output before opening', () => {
    const wrapper = tool(detail(true), true)

    // tools 里只有入口按钮：面板既不常驻，也没有第二个渲染出口。
    expect(wrapper.findAll('.combat-ext')).toHaveLength(0)
    expect(wrapper.findAll('[data-testid="combat-extension-tool"]')).toHaveLength(1)
    wrapper.unmount()
  })

  it('Case G: the entry is labelled from the shared i18n key in all four locales', () => {
    for (const [locale, label] of [
      ['zh-CN', '战斗动作'],
      ['en', 'Combat Actions'],
      ['ja', '戦闘アクション'],
      ['de', 'Kampfaktionen'],
    ] as const) {
      i18n.global.locale.value = locale
      const wrapper = tool(detail(true), false)
      expect(wrapper.get('[data-testid="combat-extension-tool"]').text()).toContain(label)
      wrapper.unmount()
    }
  })
})
