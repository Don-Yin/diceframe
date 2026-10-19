import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import type { RestActivity } from '@/api/types'

export interface RestNoticeToast {
  latest: RestActivity
  count: number
}

const STORAGE_PREFIX = 'diceframe:rest-notices:'

function readEnabled(key: string): boolean {
  try {
    return localStorage.getItem(key) !== 'false'
  } catch {
    return true
  }
}

function writeEnabled(key: string, enabled: boolean) {
  try { localStorage.setItem(key, String(enabled)) } catch { /* storage is optional */ }
}

export function useRestNotices(gameKey: Ref<string>, runId: Ref<string>, actorId: Ref<string>, activity: Ref<RestActivity[]>) {
  const enabled = ref(true)
  const unread = ref(0)
  const toast = ref<RestNoticeToast | null>(null)
  const dialogOpen = ref(false)
  const identity = ref('')
  const seen = new Set<string>()
  let timer: number | undefined

  const storageKey = computed(() => `${STORAGE_PREFIX}${JSON.stringify([gameKey.value, actorId.value])}`)

  function clearTimer() {
    if (timer !== undefined) { window.clearTimeout(timer); timer = undefined }
  }

  function resetForIdentity(current: RestActivity[]) {
    clearTimer()
    toast.value = null
    unread.value = 0
    dialogOpen.value = false
    identity.value = `${gameKey.value}\u0000${runId.value}\u0000${actorId.value}`
    enabled.value = readEnabled(storageKey.value)
    seen.clear()
    for (const item of current) seen.add(item.id)
  }

  function showToast(latest: RestActivity, count: number) {
    const previous = toast.value?.count || 0
    toast.value = { latest, count: previous + count }
    clearTimer()
    timer = window.setTimeout(() => { toast.value = null; timer = undefined }, 5000)
  }

  function processSnapshot(current: RestActivity[]) {
    const fresh: RestActivity[] = []
    for (const item of current) {
      if (seen.has(item.id)) continue
      fresh.push(item)
      seen.add(item.id)
    }
    if (!fresh.length) return
    if (!enabled.value) return
    if (dialogOpen.value) { unread.value = 0; return }
    unread.value += fresh.length
    showToast(fresh[fresh.length - 1], fresh.length)
  }

  function openHistory() {
    dialogOpen.value = true
    unread.value = 0
    toast.value = null
    clearTimer()
  }

  function closeHistory() { dialogOpen.value = false }

  function setEnabled(value: boolean) {
    enabled.value = value
    writeEnabled(storageKey.value, value)
    if (!value) { unread.value = 0; toast.value = null; clearTimer() }
  }

  function dismissToast() { toast.value = null; clearTimer() }

  watch(
    () => [gameKey.value, runId.value, actorId.value, activity.value] as const,
    ([nextGame, nextRun, nextActor, current]) => {
      const nextIdentity = `${nextGame}\u0000${nextRun}\u0000${nextActor}`
      if (nextIdentity !== identity.value) resetForIdentity(current || [])
      else processSnapshot(current || [])
    },
    { immediate: true, deep: true },
  )

  function onStorage(event: StorageEvent) {
    if (event.key !== null && event.key !== storageKey.value) return
    enabled.value = event.key === null ? true : event.newValue !== 'false'
    if (!enabled.value) { unread.value = 0; toast.value = null; clearTimer() }
  }
  onMounted(() => window.addEventListener('storage', onStorage))
  onBeforeUnmount(() => { clearTimer(); window.removeEventListener('storage', onStorage) })

  return { enabled, unread, toast, dialogOpen, openHistory, closeHistory, setEnabled, dismissToast }
}
