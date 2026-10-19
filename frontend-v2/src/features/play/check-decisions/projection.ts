import type { CheckResult } from '@/api/types'
import type { Locale } from '@/i18n'
export function pendingPostChecks(detail: { pending_luck_decisions?: CheckResult[]; pending_push_decisions?: CheckResult[] } | null | undefined) {
  const records = [...(detail?.pending_luck_decisions || []), ...(detail?.pending_push_decisions || [])]
  return [...new Map(records.map(check => [check.check_id, check])).values()]
}
const waiting: Record<Locale, string> = {
  'zh-CN': '请先处理骰子卡片上的检定选择，再继续叙事。',
  en: 'Resolve the choices on the dice cards before continuing the story.',
  ja: '物語を続ける前に、ダイスカードの判定選択を完了してください。',
  de: 'Entscheide zuerst über die Proben auf den Würfelkarten, bevor die Geschichte weitergeht.',
  ru: 'Завершите выбор на карточках бросков, прежде чем продолжать историю.',
}
export const postCheckWaiting = (locale: Locale) => waiting[locale]
