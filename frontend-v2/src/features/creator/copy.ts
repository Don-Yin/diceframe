import type { Locale } from '@/i18n'

export type CreatorCardId = 'adventures' | 'worlds' | 'lorebook' | 'rules' | 'modules' | 'textReview' | 'package'

export type CreatorCopy = {
  kicker: string
  title: string
  intro: string
  storyGroup: string
  foundationGroup: string
  sourceGroup: string
  toolGroup: string
  cards: Record<CreatorCardId, { title: string; description: string; action: string }>
}

const values: Record<Locale, CreatorCopy> = {
  'zh-CN': {
    kicker: '创作工具', title: '创作工坊', intro: '从已有工具开始制作冒险、世界、资料册、规则和内容来源。',
    storyGroup: '故事创作', foundationGroup: '世界与规则', sourceGroup: '内容来源', toolGroup: '文本工具',
    cards: {
      adventures: { title: '我的冒险编辑', description: '新建、导入、复制并编辑冒险包，审核后发布或直接开局。', action: '打开冒险创作' },
      worlds: { title: '世界制作', description: '管理世界、世界资料和与冒险开局相关的世界选择。', action: '打开世界' },
      lorebook: { title: '资料册', description: '编辑世界资料册、条目、绑定范围并导入已有资料。', action: '打开资料册' },
      rules: { title: '规则编辑', description: '查看和维护可用规则配置，保持规则结算由规则系统负责。', action: '打开规则' },
      modules: { title: '内容来源', description: '安装、导入、更新内容包，并查看包资源和来源身份。', action: '管理内容来源' },
      textReview: { title: '文本整理与分配', description: '按标题拆分普通文本，逐段选择保存到世界、资料册、角色模板或冒险。', action: '打开文本工具' },
      package: { title: '导出自制内容包', description: '把冒险、世界、资料册和角色资源打成可安装的 .dfplugin，方便分享和迁移。', action: '打开内容包导出' },
    },
  },
  en: {
    kicker: 'CREATION TOOLS', title: 'Creator workshop', intro: 'Use the existing tools to make adventures, worlds, lorebooks, rules, and content sources.',
    storyGroup: 'Story creation', foundationGroup: 'Worlds and rules', sourceGroup: 'Content sources', toolGroup: 'Text tools',
    cards: {
      adventures: { title: 'My adventure editor', description: 'Create, import, copy, edit, review, publish, export, or start an adventure package.', action: 'Open adventure creation' },
      worlds: { title: 'World building', description: 'Manage worlds, world knowledge, and the world context used when an adventure starts.', action: 'Open worlds' },
      lorebook: { title: 'Lorebooks', description: 'Edit lorebooks and entries, manage bindings, and import existing reference material.', action: 'Open lorebooks' },
      rules: { title: 'Rules editor', description: 'View and maintain available rules configurations while the rules runtime owns resolution.', action: 'Open rules' },
      modules: { title: 'Content sources', description: 'Install, import, and update content packages, then inspect their resources and source identity.', action: 'Manage content sources' },
      textReview: { title: 'Distribute text', description: 'Split ordinary text by headings and choose whether each fragment becomes a world, lorebook, character template, or adventure.', action: 'Open text tool' },
      package: { title: 'Export my content pack', description: 'Bundle adventures, worlds, lorebooks, and character resources as an installable .dfplugin for sharing or migration.', action: 'Open pack export' },
    },
  },
  ja: {
    kicker: '作成ツール', title: 'クリエイターワークショップ', intro: '既存のツールから、冒険、世界、ロアブック、ルール、コンテンツソースを作成します。',
    storyGroup: 'ストーリー作成', foundationGroup: '世界とルール', sourceGroup: 'コンテンツソース', toolGroup: 'テキストツール',
    cards: {
      adventures: { title: '冒険エディター', description: '冒険パッケージを新規作成、インポート、コピー、編集、レビュー、公開、開始できます。', action: '冒険作成を開く' },
      worlds: { title: '世界の作成', description: '世界と設定資料を管理し、冒険開始時の世界を選択します。', action: '世界を開く' },
      lorebook: { title: 'ロアブック', description: 'ロアブックと項目、バインド範囲を編集し、資料をインポートします。', action: 'ロアブックを開く' },
      rules: { title: 'ルールエディター', description: '利用可能なルール設定を管理します。判定はルールランタイムが担当します。', action: 'ルールを開く' },
      modules: { title: 'コンテンツソース', description: 'コンテンツパッケージをインストール、インポート、更新し、リソースとソース識別子を確認します。', action: 'ソースを管理' },
      textReview: { title: 'テキストを分配', description: '通常のテキストを見出しで分割し、世界、ロアブック、キャラクターテンプレート、冒険へ保存します。', action: 'テキストツールを開く' },
      package: { title: 'コンテンツパックを書き出す', description: '冒険、世界、ロアブック、キャラクター資源をインストール可能な .dfplugin にまとめます。', action: 'パック書き出しを開く' },
    },
  },
  de: {
    kicker: 'ERSTELLUNGSWERKZEUGE', title: 'Kreativwerkstatt', intro: 'Erstelle Abenteuer, Welten, Lorebücher, Regeln und Inhaltsquellen mit den vorhandenen Werkzeugen.',
    storyGroup: 'Geschichten erstellen', foundationGroup: 'Welten und Regeln', sourceGroup: 'Inhaltsquellen', toolGroup: 'Textwerkzeuge',
    cards: {
      adventures: { title: 'Mein Abenteuereditor', description: 'Abenteuerpakete erstellen, importieren, kopieren, bearbeiten, prüfen, veröffentlichen, exportieren oder starten.', action: 'Abenteuer öffnen' },
      worlds: { title: 'Welten erstellen', description: 'Welten und Weltwissen verwalten und den Weltkontext für den Abenteuerstart wählen.', action: 'Welten öffnen' },
      lorebook: { title: 'Lorebücher', description: 'Lorebücher und Einträge bearbeiten, Bindungen verwalten und Referenzmaterial importieren.', action: 'Lorebücher öffnen' },
      rules: { title: 'Regel-Editor', description: 'Verfügbare Regelkonfigurationen pflegen; die Regel-Engine übernimmt die Auflösung.', action: 'Regeln öffnen' },
      modules: { title: 'Inhaltsquellen', description: 'Inhaltspakete installieren, importieren und aktualisieren sowie Ressourcen und Quellenidentität prüfen.', action: 'Quellen verwalten' },
      textReview: { title: 'Text verteilen', description: 'Normalen Text nach Überschriften teilen und jeden Abschnitt als Welt, Lorebuch, Charaktervorlage oder Abenteuer speichern.', action: 'Textwerkzeug öffnen' },
      package: { title: 'Eigenes Inhaltspaket exportieren', description: 'Abenteuer, Welten, Lorebücher und Charakterressourcen als installierbares .dfplugin bündeln.', action: 'Paketexport öffnen' },
    },
  },
  ru: {
    kicker: 'ИНСТРУМЕНТЫ СОЗДАНИЯ', title: 'Мастерская автора', intro: 'Используйте существующие инструменты для приключений, миров, книг знаний, правил и источников контента.',
    storyGroup: 'Создание историй', foundationGroup: 'Миры и правила', sourceGroup: 'Источники контента', toolGroup: 'Текстовые инструменты',
    cards: {
      adventures: { title: 'Редактор моих приключений', description: 'Создавайте, импортируйте, копируйте, редактируйте, проверяйте, публикуйте, экспортируйте и запускайте пакеты.', action: 'Открыть создание приключения' },
      worlds: { title: 'Создание мира', description: 'Управляйте мирами и знаниями мира, выбираемыми при запуске приключения.', action: 'Открыть миры' },
      lorebook: { title: 'Книги знаний', description: 'Редактируйте книги и записи, управляйте привязками и импортируйте справочные материалы.', action: 'Открыть книги знаний' },
      rules: { title: 'Редактор правил', description: 'Просматривайте и поддерживайте конфигурации правил; расчёты выполняет движок правил.', action: 'Открыть правила' },
      modules: { title: 'Источники контента', description: 'Устанавливайте, импортируйте и обновляйте пакеты, просматривая ресурсы и идентичность источника.', action: 'Управлять источниками' },
      textReview: { title: 'Распределить текст', description: 'Разделяйте обычный текст по заголовкам и сохраняйте фрагменты как мир, книгу знаний, шаблон персонажа или приключение.', action: 'Открыть текстовый инструмент' },
      package: { title: 'Экспортировать свой пакет', description: 'Соберите приключения, миры, книги знаний и персонажей в устанавливаемый .dfplugin.', action: 'Открыть экспорт пакета' },
    },
  },
}

export function creatorCopy(locale: Locale): CreatorCopy {
  return values[locale] || values.en
}
