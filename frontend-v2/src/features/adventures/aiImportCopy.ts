import type { Locale } from '@/i18n'

const en = {
  title: 'Organize with AI', intro: 'This sends the imported text to your configured model and consumes model tokens. Usage depends on input and output length; cancelling may still incur charges for tokens already used.',
  consent: 'I understand that this sends source text and uses tokens', start: 'Start AI organization', cancel: 'Cancel', apply: 'Use this draft', discard: 'Discard result',
  instructions: 'Organization instructions (optional)', placeholder: 'For example: group scenes by chapter and preserve clues and GM secrets.',
  ready: 'AI draft ready. Review it before replacing the current draft.', cancelled: 'Cancelled. The original draft was not replaced.', stale: 'The source changed. Generate again to keep your edits.',
  failed: 'AI organization failed. The original draft was kept.', source: 'Original text is preserved as GM reference. Rules and combat numbers still require review.',
  preparing: 'Checking source text…', organizing: 'Organizing section {current} / {total}…', linking: 'Connecting the adventure flow…', validating: 'Validating the generated draft…', complete: 'Organization complete',
  progress: 'Completed work steps', scenes: 'Scenes', resources: 'Resources', result: 'Result preview',
}
const values: Record<Locale, typeof en> = {
  en,
  'zh-CN': {
    title: 'AI 整理草稿', intro: '会将导入资料发送给已配置的模型服务，消耗模型 token。用量取决于文字和结果长度；取消前已产生的用量仍可能计费。',
    consent: '我了解会发送资料并消耗 token', start: '开始 AI 整理', cancel: '取消整理', apply: '采用 AI 草稿', discard: '丢弃结果',
    instructions: '整理要求（可选）', placeholder: '例如：按章节整理场景，保留线索与 GM 秘密。',
    ready: 'AI 草稿已生成。检查结果后，再替换当前草稿。', cancelled: '已取消，原草稿未被替换。', stale: '原草稿已改变，请重新整理以保留你的修改。',
    failed: 'AI 整理失败，原草稿已保留。', source: '原文保留为 GM 参考资料；规则和战斗数值仍需审核。',
    preparing: '正在检查原文…', organizing: '正在整理第 {current} / {total} 段…', linking: '正在连接剧情流程…', validating: '正在校验生成的草稿…', complete: '整理完成',
    progress: '已完成的整理步骤', scenes: '剧情场景', resources: '资源', result: '结果预览',
  },
  ja: {
    title: 'AI で下書きを整理', intro: '読み込んだ資料を設定済みモデルへ送信し、トークンを消費します。使用量は入出力の長さによります。キャンセル前の使用量には料金が発生する場合があります。',
    consent: '資料の送信とトークン消費を理解しました', start: 'AI 整理を開始', cancel: '整理をキャンセル', apply: 'この下書きを採用', discard: '結果を破棄',
    instructions: '整理の要望（任意）', placeholder: '例：章ごとにシーンを整理し、手がかりと GM の秘密を保持する。',
    ready: 'AI 下書きができました。内容を確認してから現在の下書きを置き換えてください。', cancelled: 'キャンセルしました。元の下書きは保持されています。', stale: '元の下書きが変更されました。再度整理してください。',
    failed: 'AI 整理に失敗しました。元の下書きは保持されています。', source: '原文は GM 参考資料として保持されます。ルールと戦闘の数値は確認が必要です。',
    preparing: '原文を確認中…', organizing: '資料 {current} / {total} を整理中…', linking: '冒険の流れを接続中…', validating: '生成された下書きを検証中…', complete: '整理完了',
    progress: '完了した整理ステップ', scenes: 'シーン', resources: 'リソース', result: '結果プレビュー',
  },
  de: {
    title: 'Entwurf mit KI ordnen', intro: 'Die importierten Texte werden an dein konfiguriertes Modell gesendet und verbrauchen Tokens. Der Verbrauch hängt von Ein- und Ausgabe ab. Bereits verbrauchte Tokens können auch nach Abbruch berechnet werden.',
    consent: 'Ich verstehe den Textversand und Tokenverbrauch', start: 'KI-Organisation starten', cancel: 'Abbrechen', apply: 'Diesen Entwurf verwenden', discard: 'Ergebnis verwerfen',
    instructions: 'Hinweise zur Organisation (optional)', placeholder: 'Zum Beispiel: Szenen nach Kapiteln ordnen und Hinweise sowie GM-Geheimnisse erhalten.',
    ready: 'KI-Entwurf fertig. Prüfe ihn, bevor du den aktuellen Entwurf ersetzt.', cancelled: 'Abgebrochen. Der ursprüngliche Entwurf bleibt erhalten.', stale: 'Die Quelle wurde geändert. Erstelle den Entwurf erneut.',
    failed: 'KI-Organisation fehlgeschlagen. Der ursprüngliche Entwurf bleibt erhalten.', source: 'Der Originaltext bleibt als GM-Referenz erhalten. Regeln und Kampfwerte müssen geprüft werden.',
    preparing: 'Quelltext wird geprüft…', organizing: 'Abschnitt {current} / {total} wird geordnet…', linking: 'Abenteuerablauf wird verbunden…', validating: 'Entwurf wird geprüft…', complete: 'Organisation abgeschlossen',
    progress: 'Abgeschlossene Arbeitsschritte', scenes: 'Szenen', resources: 'Ressourcen', result: 'Ergebnisvorschau',
  },
  ru: {
    title: 'Упорядочить черновик с ИИ', intro: 'Импортированный текст отправляется настроенной модели и расходует токены. Расход зависит от длины ввода и вывода. Токены, использованные до отмены, могут быть оплачены.',
    consent: 'Я понимаю, что текст будет отправлен и будут потрачены токены', start: 'Начать обработку ИИ', cancel: 'Отменить обработку', apply: 'Использовать черновик', discard: 'Отбросить результат',
    instructions: 'Пожелания к обработке (необязательно)', placeholder: 'Например: распределить сцены по главам, сохранить улики и секреты ведущего.',
    ready: 'Черновик ИИ готов. Проверьте его перед заменой текущего.', cancelled: 'Отменено. Исходный черновик не заменён.', stale: 'Исходный черновик изменён. Повторите обработку.',
    failed: 'Обработка ИИ не удалась. Исходный черновик сохранён.', source: 'Исходный текст сохранён как справка ведущего. Правила и боевые значения требуют проверки.',
    preparing: 'Проверка исходного текста…', organizing: 'Обработка части {current} / {total}…', linking: 'Связывание сюжета…', validating: 'Проверка черновика…', complete: 'Обработка завершена',
    progress: 'Завершённые этапы', scenes: 'Сцены', resources: 'Ресурсы', result: 'Предпросмотр результата',
  },
}
export const aiImportCopy = (locale: Locale) => values[locale]
