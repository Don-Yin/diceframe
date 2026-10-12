import { computed, ref } from 'vue'
import { fetchAnnouncement, type AnnouncementPayload } from '@/api/announcements'
import { useLocale } from '@/composables/useLocale'

type AnnouncementLanguage = 'zh' | 'en'

const LEGACY_READ_HASH_KEY = 'diceframe_announcement_read_hash'
const content = ref('')
const hash = ref('')
const stale = ref(false)
const loaded = ref(false)
const currentLanguage = ref<AnnouncementLanguage>('zh')
const readHash = ref(readStoredHash('zh'))
const inflight = new Map<AnnouncementLanguage, Promise<AnnouncementPayload>>()
let requestVersion = 0

const hasUnread = computed(() => Boolean(hash.value) && hash.value !== readHash.value)
const hasContent = computed(() => Boolean(content.value))

function normalizeLanguage(locale: string): AnnouncementLanguage {
  const lang = (locale || '').toLowerCase()
  // 官方公告只有 zh/en；ja/de 及其他非中文界面都回退英文公告，而非中文。
  return lang.startsWith('zh') ? 'zh' : 'en'
}

function storageKey(language: AnnouncementLanguage): string {
  return `diceframe_announcement_read_hash:${language}`
}

function readStoredHash(language: AnnouncementLanguage): string {
  try {
    return localStorage.getItem(storageKey(language))
      || (language === 'zh' ? localStorage.getItem(LEGACY_READ_HASH_KEY) : '')
      || ''
  } catch {
    return ''
  }
}

function request(language: AnnouncementLanguage): Promise<AnnouncementPayload> {
  const existing = inflight.get(language)
  if (existing) return existing
  const pending = fetchAnnouncement(language === 'en' ? 'en' : 'zh-CN')
    .finally(() => inflight.delete(language))
  inflight.set(language, pending)
  return pending
}

async function loadAnnouncement(locale: string) {
  const language = normalizeLanguage(locale)
  const version = ++requestVersion
  if (currentLanguage.value !== language) {
    currentLanguage.value = language
    readHash.value = readStoredHash(language)
    content.value = ''
    hash.value = ''
    stale.value = false
    loaded.value = false
  }
  const payload = await request(language)
  if (version !== requestVersion || currentLanguage.value !== language) return
  content.value = payload.content
  hash.value = payload.hash
  stale.value = Boolean(payload.stale)
  loaded.value = true
}

function markRead() {
  if (!hash.value) return
  readHash.value = hash.value
  try {
    localStorage.setItem(storageKey(currentLanguage.value), hash.value)
  } catch {
    // Read state is optional; announcement display remains usable.
  }
}

export function useAnnouncements() {
  const { locale } = useLocale()
  return {
    content,
    hash,
    stale,
    hasUnread,
    hasContent,
    loaded,
    load: (nextLocale = locale.value) => loadAnnouncement(nextLocale),
    markRead,
  }
}
