import type { Locale } from '@/composables/useLocale'

const en = {
  title: 'GM workspace', todo: 'To do', party: 'Party', scene: 'Scene', rules: 'Rules', settings: 'Settings',
  attention: 'Needs attention', requests: 'Check requests', retry: 'Check service needs attention',
  decisions: 'Check decisions waiting in the story', economy: 'Economy decision', health: 'System health event', quiet: 'No pending GM actions.',
  aiRecovery: 'AI seats need attention', actionRecovery: 'Review failed action',
}
type Copy = typeof en
const copies: Record<Locale, Copy> = {
  en,
  'zh-CN': { title: 'GM 工作台', todo: '待办', party: '队伍', scene: '场景', rules: '规则', settings: '设置', attention: '需要处理', requests: '检定申请', retry: '检定服务需要处理', decisions: '剧情中有待确认的检定', economy: '经济结算', health: '系统状态事件', quiet: '当前没有待处理的 GM 事项。', aiRecovery: 'AI 队友需要处理', actionRecovery: '查看行动恢复提示' },
  ja: { title: 'GM ワークスペース', todo: '要対応', party: 'パーティ', scene: '場面', rules: 'ルール', settings: '設定', attention: '対応が必要', requests: '判定申請', retry: '判定サービスを確認', decisions: '物語に確認待ちの判定があります', economy: '経済の決定', health: 'システム状態イベント', quiet: '対応が必要な GM 項目はありません。', aiRecovery: 'AI メンバーを確認', actionRecovery: '行動の復旧を確認' },
  de: { title: 'GM-Arbeitsbereich', todo: 'Aufgaben', party: 'Gruppe', scene: 'Szene', rules: 'Regeln', settings: 'Einstellungen', attention: 'Prüfung nötig', requests: 'Würfelanfragen', retry: 'Würfeldienst prüfen', decisions: 'Ausstehende Entscheidungen in der Geschichte', economy: 'Wirtschaftsentscheidung', health: 'Systemereignis', quiet: 'Keine offenen GM-Aufgaben.', aiRecovery: 'KI-Sitze prüfen', actionRecovery: 'Aktionswiederherstellung prüfen' },
  ru: { title: 'Рабочее место ГМ', todo: 'Задачи', party: 'Группа', scene: 'Сцена', rules: 'Правила', settings: 'Настройки', attention: 'Нужно внимание', requests: 'Запросы проверок', retry: 'Проверьте сервис проверок', decisions: 'В истории есть проверки для подтверждения', economy: 'Экономическое решение', health: 'Событие состояния системы', quiet: 'Нет ожидающих действий ведущего.', aiRecovery: 'Проверьте участников ИИ', actionRecovery: 'Проверьте восстановление действия' },
}
export const workbenchCopy = (locale: Locale): Copy => copies[locale] || en
