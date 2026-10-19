import type { Locale } from '@/i18n'

const values: Record<Locale, {
  librarySummary: string
  gameSummary: string
  libraryHint: string
  gameHint: string
  noneGame: string
  unavailableGame: string
  loadFailed: string
  retry: string
  loading: string
  showBooks: string
  hideBooks: string
  noBooks: string
  scope: string
  scopeGlobal: string
  scopeWorld: string
  scopeGame: string
  scopeCharacter: string
  scopeUnbound: string
  entries: string
  enabled: string
  disabled: string
  enabledState: string
  disabledState: string
}> = {
  'zh-CN': {
    librarySummary: '资料库已启用 {enabled} / {total} 本',
    gameSummary: '本局使用 {count} 本',
    libraryHint: '已启用表示允许使用；是否参与本局还取决于使用范围与本局选择。',
    gameHint: '按当前对局与视角列出资料来源，不代表本轮全部条目已触发。',
    noneGame: '未选择对局',
    unavailableGame: '无法确认本局资料',
    loadFailed: '资料册状态加载失败',
    retry: '重试',
    loading: '正在加载资料册状态……',
    showBooks: '查看资料册',
    hideBooks: '收起资料册',
    noBooks: '暂无资料册',
    scope: '范围',
    scopeGlobal: '全局',
    scopeWorld: '世界',
    scopeGame: '对局',
    scopeCharacter: '角色',
    scopeUnbound: '未绑定',
    entries: '条目',
    enabled: '已启用',
    disabled: '已停用',
    enabledState: '资料册已启用',
    disabledState: '资料册已停用',
  },
  en: {
    librarySummary: 'Library enabled {enabled} / {total}',
    gameSummary: '{count} books used in this game',
    libraryHint: 'Enabled permits use. Scope and this game’s selection determine whether a book is used here.',
    gameHint: 'Sources for the current game and viewer, not entries triggered this round.',
    noneGame: 'No game selected',
    unavailableGame: 'This game’s lore could not be confirmed',
    loadFailed: 'Could not load lorebook status',
    retry: 'Retry',
    loading: 'Loading lorebook status…',
    showBooks: 'View lorebooks',
    hideBooks: 'Hide lorebooks',
    noBooks: 'No lorebooks',
    scope: 'Scope',
    scopeGlobal: 'Global',
    scopeWorld: 'World',
    scopeGame: 'Game',
    scopeCharacter: 'Character',
    scopeUnbound: 'Unbound',
    entries: 'Entries',
    enabled: 'Enabled',
    disabled: 'Disabled',
    enabledState: 'Lorebook enabled',
    disabledState: 'Lorebook disabled',
  },
  ja: {
    librarySummary: '資料集の有効数 {enabled} / {total}',
    gameSummary: 'このゲームで使用中 {count} 件',
    libraryHint: '有効とは使用を許可する状態で、毎ラウンド項目が発動したことを意味しません。',
    gameHint: '現在のゲームと視点で使われる資料集をサーバーが確認します。',
    noneGame: 'ゲーム未選択',
    unavailableGame: 'このゲームの資料を確認できません',
    loadFailed: '資料集の状態を読み込めませんでした',
    retry: '再試行',
    loading: '資料集の状態を読み込んでいます…',
    showBooks: '資料集を表示',
    hideBooks: '資料集を隠す',
    noBooks: '資料集はありません',
    scope: '範囲',
    scopeGlobal: '全体',
    scopeWorld: 'ワールド',
    scopeGame: 'ゲーム',
    scopeCharacter: 'キャラクター',
    scopeUnbound: '未関連付け',
    entries: '項目',
    enabled: '有効',
    disabled: '無効',
    enabledState: '資料集を有効化',
    disabledState: '資料集を無効化',
  },
  de: {
    librarySummary: 'Bibliothek aktiviert {enabled} / {total}',
    gameSummary: '{count} Bücher in diesem Spiel verwendet',
    libraryHint: 'Aktiviert bedeutet, dass das Buch verwendet werden darf; seine Einträge müssen diese Runde nicht ausgelöst worden sein.',
    gameHint: 'Der Server bestätigt die Bücher für das aktuelle Spiel und die aktuelle Sicht.',
    noneGame: 'Kein Spiel ausgewählt',
    unavailableGame: 'Die Inhalte dieses Spiels konnten nicht bestätigt werden',
    loadFailed: 'Lorebook-Status konnte nicht geladen werden',
    retry: 'Erneut versuchen',
    loading: 'Lorebook-Status wird geladen…',
    showBooks: 'Lorebooks anzeigen',
    hideBooks: 'Lorebooks ausblenden',
    noBooks: 'Keine Lorebooks',
    scope: 'Bereich',
    scopeGlobal: 'Global',
    scopeWorld: 'Welt',
    scopeGame: 'Spiel',
    scopeCharacter: 'Charakter',
    scopeUnbound: 'Nicht zugeordnet',
    entries: 'Einträge',
    enabled: 'Aktiviert',
    disabled: 'Deaktiviert',
    enabledState: 'Lorebook aktiviert',
    disabledState: 'Lorebook deaktiviert',
  },
  ru: {
    librarySummary: 'В библиотеке включено: {enabled} / {total}',
    gameSummary: 'В этой игре используется: {count}',
    libraryHint: 'Включение разрешает использование книги, но не означает, что её записи сработали в этом раунде.',
    gameHint: 'Сервер подтверждает книги для текущей игры и выбранного представления.',
    noneGame: 'Игра не выбрана',
    unavailableGame: 'Не удалось подтвердить материалы этой игры',
    loadFailed: 'Не удалось загрузить состояние лорбуков',
    retry: 'Повторить',
    loading: 'Загрузка состояния лорбуков…',
    showBooks: 'Показать лорбуки',
    hideBooks: 'Скрыть лорбуки',
    noBooks: 'Лорбуков нет',
    scope: 'Область',
    scopeGlobal: 'Глобально',
    scopeWorld: 'Мир',
    scopeGame: 'Игра',
    scopeCharacter: 'Персонаж',
    scopeUnbound: 'Не привязан',
    entries: 'Записи',
    enabled: 'Включён',
    disabled: 'Отключён',
    enabledState: 'Лорбук включён',
    disabledState: 'Лорбук отключён',
  },
}

export type UsageCopy = (typeof values)[Locale]
export const usageCopy = (locale: Locale): UsageCopy => values[locale]
