export type LorebookSource = '__builtin__' | '__blank__' | `copy:${string}`

export interface LoreWorldRef {
  world_id?: string
  id?: string
  name?: string
}

export interface LorebookLabels {
  blank: string
  copied: string
}

export interface LorebookBindingOption {
  id: string
  primary?: boolean
  source_kind?: string
  source_id?: string
  scope?: string
  ref?: { source_kind: string; source_id: string; kind: 'lorebook'; id: string; digest?: string }
}

export type CreatePayload = Record<string, unknown> & {
  world_id?: string
  game_name?: string
}

export function applyStoryMode(payload: CreatePayload, mode: 'prose' | 'dialogue'): CreatePayload {
  return { ...payload, story_mode: mode }
}

/**
 * Applies the existing world/lorebook contract to a create payload.
 * The server remains the owner of world creation; this only makes the
 * client intent explicit and testable.
 */
export function applyLorebookSource(
  payload: CreatePayload,
  source: LorebookSource,
  sourceWorldId: string,
  loreWorlds: LoreWorldRef[],
  idFactory: () => string = () => String(Date.now()),
  labels: LorebookLabels = { blank: '独立世界副本 · 空白资料册', copied: '独立世界副本 · 复制资料册' },
  selectedBookIds: string[] | undefined = undefined,
  books: LorebookBindingOption[] = [],
): CreatePayload {
  const selected = selectedBookIds !== undefined
    ? selectedBookIds
      .map(id => books.find(book => book.id === id) || { id })
      .filter(book => Boolean(book.id))
      .map((book, index) => {
        const ref = book.ref
        if (!ref?.source_kind || !ref.source_id || ref.kind !== 'lorebook') throw new Error(`资料册 ${book.id} 缺少有效来源引用`)
        return {
          ref: { ...ref, id: ref.id || book.id, digest: ref.digest || '' },
          role: book.primary || index === 0 ? 'primary' : 'runtime',
          order: book.primary || index === 0 ? 100 : 110 + index,
        }
      })
    : []
  if (source === '__builtin__') {
    return selectedBookIds !== undefined ? { ...payload, create_lorebook: false, book_bindings: selected } : { ...payload, create_lorebook: false }
  }
  const suffix = source === '__blank__' ? '_blank_' : '_copy_'
  const worldId = `${sourceWorldId}${suffix}${idFactory()}`
  const next: CreatePayload = {
    ...payload,
    source_world_id: sourceWorldId,
    world_id: worldId,
    game_name: `${String(payload.game_name || '')}${source === '__blank__' ? labels.blank : labels.copied}`,
    create_lorebook: true,
    world_ref: { source_kind: 'world', source_id: worldId, kind: 'world', id: worldId, digest: '' },
  }
  if (source === '__blank__') return { ...next, blank_lorebook: true, ...(selectedBookIds !== undefined ? { book_bindings: selected } : {}) }
  const copiedWorldId = source.slice('copy:'.length)
  if (!loreWorlds.some(world => String(world.world_id || world.id || '') === copiedWorldId)) {
    throw new Error('Selected lorebook source is unavailable')
  }
  return {
    ...next,
    lorebook_world_id: copiedWorldId,
    book_bindings: selectedBookIds !== undefined ? selected : [{ ref: { source_kind: 'world', source_id: copiedWorldId, kind: 'lorebook', id: `world:${copiedWorldId}`, digest: '' }, role: 'runtime', order: 110 }],
  }
}
