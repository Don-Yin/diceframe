import { ref, type Ref } from 'vue'

export interface ActionRecoveryIdentity {
  gameKey: string
  runId: string
  actorId: string
  round: number
}

export type ActionRecoveryKind = 'editable' | 'refresh'

export interface ActionRecoveryRecord {
  code: string
  message: string
  kind: ActionRecoveryKind
  createdAt: number
}

export interface ActionRecoverySnapshot {
  identity: ActionRecoveryIdentity
  draft: string
  recovery: ActionRecoveryRecord | null
  updatedAt: number
}

const STORAGE_PREFIX = 'diceframe:action-recovery:v1:'
const MAX_AGE_MS = 24 * 60 * 60 * 1000
const MAX_CLOCK_SKEW_MS = 5 * 60 * 1000
const MAX_IDENTITY_LENGTH = 512
const MAX_DRAFT_LENGTH = 12_000
const MAX_RECORD_CODE_LENGTH = 128
const MAX_RECORD_MESSAGE_LENGTH = 2_000

function validIdentity(value: unknown): value is ActionRecoveryIdentity {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<ActionRecoveryIdentity>
  return typeof candidate.gameKey === 'string' && candidate.gameKey.length > 0 && candidate.gameKey.length <= MAX_IDENTITY_LENGTH
    && typeof candidate.runId === 'string' && candidate.runId.length > 0 && candidate.runId.length <= MAX_IDENTITY_LENGTH
    && typeof candidate.actorId === 'string' && candidate.actorId.length > 0 && candidate.actorId.length <= MAX_IDENTITY_LENGTH
    && Number.isInteger(candidate.round) && Number(candidate.round) >= 0
}

function keyFor(identity: ActionRecoveryIdentity): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(JSON.stringify(identity))}`
}

function storage(): Storage | null {
  try { return typeof sessionStorage === 'undefined' ? null : sessionStorage } catch { return null }
}

function sameIdentity(a: ActionRecoveryIdentity, b: ActionRecoveryIdentity): boolean {
  return a.gameKey === b.gameKey && a.runId === b.runId && a.actorId === b.actorId && a.round === b.round
}

function validRecord(value: unknown): value is ActionRecoveryRecord {
  if (!value || typeof value !== 'object') return false
  const record = value as Partial<ActionRecoveryRecord>
  return typeof record.code === 'string' && record.code.length > 0 && record.code.length <= MAX_RECORD_CODE_LENGTH
    && typeof record.message === 'string' && record.message.length <= MAX_RECORD_MESSAGE_LENGTH
    && (record.kind === 'editable' || record.kind === 'refresh')
    && Number.isFinite(record.createdAt)
}

export function readActionRecovery(identity: ActionRecoveryIdentity): ActionRecoverySnapshot | null {
  if (!validIdentity(identity)) return null
  const store = storage()
  if (!store) return null
  const key = keyFor(identity)
  try {
    const raw = store.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<ActionRecoverySnapshot>
    const updatedAt = parsed.updatedAt
    const now = Date.now()
    if (!validIdentity(parsed.identity) || !sameIdentity(parsed.identity, identity)
      || typeof parsed.draft !== 'string' || typeof updatedAt !== 'number' || !Number.isFinite(updatedAt)
      || parsed.draft.length > MAX_DRAFT_LENGTH || now - updatedAt > MAX_AGE_MS || updatedAt - now > MAX_CLOCK_SKEW_MS
      || (parsed.recovery !== null && !validRecord(parsed.recovery))
      || (parsed.recovery !== null && typeof parsed.recovery?.createdAt === 'number'
        && (now - parsed.recovery.createdAt > MAX_AGE_MS || parsed.recovery.createdAt - now > MAX_CLOCK_SKEW_MS))) {
      store.removeItem(key)
      return null
    }
    return parsed as ActionRecoverySnapshot
  } catch {
    try { store.removeItem(key) } catch { /* storage may be unavailable */ }
    return null
  }
}

export function writeActionRecovery(identity: ActionRecoveryIdentity, draft: string, recovery: ActionRecoveryRecord | null): void {
  if (!validIdentity(identity) || draft.length > MAX_DRAFT_LENGTH || (recovery !== null && !validRecord(recovery))) return
  const store = storage()
  if (!store) return
  const snapshot: ActionRecoverySnapshot = { identity, draft, recovery, updatedAt: Date.now() }
  try { store.setItem(keyFor(identity), JSON.stringify(snapshot)) } catch { /* private mode or quota */ }
}

export function clearActionRecovery(identity: ActionRecoveryIdentity): void {
  if (!validIdentity(identity)) return
  try { storage()?.removeItem(keyFor(identity)) } catch { /* storage may be unavailable */ }
}

export function useActionRecovery(identity: Ref<ActionRecoveryIdentity>) {
  const snapshot = ref<ActionRecoverySnapshot | null>(readActionRecovery(identity.value))
  return {
    snapshot,
    read: () => { snapshot.value = readActionRecovery(identity.value); return snapshot.value },
    save: (draft: string, recovery: ActionRecoveryRecord | null) => {
      const next: ActionRecoverySnapshot = { identity: { ...identity.value }, draft, recovery, updatedAt: Date.now() }
      writeActionRecovery(identity.value, draft, recovery)
      snapshot.value = readActionRecovery(identity.value) || next
    },
    clear: () => {
      clearActionRecovery(identity.value)
      snapshot.value = null
    },
  }
}
