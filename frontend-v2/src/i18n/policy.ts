import registry from '../../../src/localization/registry.json'
import { sourceFingerprint } from './fingerprint.js'
export { sourceFingerprint } from './fingerprint.js'

export type Locale = keyof typeof registry
export interface LocalePolicy { tier: string; status: string }
export interface MessageTree { [key: string]: string | MessageTree }
export const LOCALE_POLICY = registry
export const KNOWN_LOCALES = Object.keys(registry) as Locale[]
export const UI_LOCALES = KNOWN_LOCALES.filter(code => registry[code].status === 'active')

export function effectiveUiLocale(locale: Locale, policy: Partial<Record<Locale, LocalePolicy>> = registry): Locale {
  return policy[locale]?.status === 'paused' ? 'en' : locale
}

export function catalogForLocale(
  locale: Locale,
  english: MessageTree,
  translated: MessageTree,
  reviewed: Record<string, string>,
  policy: Partial<Record<Locale, LocalePolicy>> = registry,
): MessageTree {
  if (effectiveUiLocale(locale, policy) !== locale) return {}
  if (policy[locale]?.tier === 'core') return translated
  function filter(source: MessageTree, target: MessageTree, prefix: string): MessageTree {
    const result: MessageTree = {}
    for (const [key, text] of Object.entries(target)) {
      const original = source[key]
      const fullKey = prefix + key
      if (typeof text === 'string' && typeof original === 'string') {
        if (reviewed[fullKey] === sourceFingerprint(original)) result[key] = text
      } else if (typeof text === 'object' && typeof original === 'object') {
        const nested = filter(original, text, `${fullKey}.`)
        if (Object.keys(nested).length) result[key] = nested
      }
    }
    return result
  }
  return filter(english, translated, '')
}
