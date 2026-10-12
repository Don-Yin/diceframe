import type { GameSummary } from '@/api/types'

export type SaveSortMode = 'recent' | 'oldest' | 'name' | 'round'

function activityTime(game: GameSummary): number | null {
  for (const value of [game.last_activity, game.started_at]) {
    if (!value) continue
    const timestamp = Date.parse(value)
    if (Number.isFinite(timestamp)) return timestamp
  }
  return null
}

function compareActivity(left: GameSummary, right: GameSummary, oldestFirst = false): number {
  const leftTime = activityTime(left)
  const rightTime = activityTime(right)
  if (leftTime === null && rightTime === null) return 0
  if (leftTime === null) return 1
  if (rightTime === null) return -1
  return oldestFirst ? leftTime - rightTime : rightTime - leftTime
}

function saveName(game: GameSummary): string {
  return String(game.world_name || game.game_key)
}

export function sortGames(games: readonly GameSummary[], mode: SaveSortMode, locale?: string): GameSummary[] {
  return [...games].sort((left, right) => {
    if (mode === 'oldest') {
      return compareActivity(left, right, true)
        || saveName(left).localeCompare(saveName(right), locale)
    }
    if (mode === 'name') {
      return saveName(left).localeCompare(saveName(right), locale)
        || compareActivity(left, right)
    }
    if (mode === 'round') {
      return Number(right.round_number || 0) - Number(left.round_number || 0)
        || compareActivity(left, right)
    }
    return compareActivity(left, right)
      || saveName(left).localeCompare(saveName(right), locale)
  })
}
