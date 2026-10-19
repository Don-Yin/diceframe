import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'
import { catalogForLocale, effectiveUiLocale, sourceFingerprint } from '@/i18n/policy'
import { messages, normalizeLocale } from '@/i18n'

describe('community translation policy', () => {
  const english = { hello: 'Hello {name}', added: 'New action' }
  const translated = { hello: 'Hallo {name}' }
  const reviewed = { hello: sourceFingerprint(english.hello) }

  it('shows current import formats in English until the community hint is reviewed', () => {
    const app = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages, missingWarn: false, fallbackWarn: false })
    expect(app.global.t('scriptImportHint')).toContain('PDF')
    if (messages.de.scriptImportHint === undefined) {
      expect(app.global.t('scriptImportHint')).toBe(messages.en.scriptImportHint)
    }
  })

  it('retains reviewed text and falls back to English for new keys', () => {
    const de = catalogForLocale('de', english, translated, reviewed)
    const app = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { en: english, de }, missingWarn: false, fallbackWarn: false })
    expect(app.global.t('hello', { name: 'Ada' })).toBe('Hallo Ada')
    expect(app.global.t('added')).toBe('New action')
  })

  it('does not let stale translations hide a changed English instruction', () => {
    const changed = { ...english, hello: 'Welcome {name}' }
    expect(catalogForLocale('de', changed, translated, reviewed)).toEqual({})
    expect(catalogForLocale('de', changed, translated, { hello: sourceFingerprint(changed.hello) })).toEqual(translated)
  })

  it('preserves nested API errors and reviews them independently', () => {
    const en = { apiErrors: { missing: 'Missing', changed: 'Changed' } }
    const de = { apiErrors: { missing: 'Fehlt', changed: 'Alt' } }
    expect(catalogForLocale('de', en, de, { 'apiErrors.missing': sourceFingerprint('Missing') })).toEqual({ apiErrors: { missing: 'Fehlt' } })
  })

  it('pauses UI translations while preserving saved language identities', () => {
    const paused = { 'zh-CN': { tier: 'core', status: 'active' }, en: { tier: 'core', status: 'active' }, de: { tier: 'community', status: 'paused' } } as const
    expect(effectiveUiLocale('de', paused)).toBe('en')
    expect(normalizeLocale('de-DE')).toBe('de')
    expect(catalogForLocale('de', english, translated, reviewed, paused)).toEqual({})
    expect(effectiveUiLocale('zh-CN', paused)).toBe('zh-CN')
  })
})
