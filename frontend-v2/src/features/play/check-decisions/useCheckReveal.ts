import { computed, getCurrentScope, onScopeDispose, ref } from 'vue'
import type { CheckRevealRecord } from '@/api/types'

interface RevealResponse {
  ok?: boolean
  error?: string
  check_id?: string
  reveal?: CheckRevealRecord
}

export interface CheckRevealDependencies {
  api: (path: string, init?: RequestInit) => Promise<RevealResponse>
  gameKey: () => string
  runId: () => string
  viewer: () => string
  applyRecord: (checkId: string, record: CheckRevealRecord) => void
  refresh: (silent?: boolean) => Promise<unknown>
  reportError: (error: unknown) => void
}

/** Owns the async fence for the shared, presentation-only reveal marker. */
export function useCheckReveal(deps: CheckRevealDependencies) {
  const inFlight = new Map<string, Promise<void>>()
  const pendingKeys = ref<string[]>([])
  const contextKey = () => `${deps.gameKey()}\u0000${deps.runId()}\u0000${deps.viewer()}\u0000`
  const busyIds = computed(() => {
    const prefix = contextKey()
    return pendingKeys.value.filter(key => key.startsWith(prefix)).map(key => key.slice(prefix.length))
  })
  let disposed = false
  if (getCurrentScope()) onScopeDispose(() => {
    disposed = true
    inFlight.clear()
    pendingKeys.value = []
  })

  function reveal(checkId: string): Promise<void> {
    const id = String(checkId || '')
    const gameKey = deps.gameKey()
    const runId = deps.runId()
    const viewer = deps.viewer()
    if (disposed || !id || !gameKey) return Promise.resolve()
    const key = `${gameKey}\u0000${runId}\u0000${viewer}\u0000${id}`
    const existing = inFlight.get(key)
    if (existing) return existing
    const sameContext = () => !disposed && deps.gameKey() === gameKey && deps.runId() === runId && deps.viewer() === viewer
    pendingKeys.value = [...pendingKeys.value, key]
    const request = (async () => {
      try {
        const result = await deps.api(`/games/${encodeURIComponent(gameKey)}/checks/${encodeURIComponent(id)}/reveal`, {
          method: 'POST',
          body: JSON.stringify({}),
        })
        if (result.ok === false || result.error) throw new Error(result.error || 'Reveal failed')
        if (!sameContext()) return
        if (result.reveal?.by) deps.applyRecord(id, result.reveal)
        if (sameContext()) await deps.refresh(true)
      } catch (error: unknown) {
        if (sameContext()) deps.reportError(error)
      }
    })()
    inFlight.set(key, request)
    // Attach cleanup after registering the promise: even a synchronous request
    // error must not leave a settled promise blocking all subsequent retries.
    const finish = () => {
      inFlight.delete(key)
      pendingKeys.value = pendingKeys.value.filter(value => value !== key)
    }
    void request.then(finish, finish)
    return request
  }

  return { reveal, busyIds }
}
