export interface CreationLorebook {
  id: string
  name: string
  enabled?: boolean
  scope?: string
  source_kind?: string
  source_id?: string
  ref?: { source_kind: string; source_id: string; kind: 'lorebook'; id: string; digest?: string }
  entry_count?: number
  bindings?: Array<{ scope_kind: string; scope_id: string; enabled?: boolean | number; role?: string }>
}

export interface CreationLorebookRow extends CreationLorebook {
  active: boolean
  primary: boolean
  scope: 'world' | 'global' | 'reference'
}

/** Read-only explanation of the current resolver; this does not choose or bind books. */
export function projectCreationLorebooks(books: CreationLorebook[], worldId: string, source: string): CreationLorebookRow[] {
  const inheritedWorld = source === '__builtin__' ? worldId : ''
  const referenceWorldId = source.startsWith('copy:') ? source.slice(5) : ''
  const seen = new Set<string>()
  const rows: CreationLorebookRow[] = []
  for (const book of books) {
    if (!book.id || seen.has(book.id)) continue
    const bindings = book.bindings || []
    const worldBindings = (inheritedWorld || referenceWorldId)
      ? bindings.filter(binding => binding.scope_kind === 'world' && binding.scope_id === (inheritedWorld || referenceWorldId))
      : []
    const globalBindings = bindings.filter(binding => binding.scope_kind === 'global')
    const reference = Boolean(referenceWorldId && worldBindings.length)
    if (!reference && !worldBindings.length && !globalBindings.length) continue
    seen.add(book.id)
    const activeGlobal = globalBindings.some(binding => binding.enabled !== false && binding.enabled !== 0)
    rows.push({
      ...book,
      scope: activeGlobal || (!reference && !worldBindings.length) ? 'global' : reference ? 'reference' : 'world',
      primary: worldBindings.some(binding => binding.role === 'primary'),
      active: book.enabled !== false && (reference || activeGlobal || worldBindings.some(binding => binding.enabled !== false && binding.enabled !== 0)),
    })
  }
  return rows
}
