import type { CharacterCard } from '@/api/types'

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export function characterCardNeedsConversion(card: CharacterCard, targetRuleId?: string): boolean {
  const source = String(card.rule_id || '').trim()
  const target = String(targetRuleId || '').trim()
  return Boolean(source && target && source !== target)
}

/**
 * Adopting a library card replaces the seat's whole sheet.  Once that seat
 * has acted (server ``has_acted`` on the roster entry) only the GM may do it;
 * a player, or the owner previewing a seat with ``delegate`` on, is refused
 * with ``ADOPT_REQUIRES_GM``.  A fresh or just-claimed seat may still switch,
 * and joining with a card (a new seat) is unaffected.
 */
export function cardAdoptionLocked(
  seat: { has_acted?: boolean } | null | undefined,
  options: { isGm: boolean, delegate?: boolean },
): boolean {
  if (!seat?.has_acted) return false
  return !options.isGm || Boolean(options.delegate)
}

export function characterCardRuleName(card: CharacterCard, unboundLabel: string): string {
  return String(card.rule_name || card.rule_id || unboundLabel)
}

/**
 * A professional card is reusable only when its canonical blueprint carries the
 * exact rule/runtime binding selected by the game. Display metadata is not
 * enough: old and imported cards can claim a rule_id without containing the
 * choices needed for the server to rebuild mechanics safely.
 */
export function characterCardHasCompatibleProfessionalBlueprint(
  card: CharacterCard,
  targetRuleId?: string,
  targetRuntimeId?: string,
): boolean {
  const canonical = record(card.ruleset_character)
  const binding = record(canonical?.rule_binding)
  const ruleId = String(targetRuleId || '').trim()
  const runtimeId = String(targetRuntimeId || '').trim()
  if (!canonical || !binding || !ruleId || !runtimeId) return false
  return String(binding.rule_id || '').trim() === ruleId
    && String(binding.runtime_id || '').trim() === runtimeId
}
