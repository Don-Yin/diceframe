import { createI18n } from 'vue-i18n'
import { en } from './messages/en'
import { ja } from './messages/ja'
import { de } from './messages/de'
import { zhCN } from './messages/zh-CN'

export type Locale = 'zh-CN' | 'en' | 'ja' | 'de'
export type MessageKey = keyof typeof zhCN

export const LOCALE_STORAGE_KEY = 'diceframe_locale'

export const messages = {
  'zh-CN': zhCN,
  en,
  ja,
  de,
} as const

export function normalizeLocale(value: unknown): Locale {
  const text = String(value || '').toLowerCase()
  if (text === 'ja' || text.startsWith('ja-') || text === '日本語') return 'ja'
  if (text === 'de' || text.startsWith('de-') || text === 'german' || text === 'deutsch') return 'de'
  return text === 'en' || text.startsWith('en-') ? 'en' : 'zh-CN'
}

function initialLocale(): Locale {
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY)
    if (stored) return normalizeLocale(stored)
  }
  if (typeof navigator !== 'undefined') {
    const preferred = navigator.languages?.find(Boolean) || navigator.language
    if (preferred) return normalizeLocale(preferred)
  }
  return 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  // 缺失语言（如 ja/de 尚未翻译的文案）回退英文，而非中文。
  fallbackLocale: 'en',
  messages,
  missingWarn: false,
  fallbackWarn: false,
})
