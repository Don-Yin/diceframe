import type { Locale } from '@/i18n'
const zh = { title: '提交审核', details: '内容与来源', references: '内容引用', unresolved: '未解析引用：解决后才能导入', conflicts: '已有同来源内容', create: '新建', update: '更新现有内容', duplicate: '保留两份', skip: '跳过重复内容', existing: '目标已存在' }
const copy: Record<Locale, typeof zh> = {
  'zh-CN': zh,
  en: { title: 'Commit review', details: 'Content and provenance', references: 'Content references', unresolved: 'Unresolved references: resolve before importing', conflicts: 'Existing content from this source', create: 'Create', update: 'Update existing content', duplicate: 'Keep both', skip: 'Skip duplicates', existing: 'Target already exists' },
  ja: { title: '保存内容の確認', details: '内容と出典', references: 'コンテンツ参照', unresolved: '未解決の参照：インポート前に解決してください', conflicts: '同じ出典の既存コンテンツ', create: '新規作成', update: '既存の内容を更新', duplicate: '両方保持', skip: '重複をスキップ', existing: '保存先に既存の内容があります' },
  de: { title: 'Import prüfen', details: 'Inhalt und Herkunft', references: 'Inhaltsverweise', unresolved: 'Unaufgelöste Verweise: vor dem Import beheben', conflicts: 'Vorhandener Inhalt aus dieser Quelle', create: 'Erstellen', update: 'Vorhandenen Inhalt aktualisieren', duplicate: 'Beide behalten', skip: 'Duplikate überspringen', existing: 'Ziel bereits vorhanden' },
  ru: { title: 'Проверка импорта', details: 'Содержимое и источник', references: 'Ссылки на содержимое', unresolved: 'Неразрешённые ссылки: исправьте перед импортом', conflicts: 'Существующее содержимое из этого источника', create: 'Создать', update: 'Обновить существующее', duplicate: 'Сохранить оба', skip: 'Пропустить дубликаты', existing: 'Цель уже существует' },
}
export const reviewCopy = (locale: Locale) => copy[locale]
