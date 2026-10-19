import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearActionRecovery,
  readActionRecovery,
  writeActionRecovery,
  type ActionRecoveryIdentity,
} from '../src/features/play/recovery/useActionRecovery'

const identity: ActionRecoveryIdentity = { gameKey: 'web|room|bot', runId: 'run-1', actorId: 'player-1', round: 4 }
const recovery = { code: 'ROUND_PROCESSING_FAILED', message: 'retry', kind: 'editable' as const, createdAt: 1_000 }

describe('action recovery storage', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.useFakeTimers()
    vi.setSystemTime(1_000)
  })
  afterEach(() => { vi.useRealTimers() })

  it('keeps drafts isolated by game, run, actor, and round', () => {
    writeActionRecovery(identity, 'draft', recovery)

    expect(readActionRecovery(identity)?.draft).toBe('draft')
    expect(readActionRecovery({ ...identity, actorId: 'player-2' })).toBeNull()
    expect(readActionRecovery({ ...identity, round: 5 })).toBeNull()
    expect(readActionRecovery({ ...identity, gameKey: 'web|other|bot' })).toBeNull()
  })

  it('drops malformed and expired entries before returning them', () => {
    writeActionRecovery(identity, 'draft', recovery)
    vi.setSystemTime(24 * 60 * 60 * 1000 + 1_001)
    expect(readActionRecovery(identity)).toBeNull()

    const key = 'diceframe:action-recovery:v1:' + encodeURIComponent(JSON.stringify(identity))
    sessionStorage.setItem(key, '{bad json')
    expect(readActionRecovery(identity)).toBeNull()
    expect(sessionStorage.getItem(key)).toBeNull()
  })

  it('clears only the selected identity', () => {
    const other = { ...identity, actorId: 'player-2' }
    writeActionRecovery(identity, 'one', recovery)
    writeActionRecovery(other, 'two', recovery)
    clearActionRecovery(identity)

    expect(readActionRecovery(identity)).toBeNull()
    expect(readActionRecovery(other)?.draft).toBe('two')
  })

  it('does not persist without a run id or beyond storage size and clock bounds', () => {
    writeActionRecovery({ ...identity, runId: '' }, 'draft', recovery)
    writeActionRecovery(identity, 'x'.repeat(12_001), recovery)
    expect(sessionStorage.length).toBe(0)

    const key = 'diceframe:action-recovery:v1:' + encodeURIComponent(JSON.stringify(identity))
    sessionStorage.setItem(key, JSON.stringify({ identity, draft: 'future', recovery, updatedAt: Date.now() + 5 * 60 * 1000 + 1 }))
    expect(readActionRecovery(identity)).toBeNull()
    expect(sessionStorage.getItem(key)).toBeNull()
  })
})
