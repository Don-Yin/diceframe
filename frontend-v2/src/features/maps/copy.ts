import type { Locale } from '@/i18n'

const en = {
  title: 'World map', kicker: 'KNOWN PLACES', chooseGame: 'Game', loading: 'Loading map…',
  emptyGames: 'No games are available yet.', emptyMap: 'This game has no known places yet.',
  error: 'The map could not be loaded.', retry: 'Retry', backToPlay: 'Back to table',
  locations: 'Known places', readOnly: 'Browse this game’s known places and routes',
}
type Copy = typeof en
const values: Record<Locale, Copy> = {
  en,
  'zh-CN': { title: '世界地图', kicker: '已知地点', chooseGame: '游戏', loading: '正在加载地图…', emptyGames: '当前还没有可用游戏。', emptyMap: '这局还没有已知地点。', error: '地图加载失败。', retry: '重试', backToPlay: '返回团桌', locations: '已知地点', readOnly: '查看本局已知地点与路线' },
  ja: { title: 'ワールドマップ', kicker: '既知の場所', chooseGame: 'ゲーム', loading: 'マップを読み込み中…', emptyGames: '利用できるゲームがありません。', emptyMap: 'このゲームには既知の場所がありません。', error: 'マップを読み込めませんでした。', retry: '再試行', backToPlay: 'テーブルに戻る', locations: '既知の場所', readOnly: 'このゲームの既知の場所とルートを見る' },
  de: { title: 'Weltkarte', kicker: 'BEKANNTE ORTE', chooseGame: 'Spiel', loading: 'Karte wird geladen…', emptyGames: 'Noch keine Spiele verfügbar.', emptyMap: 'Dieses Spiel hat noch keine bekannten Orte.', error: 'Die Karte konnte nicht geladen werden.', retry: 'Erneut versuchen', backToPlay: 'Zum Tisch', locations: 'Bekannte Orte', readOnly: 'Bekannte Orte und Wege dieses Spiels ansehen' },
  ru: { title: 'Карта мира', kicker: 'ИЗВЕСТНЫЕ МЕСТА', chooseGame: 'Игра', loading: 'Карта загружается…', emptyGames: 'Доступных игр пока нет.', emptyMap: 'В этой игре пока нет известных мест.', error: 'Не удалось загрузить карту.', retry: 'Повторить', backToPlay: 'Вернуться к столу', locations: 'Известные места', readOnly: 'Известные места и маршруты этой игры' },
}
export function mapCopy(locale: Locale): Copy { return values[locale] || en }
