import { describe, expect, it } from 'vitest'
import type { GameSummary } from '../src/api/types'
import { sortGames } from '../src/features/overview/saveSorting'

const games: GameSummary[] = [
  { game_key: 'old', world_name: 'Beta', last_activity: '2026-08-01T12:00:00Z', round_number: 8 },
  { game_key: 'undated', world_name: 'Gamma', round_number: 20 },
  { game_key: 'new', world_name: 'Alpha', last_activity: '2026-08-20T12:00:00Z', round_number: 2 },
]

describe('save sorting', () => {
  it('puts the most recently active save first by default', () => {
    expect(sortGames(games, 'recent').map(game => game.game_key)).toEqual(['new', 'old', 'undated'])
  })

  it('supports oldest, name, and round sorting without mutating the response', () => {
    expect(sortGames(games, 'oldest').map(game => game.game_key)).toEqual(['old', 'new', 'undated'])
    expect(sortGames(games, 'name', 'en').map(game => game.game_key)).toEqual(['new', 'old', 'undated'])
    expect(sortGames(games, 'round').map(game => game.game_key)).toEqual(['undated', 'old', 'new'])
    expect(games.map(game => game.game_key)).toEqual(['old', 'undated', 'new'])
  })
})
