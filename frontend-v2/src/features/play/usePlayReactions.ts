import { watch } from 'vue'
import type { useGame } from '@/composables/useGame'
import { reportAssistantReaction } from '@/composables/useAssistantReactions'

/*
 * Turns live changes of the play state into DF Agent avatar reactions.
 * Each game starts from a baseline snapshot, so loading a table (or
 * switching to another one) never replays its history as reactions. Combat
 * and check reveals report from their own live presentation queues.
 */

type Game = ReturnType<typeof useGame>

interface Baseline {
  game: string
  round: number
  scene: string
  sceneImage: string
  state: string
  level: number
  xp: number
  hp: number | null
  items: Set<string>
  players: Map<string, string>
  pushes: number
}

const LOW_HP_RATIO = 0.25

function itemKeys(game: Game): Set<string> {
  const sheet = game.player.value?.character_sheet
  const keys = new Set<string>()
  for (const item of [...(sheet?.inventory || []), ...(sheet?.key_items || [])]) {
    const record = item as unknown as Record<string, unknown>
    const name = String(record.name || record.id || '').trim()
    if (name) keys.add(name)
  }
  return keys
}

function snapshot(game: Game): Baseline {
  const detail = game.detail.value
  const sheet = game.player.value?.character_sheet
  const scene = detail?.scene as unknown
  return {
    game: game.currentGame.value || '',
    round: Number(detail?.round_number || 0),
    scene: typeof scene === 'string' ? scene : String((scene as Record<string, unknown> | undefined)?.name || ''),
    sceneImage: JSON.stringify(detail?.scene_image || ''),
    state: String(detail?.state || ''),
    level: Number(sheet?.level || 0),
    xp: Number(sheet?.xp || 0),
    hp: typeof sheet?.hp === 'number' ? sheet.hp : null,
    items: itemKeys(game),
    players: new Map(game.players.value.map(player => [player.user_id, String(player.name || player.character_sheet?.name || '')])),
    pushes: Array.isArray(detail?.pending_push_decisions) ? detail.pending_push_decisions.length : 0,
  }
}

export function usePlayReactions(game: Game): void {
  let previous: Baseline | null = null

  function evaluate(): void {
    if (!game.detail.value || game.loading.value) return
    const next = snapshot(game)
    const before = previous
    previous = next
    if (!before || before.game !== next.game) return

    if (next.state === 'ended' && before.state !== 'ended') reportAssistantReaction('gameEnded')
    if (next.round > before.round && before.round > 0) reportAssistantReaction('newRound', { amount: next.round })
    if (next.scene && before.scene && next.scene !== before.scene) reportAssistantReaction('sceneChange', { name: next.scene })
    if (next.sceneImage !== before.sceneImage && next.sceneImage !== '""' && next.sceneImage !== '{}') reportAssistantReaction('sceneImage')

    for (const [id, name] of next.players) if (!before.players.has(id)) reportAssistantReaction('playerJoin', { name })
    for (const [id, name] of before.players) if (!next.players.has(id)) reportAssistantReaction('playerLeave', { name })
    if (next.pushes > before.pushes) reportAssistantReaction('pushOffered')

    const gained = [...next.items].filter(item => !before.items.has(item))
    if (gained.length) reportAssistantReaction('itemGain', { name: gained[0] })
    if (next.xp > before.xp) reportAssistantReaction('xpGain', { amount: next.xp - before.xp })
    if (next.level > before.level && before.level > 0) reportAssistantReaction('levelUp', { amount: next.level })

    if (next.hp !== null && before.hp !== null && next.hp !== before.hp) {
      const max = Number(game.player.value?.character_sheet?.max_hp || 0)
      if (next.hp <= 0 && before.hp > 0) reportAssistantReaction('downed')
      else if (next.hp < before.hp && max > 0 && next.hp <= max * LOW_HP_RATIO && before.hp > max * LOW_HP_RATIO) reportAssistantReaction('hpLow')
      else if (next.hp < before.hp) reportAssistantReaction('hurt', { amount: before.hp - next.hp })
      else reportAssistantReaction('heal', { amount: next.hp - before.hp })
    }
  }

  watch(
    [game.currentGame, game.detail, game.players, game.loading],
    evaluate,
    { flush: 'post' },
  )
}
