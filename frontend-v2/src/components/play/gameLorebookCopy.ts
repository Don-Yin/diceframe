import type { Locale } from "@/composables/useLocale";
type Copy = Record<
  | "title"
  | "loading"
  | "retry"
  | "save"
  | "cancel"
  | "confirm"
  | "preview"
  | "only"
  | "max"
  | "failed"
  | "done"
  | "locked"
  | "disabled"
  | "entries"
  | "emptySelection",
  string
>;
const copies: Record<Locale, Copy> = {
  "zh-CN": {
    title: "本局资料册",
    loading: "正在读取本局资料册…",
    retry: "重试",
    save: "保存选择",
    cancel: "取消",
    confirm: "确认应用",
    preview: "确认本局资料册",
    only: "只影响本局",
    max: "最多选择 16 本资料册",
    failed: "加载失败",
    done: "本局资料册已更新",
    locked: "角色资料，已锁定",
    disabled: "已停用",
    entries: "条",
    emptySelection: "本局不使用可编辑资料册，角色资料仍保留",
  },
  en: {
    title: "Game lorebooks",
    loading: "Loading game lorebooks…",
    retry: "Retry",
    save: "Save selection",
    cancel: "Cancel",
    confirm: "Confirm",
    preview: "Confirm game lorebooks",
    only: "Only this game",
    max: "Up to 16 editable lorebooks",
    failed: "Load failed",
    done: "Game lorebooks updated",
    locked: "Locked character source",
    disabled: "Disabled",
    entries: "entries",
    emptySelection:
      "This game uses no editable lorebooks; character sources remain",
  },
  ja: {
    title: "本セッションの資料集",
    loading: "資料集を読み込んでいます…",
    retry: "再試行",
    save: "選択を保存",
    cancel: "キャンセル",
    confirm: "適用",
    preview: "資料集を確認",
    only: "このゲームのみ",
    max: "編集可能な資料集は最大16冊",
    failed: "読み込み失敗",
    done: "資料集を更新しました",
    locked: "キャラクター資料（固定）",
    disabled: "無効",
    entries: "件",
    emptySelection:
      "このゲームでは編集可能な資料集を使いません。キャラクター資料は保持されます",
  },
  ru: {
    title: "Книги этой игры",
    loading: "Загрузка книг…",
    retry: "Повторить",
    save: "Сохранить выбор",
    cancel: "Отмена",
    confirm: "Применить",
    preview: "Подтвердите книги",
    only: "Только эта игра",
    max: "До 16 доступных книг",
    failed: "Ошибка загрузки",
    done: "Книги обновлены",
    locked: "Книга персонажа заблокирована",
    disabled: "Отключено",
    entries: "записей",
    emptySelection:
      "В этой игре нет доступных книг; книги персонажей сохраняются",
  },
  de: {
    title: "Lorebooks dieses Spiels",
    loading: "Lorebooks werden geladen…",
    retry: "Erneut versuchen",
    save: "Auswahl speichern",
    cancel: "Abbrechen",
    confirm: "Anwenden",
    preview: "Lorebooks bestätigen",
    only: "Nur dieses Spiel",
    max: "Bis zu 16 bearbeitbare Lorebooks",
    failed: "Laden fehlgeschlagen",
    done: "Lorebooks aktualisiert",
    locked: "Gesperrte Charakterquelle",
    disabled: "Deaktiviert",
    entries: "Einträge",
    emptySelection:
      "Dieses Spiel nutzt keine bearbeitbaren Lorebooks; Charakterquellen bleiben erhalten",
  },
};
export function gameLorebookCopy(locale: Locale): Copy {
  return copies[locale] || copies.en;
}
