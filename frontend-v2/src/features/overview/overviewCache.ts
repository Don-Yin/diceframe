import type { GameSummary } from '@/api/types'

// The archive index is small compared with the scene blobs and is safe to
// retain for the lifetime of the authenticated SPA session.  Returning a
// copy prevents a refresh from mutating the cached snapshot while a route is
// still rendering it.
let cachedGames: GameSummary[] = []

export function readOverviewGamesCache(): GameSummary[] {
  return cachedGames.map(game => ({ ...game }))
}

export function writeOverviewGamesCache(games: GameSummary[]): void {
  cachedGames = games.map(game => ({ ...game }))
}

export function clearOverviewGamesCache(): void {
  cachedGames = []
}
