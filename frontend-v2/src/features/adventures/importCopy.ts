import type { Locale } from '@/i18n'
const zh = { connect: '按资料顺序连接空分支', title: '剧本与外部模组导入', formats: '支持 Markdown/TXT、Foundry Adventure JSON、Fantasy Grounds XML/.mod 和有文字层的 PDF。导入只会先生成可检查的草稿，不会直接发布给玩家。', resources: '冒险资源', add: '添加资源', edit: '编辑', remove: '删除', native: '完整资源数据', apply: '应用 JSON 编辑', invalid: '资源必须是 JSON 对象，并保留类型与身份', npc: 'NPC / 角色资料', item: '物品资料', scene: '场景资料', map_location: '地点 / 地图资料', encounter_catalog: '遭遇目录', reference: '外部数据已转为可编辑资料。数值、连接和规则效果需要在原生编辑器中确认，不自动猜测。', media: '外部媒体路径尚未物化。图片请通过本机图片库导入后设置；不会自动下载远端资源。', scripts: '宏、脚本和音乐播放列表已跳过。', pdf: 'PDF 按文字层逐页提取，请检查顺序、分栏和 GM 秘密；扫描件需要 OCR。', gates: '开放条件（全部满足）', addGate: '添加条件', type: '条件类型', identity: '身份 / 事实键', value: '预期值（JSON）', refs: '引用映射', node: '关联场景', map: '关联所选资源', pick: '请选择', hint: '先创建或编辑原生资源，再选择匹配类型的资源和目标场景；保留为文字会移除运行时引用。' }
const values: Record<Locale, typeof zh> = {
  'zh-CN': zh,
  en: { connect: 'Connect empty branches in document order', title: 'Import scripts and external adventures', formats: 'Markdown/TXT, Foundry Adventure JSON, Fantasy Grounds XML/.mod and text-layer PDF. Imported content starts GM-only; review before publishing it to players.', resources: 'Adventure resources', add: 'Add resource', edit: 'Edit', remove: 'Delete', native: 'Complete resource data', apply: 'Apply JSON edits', invalid: 'Resource must be a JSON object with its type and identity', npc: 'NPC / Character reference', item: 'Item reference', scene: 'Scene reference', map_location: 'Location / Map reference', encounter_catalog: 'Encounter catalog', reference: 'Foreign data becomes editable reference material. Confirm numbers, connections and rule effects in the native editor; they are never guessed.', media: 'External media paths were not materialized. Import images into the local image library before linking them. Remote resources are never downloaded automatically.', scripts: 'Macros, scripts and music playlists were skipped.', pdf: 'PDF text is extracted per page. Review ordering, columns and GM secrets; scans require OCR.', gates: 'Opening conditions (all required)', addGate: 'Add condition', type: 'Condition type', identity: 'Identity / Fact key', value: 'Expected value (JSON)', refs: 'Reference mapping', node: 'Linked scene', map: 'Link selected resource', pick: 'Choose', hint: 'Create or edit native resources, then select a resource of the matching type and its scene. Keeping prose removes the runtime reference.' },
  ja: { connect: '資料順に空の分岐を接続', title: 'シナリオと外部冒険の読み込み', formats: 'Markdown/TXT、Foundry Adventure JSON、Fantasy Grounds XML/.mod、文字層のある PDF に対応。初期状態は GM 専用です。確認後に公開してください。', resources: '冒険リソース', add: 'リソースを追加', edit: '編集', remove: '削除', native: '全リソースデータ', apply: 'JSON 編集を適用', invalid: '種類と ID を含む JSON オブジェクトが必要です', npc: 'NPC / キャラクター資料', item: 'アイテム資料', scene: 'シーン資料', map_location: '場所 / 地図資料', encounter_catalog: '遭遇カタログ', reference: '外部データは編集可能な資料になります。数値、接続、ルール効果は原生エディターで確認してください。自動推測は行いません。', media: '外部画像パスはコピーされていません。画像をローカルライブラリに読み込んで設定してください。遠隔リソースは自動取得されません。', scripts: 'マクロ、スクリプト、音楽リストは省略しました。', pdf: '文字層をページごとに抽出しました。順序、段組み、GM の秘密を確認してください。スキャンには OCR が必要です。', gates: '開始条件（すべて必要）', addGate: '条件を追加', type: '条件の種類', identity: 'ID / 事実キー', value: '期待値（JSON）', refs: '参照の対応付け', node: '関連シーン', map: '選択リソースを関連付け', pick: '選択', hint: '原生リソースを作成・編集し、同じ種類のリソースとシーンを選択してください。本文として保持すると実行時参照を解除します。' },
  de: { connect: 'Leere Zweige in Dokumentreihenfolge verbinden', title: 'Skripte und externe Abenteuer importieren', formats: 'Markdown/TXT, Foundry Adventure JSON, Fantasy Grounds XML/.mod und PDF mit Textebene. Importierte Inhalte sind zunächst nur für den GM sichtbar.', resources: 'Abenteuerressourcen', add: 'Ressource hinzufügen', edit: 'Bearbeiten', remove: 'Löschen', native: 'Vollständige Ressourcendaten', apply: 'JSON anwenden', invalid: 'JSON-Objekt mit Typ und Identität erforderlich', npc: 'NPC / Charakterreferenz', item: 'Gegenstandsreferenz', scene: 'Szenenreferenz', map_location: 'Ort / Kartenreferenz', encounter_catalog: 'Begegnungskatalog', reference: 'Externe Daten werden bearbeitbares Referenzmaterial. Zahlen, Verbindungen und Regeleffekte im nativen Editor bestätigen; sie werden nicht erraten.', media: 'Externe Bilder wurden nicht kopiert. Bilder lokal importieren und danach verknüpfen. Keine automatischen Downloads.', scripts: 'Makros, Skripte und Musiklisten übersprungen.', pdf: 'PDF-Texte seitenweise extrahiert. Reihenfolge, Spalten und GM-Geheimnisse prüfen; Scans benötigen OCR.', gates: 'Öffnungsbedingungen (alle erforderlich)', addGate: 'Bedingung hinzufügen', type: 'Bedingungstyp', identity: 'Identität / Faktenschlüssel', value: 'Erwarteter Wert (JSON)', refs: 'Verweise zuordnen', node: 'Verknüpfte Szene', map: 'Ressource verknüpfen', pick: 'Auswählen', hint: 'Native Ressourcen erstellen oder bearbeiten, dann passende Ressource und Szene wählen. Als Text behalten entfernt den Laufzeitverweis.' },
  ru: { connect: 'Соединить пустые ветви по порядку документа', title: 'Импорт сценариев и внешних приключений', formats: 'Markdown/TXT, Foundry Adventure JSON, Fantasy Grounds XML/.mod и PDF с текстовым слоем. Импортированные данные сначала видит только GM.', resources: 'Ресурсы приключения', add: 'Добавить ресурс', edit: 'Редактировать', remove: 'Удалить', native: 'Полные данные ресурса', apply: 'Применить JSON', invalid: 'Нужен объект JSON с типом и идентификатором', npc: 'NPC / Сведения о персонаже', item: 'Сведения о предмете', scene: 'Сведения о сцене', map_location: 'Место / Карта', encounter_catalog: 'Каталог встреч', reference: 'Внешние данные становятся редактируемыми справочными материалами. Подтвердите числа, связи и эффекты правил в редакторе; они не угадываются.', media: 'Внешние изображения не скопированы. Импортируйте их в локальную библиотеку и задайте связь. Автоматической загрузки нет.', scripts: 'Макросы, скрипты и списки музыки пропущены.', pdf: 'Текст PDF извлечён по страницам. Проверьте порядок, колонки и секреты GM; сканы требуют OCR.', gates: 'Условия открытия (все обязательны)', addGate: 'Добавить условие', type: 'Тип условия', identity: 'Идентификатор / Ключ факта', value: 'Ожидаемое значение (JSON)', refs: 'Связывание ресурсов', node: 'Связанная сцена', map: 'Связать ресурс', pick: 'Выбрать', hint: 'Создайте или измените ресурс, затем выберите ресурс нужного типа и сцену. Сохранение как текста удаляет ссылку времени выполнения.' },
}
const publishHints = {
  'zh-CN': {
    publishNeeds: '发布前还需完成：',
    publishPending: '资源数据有未应用的编辑，或条件值格式有误。请先处理编辑器中的提示，再重新校验。',
    publishValidate: '内容已修改或校验未完成，请点击“重新校验”。',
    publishReview: '请勾选“我已检查内容、分支、规则需求和 GM 私密信息”。',
    publishBusy: '正在处理，请稍候。',
    publishReady: '检查已通过，可以保存到你的冒险库。',
  },
  en: {
    publishNeeds: 'Before publishing:',
    publishPending: 'Resource edits have not been applied, or a condition value is invalid. Resolve the editor feedback, then validate again.',
    publishValidate: 'Content has changed or validation is incomplete. Click “Validate again”.',
    publishReview: 'Check the box confirming that you reviewed the content, branches, rules requirements, and GM secrets.',
    publishBusy: 'Processing, please wait.',
    publishReady: 'Checks passed. You can save this to your adventure library.',
  },
  ja: {
    publishNeeds: '公開する前に：',
    publishPending: '未適用のリソース編集、または無効な条件値があります。エディターの表示を確認し、再検証してください。',
    publishValidate: '内容が変更されたか、検証が完了していません。「再検証」を押してください。',
    publishReview: '内容、分岐、必要なルール、GM の秘密を確認したことを示すチェックボックスを選択してください。',
    publishBusy: '処理中です。しばらくお待ちください。',
    publishReady: '検証が完了しました。冒険ライブラリに保存できます。',
  },
  de: {
    publishNeeds: 'Vor dem Veröffentlichen:',
    publishPending: 'Ressourcenänderungen wurden noch nicht angewendet oder ein Bedingungswert ist ungültig. Behebe die Hinweise im Editor und prüfe erneut.',
    publishValidate: 'Der Inhalt wurde geändert oder die Prüfung ist unvollständig. Klicke auf „Erneut prüfen“.',
    publishReview: 'Bestätige per Kontrollkästchen, dass du Inhalt, Zweige, Regelanforderungen und GM-Geheimnisse geprüft hast.',
    publishBusy: 'Wird verarbeitet. Bitte warten.',
    publishReady: 'Prüfung bestanden. Du kannst das Abenteuer in deiner Bibliothek speichern.',
  },
  ru: {
    publishNeeds: 'Перед публикацией:',
    publishPending: 'Изменения ресурсов не применены или значение условия неверно. Исправьте замечания редактора и повторите проверку.',
    publishValidate: 'Содержимое изменено или проверка не завершена. Нажмите «Проверить снова».',
    publishReview: 'Отметьте, что вы проверили содержимое, ветви, требования к правилам и секреты ведущего.',
    publishBusy: 'Обработка, подождите.',
    publishReady: 'Проверка пройдена. Приключение можно сохранить в библиотеку.',
  },
} satisfies Record<Locale, Record<'publishNeeds' | 'publishPending' | 'publishValidate' | 'publishReview' | 'publishBusy' | 'publishReady', string>>

export const importCopy = (locale: Locale) => ({ ...values[locale], ...publishHints[locale] })
