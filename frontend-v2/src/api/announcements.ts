import { api } from '@/api/client'

export interface AnnouncementPayload {
  content: string
  hash: string
  fetched: boolean
  stale?: boolean
}

const EMPTY: AnnouncementPayload = { content: '', hash: '', fetched: false }

export async function fetchAnnouncement(lang: string): Promise<AnnouncementPayload> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 10000)
  try {
    const payload = await api<unknown>(`/announcements?lang=${encodeURIComponent(lang)}`, {
      signal: controller.signal,
    })
    if (!isAnnouncementPayload(payload)) return { ...EMPTY }
    return payload
  } catch {
    return { ...EMPTY }
  } finally {
    window.clearTimeout(timer)
  }
}

function isAnnouncementPayload(value: unknown): value is AnnouncementPayload {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const record = value as Record<string, unknown>
  return typeof record.content === 'string'
    && typeof record.hash === 'string'
    && typeof record.fetched === 'boolean'
}
