import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export interface WorldSelectionCandidate {
  id?: unknown
  world_id?: unknown
}

export function canonicalWorldId(world: WorldSelectionCandidate | undefined): string {
  return String(world?.id || world?.world_id || '')
}

/**
 * The lorebook page owns the browsing target. The query carries only a
 * canonical world id; it never changes the active game's saved world.
 */
export function useWorldSelectionRoute() {
  // Some embedded/unit mounts render the editor without a router provider;
  // absence of a query should retain the page's existing default selection.
  const route = useRoute() as { query?: Record<string, unknown> } | undefined
  // Lorebook is also embedded in a few dialog/test surfaces without a router.
  // Keep URL synchronization best-effort there while preserving the normal
  // route contract in the full page.
  let router: { replace?: (location: { query: Record<string, unknown> }) => unknown } | undefined
  try {
    router = useRouter() as typeof router
  } catch {
    router = undefined
  }
  const requestedWorldId = computed(() => {
    const raw = route?.query?.world
    const value = Array.isArray(raw) ? raw[0] : raw
    return String(value || '').trim()
  })
  const requestedBookId = computed(() => {
    const raw = route?.query?.book
    const value = Array.isArray(raw) ? raw[0] : raw
    return String(value || '').trim()
  })
  const requestedEntryId = computed(() => {
    const raw = route?.query?.entry
    const value = Array.isArray(raw) ? raw[0] : raw
    return String(value || '').trim()
  })
  const hasRequestedWorld = computed(() => Boolean(requestedWorldId.value))

  function resolveWorldId(candidates: WorldSelectionCandidate[]): string | null {
    const requested = requestedWorldId.value
    if (!requested) return null
    return candidates.some(candidate => canonicalWorldId(candidate) === requested) ? requested : ''
  }

  function syncWorldId(worldId: string): void {
    const canonical = String(worldId || '').trim()
    if (!canonical || !router?.replace || !route) return
    if (String(route.query?.world || '') === canonical) return
    const query: Record<string, unknown> = { ...(route.query || {}), world: canonical }
    // A deliberate world/language choice starts a new browsing context.
    // The previous Book and Entry are not targets in that new world.
    delete query.book
    delete query.entry
    router.replace({ query })
  }

  return { requestedWorldId, requestedBookId, requestedEntryId, hasRequestedWorld, resolveWorldId, syncWorldId }
}
