import type { Locale } from '@/i18n'
const values = {
  'zh-CN': { unsaved: '条目尚未保存', discardHint: '离开会丢弃当前条目的修改。要继续编辑还是放弃修改？', discard: '放弃修改', keep: '继续编辑', back: '返回条目列表', choose: '在左侧选择条目，查看完整资料或编辑。', filters: '更多筛选', context: '世界与资料册', ai: 'AI 生成条目' },
  en: { unsaved: 'Unsaved entry', discardHint: 'Leaving discards your changes. Keep editing or discard them?', discard: 'Discard changes', keep: 'Keep editing', back: 'Back to entries', choose: 'Select an entry to read or edit its full details.', filters: 'More filters', context: 'World and lorebook', ai: 'Generate entries with AI' },
  ja: { unsaved: '未保存の変更', discardHint: '移動すると変更は失われます。編集を続けますか？', discard: '変更を破棄', keep: '編集を続ける', back: '一覧に戻る', choose: '項目を選択して資料を表示・編集します。', filters: '詳細フィルター', context: '世界と資料集', ai: 'AIで項目を生成' },
  de: { unsaved: 'Ungespeicherter Eintrag', discardHint: 'Beim Verlassen gehen die Änderungen verloren. Weiter bearbeiten?', discard: 'Änderungen verwerfen', keep: 'Weiter bearbeiten', back: 'Zur Eintragsliste', choose: 'Wählen Sie einen Eintrag zum Lesen oder Bearbeiten.', filters: 'Weitere Filter', context: 'Welt und Lorebook', ai: 'Einträge mit KI erstellen' },
  ru: { unsaved: 'Несохранённая запись', discardHint: 'При выходе изменения будут потеряны. Продолжить редактирование?', discard: 'Отменить изменения', keep: 'Продолжить', back: 'К списку записей', choose: 'Выберите запись для просмотра или редактирования.', filters: 'Другие фильтры', context: 'Мир и книга', ai: 'Создать записи с ИИ' },
}
export function loreWorkspaceCopy(locale: Locale) { return values[locale] || values.en }
