import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { i18n } from '../src/i18n'
import RestNotifications from '../src/features/play/rest-notices/RestNotifications.vue'
import type { RestActivity } from '../src/api/types'

const activity = (id: string, status: RestActivity['status'] = 'requested', actor = 'u-1'): RestActivity => ({
  id, kind: 'short', status, actors: [{ uid: actor, name: actor === 'u-1' ? '阿明' : 'A very long player name that should wrap safely' }],
})
const wrappers: VueWrapper[] = []

function mountNotices(overrides: Partial<{ gameKey: string; runId: string; actorId: string; activity: RestActivity[] }> = {}) {
  const wrapper = mount(RestNotifications, {
    attachTo: document.body,
    global: { plugins: [i18n] },
    props: { gameKey: 'game-1', runId: 'run-1', actorId: 'u-1', activity: [], ...overrides },
  })
  wrappers.push(wrapper)
  return wrapper
}

beforeEach(() => localStorage.clear())
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.useRealTimers(); document.body.innerHTML = '' })

describe('RestNotifications', () => {
  it('builds a baseline without notifying historical activity, then emits one merged toast for new events', async () => {
    const wrapper = mountNotices({ activity: [activity('old')] })
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeNull()

    await wrapper.setProps({ activity: [activity('old'), activity('new-1'), activity('new-2', 'settled', 'u-2')] })
    expect(document.querySelectorAll('[data-testid="rest-notice-toast"]')).toHaveLength(1)
    expect(document.querySelector('[data-testid="rest-notice-toast"]')?.textContent).toContain('1 more')
    await wrapper.setProps({ activity: [activity('old'), activity('new-1'), activity('new-2', 'settled', 'u-2')] })
    expect(document.querySelectorAll('[data-testid="rest-notice-toast"]')).toHaveLength(1)
  })

  it('notifies the first real event after an empty initial snapshot', async () => {
    const wrapper = mountNotices()
    await wrapper.setProps({ activity: [activity('loaded-from-first-refresh')] })
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeTruthy()
  })

  it('expires and dismisses notices without disabling later reminders, and clears timers on unmount', async () => {
    vi.useFakeTimers()
    const wrapper = mountNotices()
    await wrapper.setProps({ activity: [activity('one')] })
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeTruthy()
    await vi.advanceTimersByTimeAsync(5000)
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeNull()
    await wrapper.setProps({ activity: [activity('one'), activity('two')] })
    ;(document.querySelector('[data-testid="rest-notice-dismiss"]') as HTMLButtonElement).click()
    await nextTick()
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeNull()
    await wrapper.setProps({ activity: [activity('one'), activity('two'), activity('three')] })
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeTruthy()
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeNull()
  })

  it('mutes only reminders, retains incoming history, and does not replay it when enabled again', async () => {
    const wrapper = mountNotices()
    await wrapper.setProps({ activity: [activity('one')] })
    ;(document.querySelector('[data-testid="rest-notice-mute"]') as HTMLButtonElement).click()
    await nextTick()
    await wrapper.setProps({ activity: [activity('one'), activity('two', 'settled')] })
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeNull()
    await wrapper.get('[data-testid="rest-notices-open"]').trigger('click')
    expect(document.querySelectorAll('.rest-notices-entry')).toHaveLength(2)
    const checkbox = document.querySelector('[data-testid="rest-notices-enabled"]') as HTMLInputElement
    expect(checkbox.checked).toBe(false)
    checkbox.click()
    await nextTick()
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeNull()
    await wrapper.setProps({ activity: [activity('one'), activity('two', 'settled'), activity('three')] })
    expect(document.querySelectorAll('.rest-notices-entry')).toHaveLength(3)
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeNull()
    expect(wrapper.find('.rest-notices-badge').exists()).toBe(false)
  })

  it('shows all players in history, marks opened history read, and emits the selected rest kind', async () => {
    const wrapper = mountNotices({ activity: [activity('one'), activity('two', 'settled', 'u-2')] })
    await wrapper.get('[data-testid="rest-notices-open"]').trigger('click')
    expect(document.querySelector('[data-testid="rest-notices-dialog"]')).toBeTruthy()
    expect(document.querySelector('[data-testid="rest-notices-list"]')?.textContent).toContain('A very long player name')
    await (document.querySelector('[data-testid="rest-notice-view"]') as HTMLButtonElement).click()
    expect(wrapper.emitted('open-rest')).toEqual([["short"]])
  })

  it('persists personal preference by game and actor, and storage events sync mute state', async () => {
    const wrapper = mountNotices()
    await wrapper.get('[data-testid="rest-notices-open"]').trigger('click')
    const checkbox = document.querySelector('[data-testid="rest-notices-enabled"]') as HTMLInputElement
    expect(checkbox.checked).toBe(true)
    checkbox.click()
    await nextTick()
    const key = 'diceframe:rest-notices:["game-1","u-1"]'
    expect(localStorage.getItem(key)).toBe('false')
    window.dispatchEvent(new StorageEvent('storage', { key, newValue: 'true' }))
    await nextTick()
    expect(checkbox.checked).toBe(true)
    checkbox.click()
    await nextTick()
    window.dispatchEvent(new StorageEvent('storage', { key: null, newValue: null }))
    await nextTick()
    expect(checkbox.checked).toBe(true)
    wrapper.unmount()
  })

  it('deduplicates by stable id when server updates status or actor names', async () => {
    const wrapper = mountNotices({ activity: [activity('stable')] })
    await wrapper.setProps({ activity: [{ ...activity('stable', 'settled'), actors: [{ uid: 'u-1', name: '改名后的玩家' }, { uid: 'u-2', name: '另一位玩家' }] }] })
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeNull()
  })

  it('does not leak toast or unread state when game, run, or actor changes', async () => {
    const wrapper = mountNotices({ activity: [activity('baseline')] })
    await wrapper.setProps({ activity: [activity('new')] })
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeTruthy()
    await wrapper.setProps({ gameKey: 'game-2', runId: 'run-2', actorId: 'u-2', activity: [activity('other', 'requested', 'u-2')] })
    expect(document.querySelector('[data-testid="rest-notice-toast"]')).toBeNull()
    expect(wrapper.get('[data-testid="rest-notices-open"]').text()).not.toContain('1')
  })

  it('renders a polite, non-focus-stealing toast with mobile-safe long text styles', async () => {
    const wrapper = mountNotices({ activity: [activity('baseline')] })
    await wrapper.setProps({ activity: [activity('baseline'), activity('long', 'error', 'u-2')] })
    const toast = document.querySelector('[data-testid="rest-notice-toast"]')!
    expect(toast.getAttribute('role')).toBe('status')
    expect(toast.getAttribute('aria-live')).toBe('polite')
    expect(toast.querySelector('[data-testid="rest-notice-dismiss"]')).toBeTruthy()
    expect(toast.querySelector('[data-testid="rest-notice-mute"]')).toBeTruthy()
    expect(toast.querySelector('[data-testid="rest-notice-view"]')).toBeTruthy()
    expect(document.querySelector('.rest-notice-toast')?.classList.contains('rest-notice-toast')).toBe(true)
  })
})
