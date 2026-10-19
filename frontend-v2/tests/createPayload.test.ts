import { describe, expect, it } from 'vitest'
import { applyLorebookSource, type LorebookSource } from '../src/features/create/createPayload'

describe('new adventure lorebook payload contract', () => {
  const base = { world_id: 'harbor', game_name: '雾港' }
  const idFactory = () => 'fixed-id'

  it('uses the selected world without creating a lorebook', () => {
    expect(applyLorebookSource(base, '__builtin__', 'harbor', [], idFactory)).toEqual({
      world_id: 'harbor', game_name: '雾港', create_lorebook: false,
    })
  })

  it.each([
    ['__blank__', 'harbor_blank_fixed-id', '独立世界副本 · 空白资料册'],
    ['copy:source', 'harbor_copy_fixed-id', '独立世界副本 · 复制资料册'],
  ] satisfies Array<[LorebookSource, string, string]>)('creates an explicit independent world copy for %s', (source, worldId, label) => {
    const result = applyLorebookSource(base, source, 'harbor', [{ world_id: 'source', name: '旧港' }], idFactory)
    expect(result.world_id).toBe(worldId)
    expect(result.source_world_id).toBe('harbor')
    expect(result.game_name).toContain(label)
    expect(result.world_ref).toMatchObject({ source_kind: 'world', source_id: worldId, kind: 'world', id: worldId })
    if (source === '__blank__') expect(result.blank_lorebook).toBe(true)
    else expect(result.book_bindings).toEqual([{ ref: { source_kind: 'world', source_id: 'source', kind: 'lorebook', id: 'world:source', digest: '' }, role: 'runtime', order: 110 }])
  })

  it('rejects a stale copy source instead of creating a silent blank world', () => {
    expect(() => applyLorebookSource(base, 'copy:missing', 'harbor', [], idFactory)).toThrow('unavailable')
  })

  it('submits only the books selected for this game with explicit provenance', () => {
    const result = applyLorebookSource(base, '__builtin__', 'harbor', [], idFactory, undefined, ['world:harbor', 'global:glossary'], [
      { id: 'world:harbor', primary: true, ref: { source_kind: 'world', source_id: 'harbor', kind: 'lorebook', id: 'world:harbor', digest: '' } },
      { id: 'global:glossary', ref: { source_kind: 'user', source_id: 'glossary', kind: 'lorebook', id: 'global:glossary', digest: '' } },
    ])
    expect(result.book_bindings).toEqual([
      { ref: { source_kind: 'world', source_id: 'harbor', kind: 'lorebook', id: 'world:harbor', digest: '' }, role: 'primary', order: 100 },
      { ref: { source_kind: 'user', source_id: 'glossary', kind: 'lorebook', id: 'global:glossary', digest: '' }, role: 'runtime', order: 111 },
    ])
  })

  it('distinguishes automatic book resolution from an explicit empty selection', () => {
    const automatic = applyLorebookSource(base, '__builtin__', 'harbor', [], idFactory)
    expect(automatic).not.toHaveProperty('book_bindings')
    const explicitEmpty = applyLorebookSource(base, '__builtin__', 'harbor', [], idFactory, undefined, [])
    expect(explicitEmpty.book_bindings).toEqual([])
  })
})
