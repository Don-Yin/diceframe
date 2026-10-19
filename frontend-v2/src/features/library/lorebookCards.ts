import type { WorldSummary } from '@/api/types'
import type { ContentHubCopy } from './hubCopy'

export interface LibraryLorebook {
  id: string
  name?: string
  description?: string
  entry_count?: number
  scope?: string
  language?: string
  primary?: boolean
  bindings?: Array<{ scope_kind?: string; scope_id?: string; role?: string }>
  ref?: { id?: string; source_id?: string; source_kind?: string; kind?: string }
}

// Display metadata only: never rename persisted books or derive their identity
// from a translated title. Binding scope and provenance remain distinct.
export function lorebookCard(book: LibraryLorebook, worlds: WorldSummary[], copy: ContentHubCopy) {
  const worldBindings = (book.bindings || []).filter(binding => binding.scope_kind === 'world' && binding.scope_id)
  const worldNames = [...new Set(worldBindings.map(binding => {
    const world = worlds.find(item => String(item.id || item.world_id || '') === binding.scope_id)
    return String(world?.name || world?.world_name || copy.unlistedWorld)
  }))]
  const primary = worldBindings.some(binding => binding.role === 'primary')
  const kind = primary ? copy.primaryLorebook : worldBindings.length ? copy.lorebooksSection
    : book.bindings?.some(binding => binding.scope_kind === 'global') ? copy.globalLorebook
      : book.bindings?.length ? copy.lorebooksSection : copy.independentLorebook
  const name = book.name?.trim() || copy.unnamedLorebook
  return {
    title: primary && worldNames.includes(name) ? `${name} · ${copy.primaryLorebook}` : name,
    kind,
    worldNames,
  }
}
