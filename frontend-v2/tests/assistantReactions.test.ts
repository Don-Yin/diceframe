import { mount } from '@vue/test-utils'
import { computed, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AssistantShell from '../src/components/assistant/AssistantShell.vue'
import { useAssistantPreferences } from '../src/composables/useAssistantPreferences'
import { clearAssistantReaction, reportAssistantReaction, useAssistantReactions } from '../src/composables/useAssistantReactions'
import { speakableText } from '../src/composables/useAssistantVoice'
import { usePlayReactions } from '../src/features/play/usePlayReactions'
import type { useGame } from '../src/composables/useGame'
import { i18n } from '../src/i18n'

const stubs = {
  NDrawer: { template: '<div />' },
  NDrawerContent: { template: '<div><slot /></div>' },
  AssistantPanel: true,
}

function resetPreferences() {
  const preferences = useAssistantPreferences()
  preferences.setEnabled(true)
  preferences.setReactions(true)
  preferences.setReactionSpeech(false)
  for (const category of ['check', 'combat', 'story', 'growth', 'table'] as const) preferences.setReactionCategory(category, true)
}

describe('DF Agent table reactions', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useFakeTimers()
    resetPreferences()
    clearAssistantReaction()
  })

  afterEach(() => {
    clearAssistantReaction()
    vi.useRealTimers()
  })

  it('shows a reveal outcome on the launcher and then settles back', async () => {
    const wrapper = mount(AssistantShell, { global: { plugins: [i18n], stubs } })
    const fab = wrapper.get('[data-testid="assistant-shell-fab"]')
    expect(fab.attributes('data-mood')).toBe('idle')

    reportAssistantReaction('diceRoll')
    await nextTick()
    expect(fab.attributes('data-mood')).toBe('rolling')

    reportAssistantReaction('critical')
    await nextTick()
    expect(fab.attributes('data-mood')).toBe('cheer')
    expect(wrapper.find('.assistant-shell-reaction-great').text()).toMatch(/大成功|Critical success/)

    vi.advanceTimersByTime(4000)
    await nextTick()
    expect(fab.attributes('data-mood')).toBe('idle')
    wrapper.unmount()
  })

  it('keeps a strong reaction briefly instead of letting a weaker one cut it off', () => {
    const { reaction } = useAssistantReactions()
    reportAssistantReaction('attackCrit')
    reportAssistantReaction('attackHit')
    expect(reaction.value?.kind).toBe('attackCrit')
    vi.advanceTimersByTime(1000)
    reportAssistantReaction('attackHit')
    expect(reaction.value?.kind).toBe('attackHit')
  })

  it('respects the master switch and per-category switches', () => {
    const preferences = useAssistantPreferences()
    const { reaction } = useAssistantReactions()
    preferences.setReactionCategory('combat', false)
    expect(JSON.parse(localStorage.getItem('diceframe_assistant_reaction_categories_off') || '[]')).toEqual(['combat'])
    reportAssistantReaction('yourTurn')
    expect(reaction.value).toBeNull()
    reportAssistantReaction('levelUp', { amount: 3 })
    expect(reaction.value?.kind).toBe('levelUp')

    clearAssistantReaction()
    preferences.setReactions(false)
    reportAssistantReaction('success')
    expect(reaction.value).toBeNull()
  })
})

describe('live play state reactions', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useFakeTimers()
    resetPreferences()
    clearAssistantReaction()
  })
  afterEach(() => {
    clearAssistantReaction()
    vi.useRealTimers()
  })

  function fakeGame() {
    const sheet = ref<Record<string, unknown>>({ hp: 20, max_hp: 20, xp: 0, level: 1, inventory: [{ name: '火把' }] })
    const detail = ref<Record<string, unknown> | null>(null)
    const players = ref([{ user_id: 'me', name: '艾拉', character_sheet: sheet.value }])
    const game = {
      currentGame: ref('web|room|bot'),
      detail,
      players,
      player: computed(() => ({ ...players.value[0], character_sheet: sheet.value })),
      loading: ref(false),
    } as unknown as ReturnType<typeof useGame>
    return { game, sheet, detail, players }
  }

  it('does not replay the loaded table, then reacts to live changes', async () => {
    const { game, sheet, detail, players } = fakeGame()
    const { reaction } = useAssistantReactions()
    usePlayReactions(game)
    detail.value = { round_number: 4, state: 'action', scene: '港口' }
    await nextTick()
    expect(reaction.value).toBeNull()

    sheet.value = { ...sheet.value, inventory: [{ name: '火把' }, { name: '银钥匙' }] }
    players.value = [...players.value]
    await nextTick()
    expect(reaction.value).toMatchObject({ kind: 'itemGain', detail: { name: '银钥匙' } })

    vi.advanceTimersByTime(5000)
    sheet.value = { ...sheet.value, hp: 12 }
    players.value = [...players.value]
    await nextTick()
    expect(reaction.value).toMatchObject({ kind: 'hurt', detail: { amount: 8 } })

    vi.advanceTimersByTime(5000)
    sheet.value = { ...sheet.value, hp: 0 }
    players.value = [...players.value]
    await nextTick()
    expect(reaction.value?.kind).toBe('downed')

    vi.advanceTimersByTime(5000)
    detail.value = { ...detail.value, state: 'ended' }
    await nextTick()
    expect(reaction.value?.kind).toBe('gameEnded')
  })
})

describe('DF Agent voice text', () => {
  it('strips markdown before reading a reply aloud', () => {
    expect(speakableText('## 下一步\n**打开** [创作台](#/create)：\n```js\nx()\n```\n- 完成')).toBe('下一步 打开 创作台： - 完成')
  })
})
