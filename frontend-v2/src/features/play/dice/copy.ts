import type { Locale } from '@/i18n'
const copy: Record<Locale, { show: string; hide: string; units: string; tens: string }> = {
  'zh-CN': { show: '展开骰盘', hide: '收起骰盘', units: '共享个位', tens: '十位骰' },
  en: { show: 'Show dice tray', hide: 'Hide dice tray', units: 'Shared units', tens: 'Tens die' },
  ja: { show: 'ダイストレイを開く', hide: 'ダイストレイを閉じる', units: '共通の一の位', tens: '十の位' },
  de: { show: 'Würfeltablett öffnen', hide: 'Würfeltablett schließen', units: 'Gemeinsame Einer', tens: 'Zehnerwürfel' },
  ru: { show: 'Открыть лоток кубиков', hide: 'Свернуть лоток кубиков', units: 'Общие единицы', tens: 'Кость десятков' },
}
export const dicePresentationCopy = (locale: Locale) => copy[locale]
