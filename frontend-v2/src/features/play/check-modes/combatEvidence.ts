import type { Locale } from '@/i18n'
import { modeCopy, modeText } from './copy'

export function combatRollEvidence(event: Record<string, unknown>, locale: Locale): string {
  const copy = modeCopy[locale]
  const natural = event.natural ?? event.roll ?? ''
  const rolls = Array.isArray(event.rolls) && event.rolls.every(v => Number.isInteger(v) && v >= 1 && v <= 20) ? event.rolls : []
  const dice = rolls.length > 1 ? `d20 [${rolls.join(', ')}] → ${natural}` : `d20 ${natural}`
  const mode = event.advantage_mode === 'advantage' || event.advantage_mode === 'disadvantage' ? modeText(copy, event.advantage_mode) : ''
  const sources = Array.isArray(event.advantage_sources) ? event.advantage_sources.flatMap(raw => {
    const source = raw as Record<string, unknown> | null
    if (!source || typeof source.code !== 'string') return []
    return [`${modeText(copy, source.code)}${typeof source.reason === 'string' ? `: ${source.reason}` : ''}`]
  }) : []
  return [dice, mode, ...sources].filter(Boolean).join(' · ')
}
