import { describe, expect, it } from 'vitest'
import type { LoreEntry } from '../src/api/types'
import {
  DEFAULT_LORE_ENTRY_FILTERS,
  applyLoreProductActivation,
  filterLoreEntries,
  isLoreEntryFilterActive,
  loreEntryActivationOptions,
  loreEntryEnabled,
  loreEntrySource,
  loreEntrySourceOptions,
  loreProductActivation,
  matchesLoreEntryFilters,
  normalizeVectorActivation,
} from '../src/features/lorebook/entryFilters'

function entry(overrides: Partial<LoreEntry> & Record<string, unknown> = {}): LoreEntry {
  return { id: 'e1', name: '城门守卫', type: 'npc', content: '公开背景', ...overrides } as LoreEntry
}

const ENTRIES: LoreEntry[] = [
  entry({ id: 'a', name: '城门守卫', type: 'npc', content: '公开背景', keywords: ['城门'], visible_to: ['*'], enabled: 1, match_mode: 'any', is_constant: false, vector_activation: 'off' }),
  entry({ id: 'b', name: '秘血教派', type: 'faction', content: '莱拉的私人线索', keywords: ['血', '教派'], visible_to: ['u1'], enabled: 0, match_mode: 'all', is_constant: false, vector_activation: 'hybrid' }),
  entry({ id: 'c', name: '幕后黑手', type: 'npc', content: 'GM 秘密', visible_to: [], source_plugin: 'demo_plugin', match_mode: 'not_any', is_constant: true, vector_activation: 'off' }),
]

function ids(rows: LoreEntry[]) {
  return rows.map(row => row.id)
}

describe('lore entry search', () => {
  it('matches name, content, and keywords case-insensitively', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: '城门' }))).toEqual(['a'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: '私人线索' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: '教派' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: 'GM 秘密' }))).toEqual(['c'])
  })

  it('ignores surrounding whitespace and keeps everything when empty', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: '   ' }))).toEqual(['a', 'b', 'c'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: ' 血 ' }))).toEqual(['b'])
  })
})

describe('lore entry filters', () => {
  it('filters by canonical type', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, type: 'npc' }))).toEqual(['a', 'c'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, type: 'faction' }))).toEqual(['b'])
  })

  it('classifies visibility with the shared normalizer', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, visibility: 'public' }))).toEqual(['a'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, visibility: 'characters' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, visibility: 'gm' }))).toEqual(['c'])
  })

  it('treats a missing enabled flag as enabled and 0 as disabled', () => {
    expect(loreEntryEnabled(ENTRIES[0])).toBe(true)
    expect(loreEntryEnabled(ENTRIES[1])).toBe(false)
    expect(loreEntryEnabled(ENTRIES[2])).toBe(true)
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, state: 'disabled' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, state: 'enabled' }))).toEqual(['a', 'c'])
  })

  it('filters by the product activation concept derived from is_constant + vector_activation', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'keyword' }))).toEqual(['a'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'hybrid' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'always' }))).toEqual(['c'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'semantic' }))).toEqual([])
    expect(loreEntryActivationOptions(ENTRIES)).toEqual(['keyword', 'always', 'hybrid'])
  })

  it('keys the activation filter off the product fields, not legacy match_mode', () => {
    // 两行的 legacy match_mode 完全相同，产品档位却不同：筛选必须按产品档位分组。
    const rows = [
      entry({ id: 'kw', match_mode: 'all', is_constant: false, vector_activation: 'off' }),
      entry({ id: 'both', match_mode: 'all', is_constant: false, vector_activation: 'hybrid' }),
      entry({ id: 'always', match_mode: 'all', is_constant: true, vector_activation: 'vector_only' }),
    ]
    expect(ids(filterLoreEntries(rows, { ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'keyword' }))).toEqual(['kw'])
    expect(ids(filterLoreEntries(rows, { ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'hybrid' }))).toEqual(['both'])
    expect(ids(filterLoreEntries(rows, { ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'always' }))).toEqual(['always'])
    // legacy match_mode 的 'all' 不再是一种筛选值（空串是唯一哨兵）。
    expect(isLoreEntryFilterActive({ ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'keyword' })).toBe(true)
  })

  it('reads the source from source_plugin and provenance', () => {
    expect(loreEntrySource(ENTRIES[0])).toBe('')
    expect(loreEntrySource(ENTRIES[2])).toBe('demo_plugin')
    expect(loreEntrySource(entry({ provenance: { source: 'sillytavern' } }))).toBe('sillytavern')
    expect(loreEntrySource(entry({ provenance: '{"kind":"import"}' }))).toBe('import')
    expect(loreEntrySourceOptions(ENTRIES)).toEqual(['demo_plugin'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, source: 'demo_plugin' }))).toEqual(['c'])
  })

  it('combines every filter with AND', () => {
    const filters = { ...DEFAULT_LORE_ENTRY_FILTERS, type: 'npc', state: 'enabled' as const, search: '秘密' }
    expect(ids(filterLoreEntries(ENTRIES, filters))).toEqual(['c'])
    expect(ids(filterLoreEntries(ENTRIES, { ...filters, visibility: 'public' }))).toEqual([])
  })

  it('reports whether any filter is narrowing the list', () => {
    expect(isLoreEntryFilterActive(DEFAULT_LORE_ENTRY_FILTERS)).toBe(false)
    expect(isLoreEntryFilterActive({ ...DEFAULT_LORE_ENTRY_FILTERS, type: 'npc' })).toBe(false)
    expect(isLoreEntryFilterActive({ ...DEFAULT_LORE_ENTRY_FILTERS, search: 'x' })).toBe(true)
    expect(isLoreEntryFilterActive({ ...DEFAULT_LORE_ENTRY_FILTERS, state: 'disabled' })).toBe(true)
  })

  it('keeps the entry when only the search text matches nothing', () => {
    expect(matchesLoreEntryFilters(ENTRIES[0], DEFAULT_LORE_ENTRY_FILTERS)).toBe(true)
    expect(matchesLoreEntryFilters(ENTRIES[0], { ...DEFAULT_LORE_ENTRY_FILTERS, search: 'zzz' })).toBe(false)
  })
})

// 产品契约：第一屏「触发方式」= is_constant + vector_activation 的组合。
describe('product trigger mode mapping', () => {
  it('derives the selected mode from the canonical pair', () => {
    expect(loreProductActivation({ is_constant: true, vector_activation: 'off' })).toBe('always')
    expect(loreProductActivation({ is_constant: true, vector_activation: 'vector_only' })).toBe('always')
    expect(loreProductActivation({ is_constant: false, vector_activation: 'off' })).toBe('keyword')
    expect(loreProductActivation({ is_constant: false, vector_activation: 'hybrid' })).toBe('hybrid')
    expect(loreProductActivation({ is_constant: false, vector_activation: 'vector_only' })).toBe('semantic')
  })

  it('treats a missing or unknown vector_activation as the backend canonical default', () => {
    // 与后端 store.normalize_vector_activation 同向：缺失 → hybrid，绝不是 off。
    expect(normalizeVectorActivation(undefined)).toBe('hybrid')
    expect(normalizeVectorActivation('')).toBe('hybrid')
    expect(normalizeVectorActivation('nonsense')).toBe('hybrid')
    expect(normalizeVectorActivation('OFF')).toBe('off')
    expect(loreProductActivation({ is_constant: false })).toBe('hybrid')
  })

  it('writes the canonical pair for each selected mode', () => {
    expect(applyLoreProductActivation({ is_constant: false, vector_activation: 'hybrid' }, 'keyword'))
      .toEqual({ is_constant: false, vector_activation: 'off' })
    expect(applyLoreProductActivation({ is_constant: false, vector_activation: 'off' }, 'always'))
      .toEqual({ is_constant: true, vector_activation: 'off' })
    expect(applyLoreProductActivation({ is_constant: true, vector_activation: 'vector_only' }, 'always'))
      .toEqual({ is_constant: true, vector_activation: 'vector_only' })
    expect(applyLoreProductActivation({ is_constant: true, vector_activation: 'off' }, 'hybrid'))
      .toEqual({ is_constant: false, vector_activation: 'hybrid' })
    expect(applyLoreProductActivation({ is_constant: true, vector_activation: 'hybrid' }, 'semantic'))
      .toEqual({ is_constant: false, vector_activation: 'vector_only' })
  })

  it('round-trips every mode through the canonical pair', () => {
    for (const mode of ['keyword', 'always', 'hybrid', 'semantic'] as const) {
      const pair = applyLoreProductActivation({ is_constant: false, vector_activation: 'in' }, mode)
      expect(loreProductActivation(pair)).toBe(mode)
    }
  })
})
