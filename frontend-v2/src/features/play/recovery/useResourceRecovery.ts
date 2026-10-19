import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { RecoveryCommand, RecoverySnapshot } from './resourceRecoveryTypes'

interface PendingCommand { gameKey: string; action: RecoveryCommand; body: Record<string, unknown> }
interface Failure { ok?: boolean; error?: string; code?: string }

// LAN HTTP clients may not expose randomUUID. This ID identifies an operation;
// it is never a credential or a rules roll.
function operationId() {
  return globalThis.crypto?.randomUUID?.() || `recovery-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function useResourceRecovery(gameKey: Ref<string>, refreshKey: Ref<unknown>, viewerKey: Ref<string>, changed: () => void) {
  const snapshot = ref<RecoverySnapshot | null>(null)
  const loading = ref(false)
  const busy = ref(false)
  const error = ref('')
  const uncertain = ref(false)
  const completed = ref(false)
  let pending: PendingCommand | null = null
  let generation = 0
  let loadId = 0

  async function refresh() {
    const context = generation
    const request = ++loadId
    const key = gameKey.value
    if (!key) return
    loading.value = true
    try {
      const response = await api<RecoverySnapshot & Failure>(`/games/${encodeURIComponent(key)}/recovery`)
      if (context !== generation || request !== loadId) return
      if (response.ok === false) throw new Error(response.error || response.code || 'Recovery unavailable')
      snapshot.value = response
      if (!uncertain.value) error.value = ''
    } catch (failure) {
      if (context === generation && request === loadId) error.value = errorMessage(failure)
    } finally {
      if (context === generation && request === loadId) loading.value = false
    }
  }

  async function execute(command: PendingCommand) {
    if (busy.value || command.gameKey !== gameKey.value) return
    const context = generation
    busy.value = true
    error.value = ''
    completed.value = false
    try {
      const result = await api<Failure>(`/games/${encodeURIComponent(command.gameKey)}/recovery/${command.action}`, { method: 'POST', body: JSON.stringify(command.body) })
      if (context !== generation) return
      if (result.ok === false) {
        pending = null
        uncertain.value = false
        await refresh()
        error.value = result.error || result.code || 'Recovery unavailable'
        return
      }
      pending = null
      uncertain.value = false
      completed.value = true
      changed()
      await refresh()
    } catch (failure) {
      if (context !== generation) return
      // A rejected HTTP response is definitive. A transport failure can occur
      // after commit, so keep the original revision and operation ID for retry.
      const definite = typeof failure === 'object' && failure !== null && 'status' in failure
        && typeof failure.status === 'number' && failure.status < 500
      if (definite) {
        pending = null
        uncertain.value = false
        await refresh()
      } else {
        pending = command
        uncertain.value = true
      }
      error.value = errorMessage(failure)
    } finally {
      if (context === generation) busy.value = false
    }
  }

  async function submit(action: RecoveryCommand, payload: Record<string, unknown>) {
    const state = snapshot.value
    if (!state?.supported || busy.value || uncertain.value) return
    const command: PendingCommand = {
      gameKey: gameKey.value, action,
      body: { ...payload, run_id: state.run_id, expected_revision: state.revision, operation_id: operationId() },
    }
    await execute(command)
  }

  async function retry() { if (pending) await execute(pending) }

  watch([gameKey, viewerKey], () => {
    generation++
    snapshot.value = null
    pending = null
    uncertain.value = false
    busy.value = false
    error.value = ''
    completed.value = false
    void refresh()
  }, { immediate: true })
  watch(refreshKey, () => { if (!busy.value) void refresh() })
  onBeforeUnmount(() => { generation++; loadId++ })
  return { snapshot, loading, busy, error, uncertain, completed, refresh, submit, retry }
}
