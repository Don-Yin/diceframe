import type { Router } from 'vue-router'

const RUNTIME_RELOAD_KEY = 'diceframe_runtime_reload_at'
const RUNTIME_RELOAD_COOLDOWN_MS = 30_000

type RuntimeRecoveryOptions = {
  storage?: Pick<Storage, 'getItem' | 'setItem'>
  now?: () => number
  reload?: () => void
}

export function isStaleRuntimeAssetError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error || '')
  return /(?:Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|ChunkLoadError|Loading chunk .+ failed|Unable to preload CSS)/iu.test(message)
}

export function reserveRuntimeReload(
  storage: Pick<Storage, 'getItem' | 'setItem'>,
  now = Date.now(),
  cooldownMs = RUNTIME_RELOAD_COOLDOWN_MS,
): boolean {
  try {
    const previous = Number(storage.getItem(RUNTIME_RELOAD_KEY) || 0)
    if (Number.isFinite(previous) && previous > 0 && now - previous < cooldownMs) return false
    storage.setItem(RUNTIME_RELOAD_KEY, String(now))
    return true
  } catch {
    // Without persistent per-tab state an automatic reload could loop forever.
    return false
  }
}

export function installRuntimeRecovery(
  router: Pick<Router, 'onError'>,
  options: RuntimeRecoveryOptions = {},
): () => void {
  const storage = options.storage ?? window.sessionStorage
  const now = options.now ?? Date.now
  const reload = options.reload ?? (() => window.location.reload())

  const recover = (): boolean => {
    if (!reserveRuntimeReload(storage, now())) return false
    reload()
    return true
  }
  const onPreloadError = (event: Event) => {
    if (recover()) event.preventDefault()
  }
  window.addEventListener('vite:preloadError', onPreloadError)
  const removeRouterError = router.onError((error) => {
    if (isStaleRuntimeAssetError(error)) recover()
  })

  return () => {
    window.removeEventListener('vite:preloadError', onPreloadError)
    removeRouterError()
  }
}
