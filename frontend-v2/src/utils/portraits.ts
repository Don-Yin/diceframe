import type { CharacterPortrait } from '@/api/types'

export interface BuiltinPortrait {
  id: string
  ruleId: string
  index: number
  style: 'realistic' | 'anime'
  image: string
  position: string
}

const SUPPORTED_RULES = new Set([
  'dnd5e',
  'freeform_coc',
  'freeform_cyberpunk',
  'freeform_fantasy',
  'freeform_wuxia',
  'tavern_free',
])

const RULE_PORTRAIT_FILES = [
  'realistic-1.jpg',
  'realistic-2.jpg',
  'realistic-3.jpg',
  'realistic-4.jpg',
  'anime-1.jpg',
  'anime-2.jpg',
  'anime-3.jpg',
  'anime-4.jpg',
] as const

export function builtinRule(ruleId?: string): string {
  const normalized = String(ruleId || '').replace(/_en$/, '')
  return SUPPORTED_RULES.has(normalized) ? normalized : 'freeform_fantasy'
}

function hash(value: string): number {
  let output = 2166136261
  for (let i = 0; i < value.length; i += 1) {
    output ^= value.charCodeAt(i)
    output = Math.imul(output, 16777619)
  }
  return output >>> 0
}

export function builtinPortraits(ruleId?: string): BuiltinPortrait[] {
  const rule = builtinRule(ruleId)
  return RULE_PORTRAIT_FILES.map((image, index) => ({
    id: `${rule}:${index}`,
    ruleId: rule,
    index,
    style: index < 4 ? 'realistic' : 'anime',
    image: `${import.meta.env.BASE_URL}avatars/v3/${rule}/${image}`,
    position: '50% 26%',
  }))
}

export function defaultBuiltinPortrait(ruleId?: string, seed?: string): BuiltinPortrait {
  const options = builtinPortraits(ruleId)
  return options[hash(`${builtinRule(ruleId)}|${seed || 'default'}`) % options.length]
}

export function resolveBuiltinPortrait(portrait?: CharacterPortrait | null, ruleId?: string, seed?: string): BuiltinPortrait {
  if (portrait?.kind === 'builtin' && portrait.id) {
    const [storedRule, rawIndex] = portrait.id.split(':')
    const options = builtinPortraits(storedRule)
    const index = Number(rawIndex)
    if (Number.isInteger(index) && index >= 0 && index < options.length) return options[index]
  }
  return defaultBuiltinPortrait(ruleId, seed)
}

export function initials(name?: string): string {
  const value = String(name || '?').trim()
  return Array.from(value).slice(0, 2).join('').toUpperCase() || '?'
}
