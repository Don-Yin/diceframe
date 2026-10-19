import type { Locale } from '@/i18n'

const labels: Record<Locale, string> = {
  'zh-CN': '当前场景',
  en: 'Current scene',
  ja: '現在のシーン',
  de: 'Aktuelle Szene',
  ru: 'Текущая сцена',
}

export function sceneLabel(locale: Locale): string {
  return labels[locale] || labels.en
}

const tools: Record<Locale, string> = {
  'zh-CN': '游戏工具', en: 'Game tools', de: 'Spielwerkzeuge', ja: 'ゲームツール', ru: 'Инструменты игры',
}
export function gameToolsLabel(locale: Locale): string { return tools[locale] || tools.en }
