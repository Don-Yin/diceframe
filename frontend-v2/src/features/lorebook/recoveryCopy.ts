import type { Locale } from "@/composables/useLocale";
type Copy = Record<
  | "title"
  | "loading"
  | "loadFailed"
  | "retry"
  | "empty"
  | "undo"
  | "restore"
  | "pending"
  | "preview"
  | "affected"
  | "count"
  | "confirm"
  | "cancel"
  | "failed"
  | "done"
  | "noPermission"
  | "statusPrepared"
  | "statusUndone"
  | "statusApplied"
  | "statusRestored"
  | "statusUnknown"
  | "preparedHint",
  string
>;
const copies: Record<Locale, Copy> = {
  "zh-CN": {
    title: "内容撤销 / 回收站",
    loading: "正在读取操作记录…",
    loadFailed: "无法读取操作记录",
    retry: "重试",
    empty: "暂无可回收的内容操作。",
    undo: "撤销此操作",
    restore: "恢复内容",
    pending: "正在准备恢复方案…",
    preview: "请确认这次内容恢复",
    affected: "影响对象",
    count: "条目数",
    confirm: "确认执行",
    cancel: "取消并返回",
    failed: "操作失败",
    done: "内容操作已完成",
    noPermission: "只有主持人可以执行内容恢复。",
    statusPrepared: "结果待核实",
    statusUndone: "已撤销",
    statusApplied: "已执行",
    statusRestored: "已恢复",
    statusUnknown: "状态未知",
    preparedHint: "该操作已准备但结果待核实，暂不能重复执行。",
  },
  en: {
    title: "Content recovery",
    loading: "Loading operation history…",
    loadFailed: "Could not load operation history",
    retry: "Retry",
    empty: "No recoverable content operations.",
    undo: "Undo operation",
    restore: "Restore content",
    pending: "Preparing recovery plan…",
    preview: "Confirm this content recovery",
    affected: "Affected target",
    count: "Entries",
    confirm: "Confirm",
    cancel: "Cancel",
    failed: "Operation failed",
    done: "Content operation completed",
    noPermission: "Only the GM can recover content.",
    statusPrepared: "Result pending verification",
    statusUndone: "Undone",
    statusApplied: "Applied",
    statusRestored: "Restored",
    statusUnknown: "Status unknown",
    preparedHint:
      "This operation is prepared but its result is unverified; it cannot be run again yet.",
  },
  ja: {
    title: "コンテンツの取り消し / ごみ箱",
    loading: "操作履歴を読み込んでいます…",
    loadFailed: "操作履歴を読み込めません",
    retry: "再試行",
    empty: "復元できる操作はありません。",
    undo: "操作を取り消す",
    restore: "コンテンツを復元",
    pending: "復元案を準備しています…",
    preview: "この復元を確認",
    affected: "対象",
    count: "件",
    confirm: "実行",
    cancel: "キャンセル",
    failed: "操作に失敗しました",
    done: "操作が完了しました",
    noPermission: "GM のみ実行できます。",
    statusPrepared: "結果確認待ち",
    statusUndone: "取り消し済み",
    statusApplied: "実行済み",
    statusRestored: "復元済み",
    statusUnknown: "不明な状態",
    preparedHint: "結果が未確認のため、再実行できません。",
  },
  ru: {
    title: "Отмена / восстановление контента",
    loading: "Загрузка истории…",
    loadFailed: "Не удалось загрузить историю",
    retry: "Повторить",
    empty: "Нет доступных операций восстановления.",
    undo: "Отменить операцию",
    restore: "Восстановить",
    pending: "Подготовка плана…",
    preview: "Подтвердите восстановление",
    affected: "Объект",
    count: "записей",
    confirm: "Подтвердить",
    cancel: "Отмена",
    failed: "Операция не выполнена",
    done: "Операция завершена",
    noPermission: "Доступно только GM.",
    statusPrepared: "Ожидает проверки",
    statusUndone: "Отменено",
    statusApplied: "Выполнено",
    statusRestored: "Восстановлено",
    statusUnknown: "Неизвестный статус",
    preparedHint: "Результат не подтверждён, повторный запуск пока запрещён.",
  },
  de: {
    title: "Inhalte zurücknehmen / Papierkorb",
    loading: "Vorgangsverlauf wird geladen…",
    loadFailed: "Vorgangsverlauf konnte nicht geladen werden",
    retry: "Erneut versuchen",
    empty: "Keine wiederherstellbaren Vorgänge.",
    undo: "Vorgang zurücknehmen",
    restore: "Inhalt wiederherstellen",
    pending: "Wiederherstellungsplan wird erstellt…",
    preview: "Wiederherstellung bestätigen",
    affected: "Ziel",
    count: "Einträge",
    confirm: "Bestätigen",
    cancel: "Abbrechen",
    failed: "Vorgang fehlgeschlagen",
    done: "Vorgang abgeschlossen",
    noPermission: "Nur der GM kann Inhalte wiederherstellen.",
    statusPrepared: "Prüfung ausstehend",
    statusUndone: "Zurückgenommen",
    statusApplied: "Ausgeführt",
    statusRestored: "Wiederhergestellt",
    statusUnknown: "Unbekannter Status",
    preparedHint:
      "Das Ergebnis ist nicht bestätigt; der Vorgang kann noch nicht erneut ausgeführt werden.",
  },
};
export function recoveryCopy(locale: Locale): Copy {
  return copies[locale] || copies.en;
}
