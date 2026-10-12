import { describe, expect, it } from 'vitest'
import type { GameDetail, Player } from '../src/api/types'
import { isStoredPlayerMember } from '../src/utils/joinIdentity'

function player(id: string): Player {
  return { user_id: id, character_name: id }
}

function detail(fields: GameDetail['multiplayer']): Partial<GameDetail> {
  return { multiplayer: fields }
}

describe('isStoredPlayerMember', () => {
  it('returns true when the uid is among ready players', () => {
    expect(isStoredPlayerMember(detail({ ready_players: [player('u1')], waiting_players: [], away_players: [] }), 'u1')).toBe(true)
  })

  it('returns true when the uid is waiting', () => {
    expect(isStoredPlayerMember(detail({ ready_players: [], waiting_players: [player('u2')], away_players: [] }), 'u2')).toBe(true)
  })

  it('returns true when the uid is away', () => {
    expect(isStoredPlayerMember(detail({ ready_players: [], waiting_players: [], away_players: [player('u3')] }), 'u3')).toBe(true)
  })

  it('returns false for a uid that was kicked', () => {
    expect(isStoredPlayerMember(detail({ ready_players: [player('u1')], waiting_players: [], away_players: [] }), 'kicked')).toBe(false)
  })

  it('returns false when no multiplayer info is present', () => {
    expect(isStoredPlayerMember({}, 'u1')).toBe(false)
  })

  it('trusts the server viewer signal over any roster', () => {
    const roster = { ready_players: [player('u1')], waiting_players: [], away_players: [] }
    expect(isStoredPlayerMember({ viewer: { kind: 'seat', uid: 'u1' }, multiplayer: roster }, 'u1')).toBe(true)
    expect(isStoredPlayerMember({ viewer: { kind: 'seat', uid: 'u2' }, multiplayer: roster }, 'u1')).toBe(false)
    expect(isStoredPlayerMember({ viewer: { kind: 'outsider' }, multiplayer: roster }, 'u1')).toBe(false)
  })

  it('treats a visitor lobby view as not a member', () => {
    expect(isStoredPlayerMember({ viewer: { kind: 'outsider' }, multiplayer: { player_count: 3 } as GameDetail['multiplayer'] }, 'u1')).toBe(false)
  })
})
