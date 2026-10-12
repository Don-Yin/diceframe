import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchAnnouncement: vi.fn(),
  locale: { value: 'zh-CN' },
}))

vi.mock('../src/api/announcements', () => ({
  fetchAnnouncement: mocks.fetchAnnouncement,
}))

vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({ locale: mocks.locale }),
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(next => { resolve = next })
  return { promise, resolve }
}

describe('useAnnouncements', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.fetchAnnouncement.mockReset()
    mocks.locale.value = 'zh-CN'
    localStorage.clear()
  })

  it('coalesces same-language loads and marks read reactively', async () => {
    const pending = deferred<{ content: string; hash: string; fetched: boolean }>()
    mocks.fetchAnnouncement.mockReturnValue(pending.promise)
    const { useAnnouncements } = await import('../src/composables/useAnnouncements')
    const announcements = useAnnouncements()

    const first = announcements.load('zh-CN')
    const second = announcements.load('zh-CN')
    expect(mocks.fetchAnnouncement).toHaveBeenCalledTimes(1)
    pending.resolve({ content: '公告', hash: 'new-hash', fetched: true })
    await Promise.all([first, second])

    expect(announcements.content.value).toBe('公告')
    expect(announcements.hasUnread.value).toBe(true)
    announcements.markRead()
    expect(announcements.hasUnread.value).toBe(false)
    expect(localStorage.getItem('diceframe_announcement_read_hash:zh')).toBe('new-hash')
  })

  it('keeps a slow old-language response from overwriting the new language', async () => {
    const chinese = deferred<{ content: string; hash: string; fetched: boolean }>()
    const english = deferred<{ content: string; hash: string; fetched: boolean }>()
    mocks.fetchAnnouncement.mockImplementation((language: string) => (
      language === 'en' ? english.promise : chinese.promise
    ))
    const { useAnnouncements } = await import('../src/composables/useAnnouncements')
    const announcements = useAnnouncements()

    const first = announcements.load('zh-CN')
    const second = announcements.load('en')
    english.resolve({ content: 'English notice', hash: 'en-hash', fetched: true })
    await second
    chinese.resolve({ content: '中文公告', hash: 'zh-hash', fetched: true })
    await first

    expect(announcements.content.value).toBe('English notice')
    announcements.markRead()
    expect(localStorage.getItem('diceframe_announcement_read_hash:en')).toBe('en-hash')
    expect(localStorage.getItem('diceframe_announcement_read_hash:zh')).toBeNull()
  })
})
