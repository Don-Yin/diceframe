import { describe, expect, it } from 'vitest'
import { projectCreationLorebooks, type CreationLorebook } from '../src/features/create/creationLorebooks'

const book = (id: string, scope: string, scopeId: string, enabled = true, bindingEnabled = true): CreationLorebook => ({
  id, name: id, enabled, entry_count: 3,
  bindings: [{ scope_kind: scope, scope_id: scopeId, enabled: bindingEnabled, role: id.startsWith('world:') ? 'primary' : 'supplemental' }],
})

describe('creation lorebook summary mirrors existing inheritance', () => {
  const books = [book('world:harbor', 'world', 'harbor'), book('npc', 'world', 'harbor'), book('global', 'global', ''), book('other', 'world', 'forest'), book('unused', 'none', '')]
  it('includes all matching world books and global books, without selecting unrelated or unbound books', () => {
    expect(projectCreationLorebooks(books, 'harbor', '__builtin__').map(item => item.id)).toEqual(['world:harbor', 'npc', 'global'])
  })
  it('shows disabled world books as inactive rather than presenting them as runtime sources', () => {
    const projected = projectCreationLorebooks([book('off-book', 'world', 'harbor', false), book('off-binding', 'world', 'harbor', true, false)], 'harbor', '__builtin__')
    expect(projected.map(item => item.active)).toEqual([false, false])
  })
  it('does not allow a disabled game binding to cancel a matching world binding', () => {
    const mixed = book('mixed', 'world', 'harbor')
    mixed.bindings!.push({ scope_kind: 'game', scope_id: 'some-game', enabled: false })
    expect(projectCreationLorebooks([mixed], 'harbor', '__builtin__')[0].active).toBe(true)
  })
  it('keeps global inheritance for a blank independent world', () => {
    expect(projectCreationLorebooks(books, 'harbor', '__blank__').map(item => item.id)).toEqual(['global'])
  })
  it('offers every bound source book for an independent world', () => {
    expect(projectCreationLorebooks(books, 'new-world', 'copy:harbor').map(item => [item.id, item.scope])).toEqual([['world:harbor', 'reference'], ['npc', 'reference'], ['global', 'global']])
  })
  it('keeps a reference inactive if its source book is disabled', () => {
    expect(projectCreationLorebooks([book('world:harbor', 'world', 'harbor', false)], '', 'copy:harbor')[0].active).toBe(false)
  })
  it('does not infer inheritance from a display scope when binding facts are missing', () => {
    expect(projectCreationLorebooks([{ id: 'unknown', name: 'Unknown', scope: 'world', enabled: true }], 'harbor', '__builtin__')).toEqual([])
  })
})
