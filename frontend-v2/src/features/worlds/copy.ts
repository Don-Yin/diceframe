import type { Locale } from '@/i18n'

/** Copy that belongs to the world gallery, kept separate from lorebook editor wording. */
const values: Record<Locale, {
  intro: string
  purpose: string
  shortIntro: string
  materialCount: string
  materialHint: string
  editMaterials: string
  worldSetting: string
  starterScene: string
  definitionLoading: string
  definitionLoadFailed: string
  definitionRetry: string
  definitionReadonly: string
  cloneToEdit: string
  defaultsNotice: string
  materialsCopyTitle: string
  materialsCopyHint: string
  materialsCopyAction: string
}> = {
  'zh-CN': {
    intro: '挑选用于开团的背景世界；人物、地点与其他资料在资料册页面编辑。',
    purpose: '游玩背景',
    shortIntro: '简要介绍',
    materialCount: '{count} 条资料册内容',
    materialHint: '资料册内容',
    editMaterials: '编辑资料册',
    worldSetting: '世界背景',
    starterScene: '默认开场',
    definitionLoading: '正在加载世界背景……',
    definitionLoadFailed: '世界背景加载失败',
    definitionRetry: '重试',
    definitionReadonly: '内置或插件世界只读；请先克隆为我的世界，再编辑世界背景。',
    cloneToEdit: '克隆为我的世界并编辑',
    defaultsNotice: '这些默认值会用于之后新建的对局；已经开始的对局继续使用运行时已加载的内容。',
    materialsCopyTitle: '编辑资料册',
    materialsCopyHint: '这个世界的资料来自模板或内容包。创建“我的世界”副本后即可编辑资料册，原始内容与当前游戏会保留。',
    materialsCopyAction: '创建副本并编辑资料册',
  },
  en: {
    intro: 'Choose a world as the background for a game; edit people, places, and reference material in its lorebooks.',
    purpose: 'Game background',
    shortIntro: 'Short introduction',
    materialCount: '{count} lorebook entries',
    materialHint: 'Lorebook content',
    editMaterials: 'Edit lorebooks',
    worldSetting: 'World background',
    starterScene: 'Default opening',
    definitionLoading: 'Loading world background…',
    definitionLoadFailed: 'Could not load the world background',
    definitionRetry: 'Retry',
    definitionReadonly: 'Built-in and plugin worlds are read-only. Clone this world to edit its background.',
    cloneToEdit: 'Clone to my world and edit',
    defaultsNotice: 'These defaults apply to games created later; games already in progress keep their loaded runtime content.',
    materialsCopyTitle: 'Edit lorebooks',
    materialsCopyHint: 'This world comes from a template or content pack. Create a copy in My worlds to edit its lorebooks while preserving the source and current game.',
    materialsCopyAction: 'Create a copy and edit lorebooks',
  },
  ja: {
    intro: 'ゲームの背景となる世界を選びます。人物・場所などの資料は資料集ページで編集します。',
    purpose: 'ゲームの背景',
    shortIntro: '概要',
    materialCount: '資料集 {count} 件',
    materialHint: '資料集の内容',
    editMaterials: '資料集を編集',
    worldSetting: '世界背景',
    starterScene: 'デフォルトの導入',
    definitionLoading: '世界背景を読み込んでいます…',
    definitionLoadFailed: '世界背景を読み込めませんでした',
    definitionRetry: '再試行',
    definitionReadonly: '内蔵・プラグインの世界は読み取り専用です。編集するには自分の世界に複製してください。',
    cloneToEdit: '自分の世界に複製して編集',
    defaultsNotice: 'これらの既定値は後から作成するゲームに適用され、進行中のゲームは読み込み済みの内容を使い続けます。',
    materialsCopyTitle: '資料集を編集',
    materialsCopyHint: 'この世界はテンプレートまたはコンテンツパックの資料です。自分の世界に複製すると資料集を編集できます。元の資料と現在のゲームは保持されます。',
    materialsCopyAction: '複製して資料集を編集',
  },
  de: {
    intro: 'Wähle eine Welt als Spielhintergrund; Personen, Orte und weitere Inhalte bearbeitest du in den Lorebooks.',
    purpose: 'Spielhintergrund',
    shortIntro: 'Kurzbeschreibung',
    materialCount: '{count} Lorebook-Einträge',
    materialHint: 'Lorebook-Inhalt',
    editMaterials: 'Lorebooks bearbeiten',
    worldSetting: 'Welthintergrund',
    starterScene: 'Standarderöffnung',
    definitionLoading: 'Welthintergrund wird geladen…',
    definitionLoadFailed: 'Welthintergrund konnte nicht geladen werden',
    definitionRetry: 'Erneut versuchen',
    definitionReadonly: 'Integrierte und Plugin-Welten sind schreibgeschützt. Klone diese Welt, um ihren Hintergrund zu bearbeiten.',
    cloneToEdit: 'In meine Welt klonen und bearbeiten',
    defaultsNotice: 'Diese Standardwerte gelten für später erstellte Spiele; laufende Spiele behalten ihren bereits geladenen Laufzeitinhalt.',
    materialsCopyTitle: 'Lorebooks bearbeiten',
    materialsCopyHint: 'Diese Welt stammt aus einer Vorlage oder einem Inhaltspaket. Erstelle eine Kopie in Meine Welten, um ihre Lorebooks zu bearbeiten. Quelle und laufendes Spiel bleiben erhalten.',
    materialsCopyAction: 'Kopie erstellen und Lorebooks bearbeiten',
  },
  ru: {
    intro: 'Выберите мир для фона игры; персонажей, места и другие материалы редактируйте на странице лорбуков.',
    purpose: 'Фон игры',
    shortIntro: 'Краткое описание',
    materialCount: 'Записей лорбука: {count}',
    materialHint: 'Материалы лорбука',
    editMaterials: 'Изменить лорбуки',
    worldSetting: 'Фон мира',
    starterScene: 'Начальная сцена по умолчанию',
    definitionLoading: 'Загрузка фона мира…',
    definitionLoadFailed: 'Не удалось загрузить фон мира',
    definitionRetry: 'Повторить',
    definitionReadonly: 'Встроенные миры и миры плагинов доступны только для чтения. Скопируйте этот мир, чтобы изменить его фон.',
    cloneToEdit: 'Скопировать в мой мир и изменить',
    defaultsNotice: 'Эти значения применяются к новым играм; уже начатые игры продолжают использовать загруженное содержимое.',
    materialsCopyTitle: 'Изменить лорбуки',
    materialsCopyHint: 'Этот мир взят из шаблона или пакета материалов. Создайте копию в Моих мирах для редактирования лорбуков. Исходные материалы и текущая игра сохранятся.',
    materialsCopyAction: 'Создать копию и изменить лорбуки',
  },
}

export type WorldsCopy = (typeof values)[Locale]
export const worldsCopy = (locale: Locale): WorldsCopy => values[locale]
