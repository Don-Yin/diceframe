import { i18n, localeChain, localeEndonym, normalizeLocale, SUPPORTED_LOCALES, type Locale, type MessageKey } from '@/i18n'

export interface LanguageTaggedContent {
  language?: unknown
}

/**
 * 内容语言选项契约：值就是全局 Locale，不在 Lorebook 里再养一套语言枚举。
 * 语言名统一显示自身名称（简体中文 / English / 日本語 / Deutsch），文案走 i18n。
 */
const CONTENT_LANGUAGE_LABEL_KEYS: Record<Locale, MessageKey> = {
  'zh-CN': 'contentLangZhCN', en: 'contentLangEn', ja: 'contentLangJa', de: 'contentLangDe', ru: 'contentLangRu',
}
export const CONTENT_LANGUAGE_OPTIONS = SUPPORTED_LOCALES.map(value => ({
  value, labelKey: CONTENT_LANGUAGE_LABEL_KEYS[value],
}))

export function contentLanguageLabelKey(locale: Locale): MessageKey {
  return CONTENT_LANGUAGE_OPTIONS.find(option => option.value === locale)?.labelKey ?? 'contentLangZhCN'
}

/** Built-in legacy content without a language marker is Chinese. */
export function contentLanguageOf(item: LanguageTaggedContent | null | undefined): Locale {
  return normalizeLocale(item?.language)
}

/**
 * Pick the best-matching content for a locale, falling back the way the backend
 * does: requested locale, then English, then Chinese. An exact-match filter left
 * every locale beyond zh-CN/en staring at an empty list, because no built-in
 * world, rule or template is tagged ja, de or ru.
 */
export function filterByContentLanguage<T extends LanguageTaggedContent>(
  items: T[],
  language: Locale,
): T[] {
  for (const candidate of localeChain(language)) {
    const matched = items.filter(item => contentLanguageOf(item) === candidate)
    if (matched.length) return matched
  }
  return []
}

/**
 * Display name of a content language, for pickers and "world · language · N
 * entries" lines. Uses the translated name where the catalogue has a key and the
 * locale's own name otherwise, keeping the project's existing convention.
 */
export function localeLabel(locale: Locale): string {
  if (locale === 'zh-CN') return i18n.global.t('chinese')
  if (locale === 'en') return i18n.global.t('english')
  if (locale === 'de') return i18n.global.t('german')
  return localeEndonym(locale)
}
