// 世界书条目可见性（编辑端）。
// 判定的单一事实来源在后端 src/knowledge/visibility.py；此处仅做编辑表单的
// 档位归类。canonical 公开标记是语言无关的 "*"，中英文写法只是识别别名——
// Locale 不得影响 mechanics。
export const PUBLIC_VISIBILITY_MARKERS = [
  '*', 'all', 'everyone', 'public', 'party', 'players',
  '公开', '所有人', '全体玩家',
] as const

export type LoreVisibilityMode = 'gm' | 'public' | 'characters'

// 历史数据的可见性可能是字符串形态：后端 visibility_values 兼容
// JSON 字符串（"[\"u1\"]"）与逗号分隔（"u1,u2"），DB 里也可能存着
// "public" 这样的原始字符串。编辑端统一先归一化成 string[]。
export function normalizeVisibilityValues(value: unknown): string[] {
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text) return []
    try {
      const parsed = JSON.parse(text) as unknown
      if (Array.isArray(parsed)) {
        return parsed.map(item => String(item).trim()).filter(Boolean)
      }
    } catch {
      // 不是合法 JSON：按逗号分隔字符串处理
    }
    return text.split(/[,，、]/).map(item => item.trim()).filter(Boolean)
  }
  if (Array.isArray(value)) {
    return value.map(item => String(item).trim()).filter(Boolean)
  }
  return []
}

export function visibilityModeOf(value: unknown): LoreVisibilityMode {
  const list = normalizeVisibilityValues(value)
  if (!list.length) return 'gm'
  const markers = new Set(PUBLIC_VISIBILITY_MARKERS.map(marker => marker.toLowerCase()))
  // 后端判定大小写不敏感（casefold），编辑端必须一致：历史 "PUBLIC" 一旦被
  // 归成「指定角色」，保存时 sanitizer 会把它剥掉 → 静默变成 GM-only。
  return list.some(item => markers.has(item.toLowerCase())) ? 'public' : 'characters'
}

// 「指定角色」档不允许混入 public marker：手输 * / public / 公开 会被剥掉，
// UI 档位与真实权限保持一致。trim、去空、大小写不敏感去重。
export function sanitizeCharacterVisibility(values: unknown): string[] {
  const markers = new Set(PUBLIC_VISIBILITY_MARKERS.map(marker => marker.toLowerCase()))
  const out: string[] = []
  for (const value of normalizeVisibilityValues(values)) {
    if (markers.has(value.toLowerCase())) continue
    if (out.some(existing => existing.toLowerCase() === value.toLowerCase())) continue
    out.push(value)
  }
  return out
}
