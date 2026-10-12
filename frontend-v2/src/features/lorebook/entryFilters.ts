// 世界书条目列表的搜索 / 筛选：纯粹在「已经加载的条目」上计算，
// 不新增查询接口、也不改 fetch 载荷——服务端过滤会让分页与激活预览失真。
import type { LoreEntry } from '@/api/types'
import { visibilityModeOf, type LoreVisibilityMode } from './visibility'

export const LORE_TYPE_ORDER = [
  'npc', 'location', 'faction', 'item', 'event', 'puzzle', 'spell', 'class', 'other',
] as const

/**
 * 产品语义的「触发方式」：由 is_constant 与 vector_activation 两个 canonical 字段共同表达。
 * 这是编辑器第一屏与条目列表筛选共用的唯一口径，legacy match_mode 不再冒充它。
 */
export const LORE_PRODUCT_ACTIVATION_MODES = ['keyword', 'always', 'hybrid', 'semantic'] as const

export type LoreProductActivationMode = (typeof LORE_PRODUCT_ACTIVATION_MODES)[number]

/** canonical vector_activation 取值（与后端 CANONICAL_VECTOR_ACTIVATION 对齐）。 */
export const LORE_VECTOR_ACTIVATION_MODES = ['off', 'hybrid', 'vector_only'] as const

/** 产品触发方式的最小模型形状：编辑器只依赖这两个字段。 */
export interface LoreActivationFields {
  is_constant?: unknown
  vector_activation?: unknown
}

/**
 * 与后端 store.normalize_vector_activation 同向：未知/缺失一律落到 canonical 默认 hybrid。
 * 「读路径兜底成 off」正是 off 与 hybrid 互相打架的根源，这里必须与后端一致。
 */
export function normalizeVectorActivation(value: unknown): string {
  const mode = String(value ?? '').trim().toLowerCase()
  return (LORE_VECTOR_ACTIVATION_MODES as readonly string[]).includes(mode) ? mode : 'hybrid'
}

/** 从 canonical 字段派生产品触发方式：is_constant 优先，其余看 vector_activation。 */
export function loreProductActivation(entry: LoreActivationFields): LoreProductActivationMode {
  if (entry.is_constant) return 'always'
  const mode = normalizeVectorActivation(entry.vector_activation)
  if (mode === 'off') return 'keyword'
  if (mode === 'vector_only') return 'semantic'
  return 'hybrid'
}

/**
 * 反向写入 canonical 字段（产品契约）：
 * - 关键词 → is_constant=false，vector_activation=off
 * - 始终生效 → is_constant=true，vector_activation 保持模型当前值
 * - 关键词 + 语义 → is_constant=false，vector_activation=hybrid
 * - 仅语义 → is_constant=false，vector_activation=vector_only
 */
export function applyLoreProductActivation(
  entry: LoreActivationFields,
  mode: LoreProductActivationMode,
): { is_constant: boolean; vector_activation: string } {
  const current = normalizeVectorActivation(entry.vector_activation)
  if (mode === 'always') return { is_constant: true, vector_activation: current }
  return {
    is_constant: false,
    vector_activation: mode === 'keyword' ? 'off' : mode === 'semantic' ? 'vector_only' : 'hybrid',
  }
}

export type LoreEntryStateFilter = 'all' | 'enabled' | 'disabled'
export type LoreEntryVisibilityFilter = 'all' | LoreVisibilityMode

export interface LoreEntryFilters {
  search: string
  /** 类型过滤与分类 tab 共用同一个 canonical 值：'all' 或 LORE_TYPE_ORDER 之一。 */
  type: string
  visibility: LoreEntryVisibilityFilter
  state: LoreEntryStateFilter
  /**
   * 产品触发方式（is_constant + vector_activation 派生），空串表示不过滤。
   * 这里不能用 'all' 当哨兵：legacy match_mode 的 'all' 是合法取值。
   */
  activation: string
  /** canonical 来源标签：'all' 或 loreEntrySource() 的取值。 */
  source: string
}

export const DEFAULT_LORE_ENTRY_FILTERS: LoreEntryFilters = {
  search: '',
  type: 'all',
  visibility: 'all',
  state: 'all',
  activation: '',
  source: 'all',
}

function rowOf(entry: LoreEntry): Record<string, unknown> {
  return entry as unknown as Record<string, unknown>
}

export function normalizeLoreEntryType(type: unknown): string {
  const text = String(type || 'other')
  return (LORE_TYPE_ORDER as readonly string[]).includes(text) ? text : 'other'
}

/** 后端把 enabled 存成 0/1；字段缺失按 canonical 默认视为启用。 */
export function loreEntryEnabled(entry: LoreEntry): boolean {
  const raw = rowOf(entry).enabled
  if (raw === undefined || raw === null) return true
  if (typeof raw === 'boolean') return raw
  if (typeof raw === 'number') return raw !== 0
  const text = String(raw).trim().toLowerCase()
  return !(text === '' || text === '0' || text === 'false')
}

/** 条目的产品触发方式（与编辑器第一屏同一口径）。 */
export function loreEntryActivation(entry: LoreEntry): LoreProductActivationMode {
  return loreProductActivation(rowOf(entry))
}

/** 条目的来源标签：优先插件来源，其次 provenance（对象或 JSON 字符串）。 */
export function loreEntrySource(entry: LoreEntry): string {
  const row = rowOf(entry)
  const plugin = String(row.source_plugin || '').trim()
  if (plugin) return plugin
  const provenance = row.provenance
  if (provenance && typeof provenance === 'object' && !Array.isArray(provenance)) {
    const data = provenance as Record<string, unknown>
    return String(data.source || data.source_id || data.kind || '').trim()
  }
  const text = String(provenance || '').trim()
  if (!text) return ''
  try {
    const parsed = JSON.parse(text) as Record<string, unknown>
    return String(parsed.source || parsed.source_id || parsed.kind || '').trim()
  } catch {
    return text
  }
}

export function loreEntryVisibility(entry: LoreEntry): LoreVisibilityMode {
  return visibilityModeOf(rowOf(entry).visible_to)
}

/** 搜索命中范围：名称、内容、触发词（以及可读的摘要/描述）。 */
export function loreEntrySearchText(entry: LoreEntry): string {
  const row = rowOf(entry)
  const keywords = Array.isArray(entry.keywords) ? entry.keywords : []
  return [entry.name, entry.content, entry.summary, entry.description, row.secondary_keys, ...keywords]
    .flatMap(value => Array.isArray(value) ? value : [value])
    .map(value => String(value ?? ''))
    .join('\n')
    .toLowerCase()
}

export function matchesLoreEntrySearch(entry: LoreEntry, search: string): boolean {
  const needle = String(search || '').trim().toLowerCase()
  if (!needle) return true
  return loreEntrySearchText(entry).includes(needle)
}

export function matchesLoreEntryFilters(entry: LoreEntry, filters: LoreEntryFilters): boolean {
  if (filters.type !== 'all' && normalizeLoreEntryType(entry.type) !== filters.type) return false
  if (filters.visibility !== 'all' && loreEntryVisibility(entry) !== filters.visibility) return false
  if (filters.state === 'enabled' && !loreEntryEnabled(entry)) return false
  if (filters.state === 'disabled' && loreEntryEnabled(entry)) return false
  if (filters.activation && loreEntryActivation(entry) !== filters.activation) return false
  if (filters.source !== 'all' && loreEntrySource(entry) !== filters.source) return false
  return matchesLoreEntrySearch(entry, filters.search)
}

export function filterLoreEntries(entries: LoreEntry[], filters: LoreEntryFilters): LoreEntry[] {
  return entries.filter(entry => matchesLoreEntryFilters(entry, filters))
}

export function loreEntrySourceOptions(entries: LoreEntry[]): string[] {
  return [...new Set(entries.map(loreEntrySource).filter(Boolean))].sort()
}

export function loreEntryActivationOptions(entries: LoreEntry[]): LoreProductActivationMode[] {
  const present = new Set(entries.map(loreEntryActivation))
  return LORE_PRODUCT_ACTIVATION_MODES.filter(mode => present.has(mode))
}

export function isLoreEntryFilterActive(filters: LoreEntryFilters): boolean {
  return filters.visibility !== 'all'
    || filters.state !== 'all'
    || filters.activation !== ''
    || filters.source !== 'all'
    || !!String(filters.search || '').trim()
}
