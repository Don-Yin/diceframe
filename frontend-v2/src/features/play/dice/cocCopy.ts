import type { Locale } from '@/i18n'

export const cocCopy: Record<Locale, { units: string; tens: string; bonus: string; penalty: string; taken: string }> = {
  'zh-CN': { units: '共享个位', tens: '十位骰组合', bonus: '奖励骰', penalty: '惩罚骰', taken: '采用' },
  en: { units: 'Shared units', tens: 'Tens combinations', bonus: 'Bonus dice', penalty: 'Penalty dice', taken: 'Taken' },
  ja: { units: '共通の一の位', tens: '十の位の組合せ', bonus: 'ボーナスダイス', penalty: 'ペナルティダイス', taken: '採用' },
  de: { units: 'Gemeinsame Einerstelle', tens: 'Zehnerkombinationen', bonus: 'Bonuswürfel', penalty: 'Strafwürfel', taken: 'Verwendet' },
  ru: { units: 'Общие единицы', tens: 'Комбинации десятков', bonus: 'Бонусные кости', penalty: 'Штрафные кости', taken: 'Выбрано' },
}
