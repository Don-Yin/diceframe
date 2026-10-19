import type { Locale } from '@/i18n'
const zh = { mode: '分支推进方式', parallel: '开启所有满足条件的分支', exclusive: '由队伍选择一条路线', label: '选项文字', confirm: '确认队伍选择', request: '提出路线选择', pending: '选择已提出，等待 GM 确认', requests: '玩家提出的选择', selected: '已确认的选择' }
const values: Record<Locale, typeof zh> = {
  'zh-CN': zh,
  en: { mode: 'Branch progression', parallel: 'Open every eligible branch', exclusive: 'Party selects one route', label: 'Option text', confirm: 'Confirm party choice', request: 'Propose route', pending: 'Choice proposed; waiting for GM confirmation', requests: 'Player proposals', selected: 'Confirmed choice' },
  ja: { mode: '分岐の進行方式', parallel: '条件を満たすすべての分岐を開始', exclusive: '一つの経路を選択', label: '選択肢の表示', confirm: 'チームの選択を確定', request: '経路を提案', pending: '提案済み：GM の確認待ち', requests: 'プレイヤーの提案', selected: '確定した選択' },
  de: { mode: 'Zweigfortschritt', parallel: 'Alle erlaubten Zweige öffnen', exclusive: 'Gruppe wählt einen Weg', label: 'Optionstext', confirm: 'Gruppenwahl bestätigen', request: 'Weg vorschlagen', pending: 'Vorgeschlagen; wartet auf GM-Bestätigung', requests: 'Spielervorschläge', selected: 'Bestätigte Wahl' },
  ru: { mode: 'Переход по ветвям', parallel: 'Открыть все доступные ветви', exclusive: 'Группа выбирает один путь', label: 'Текст варианта', confirm: 'Подтвердить выбор группы', request: 'Предложить путь', pending: 'Выбор предложен; ожидается подтверждение GM', requests: 'Предложения игроков', selected: 'Подтверждённый выбор' },
}
export const choiceCopy = (locale: Locale) => values[locale]
