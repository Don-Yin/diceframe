import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import UpdateReadinessBanner from '@/features/admin/UpdateReadinessBanner.vue'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('@/api/client', () => ({ api }))
vi.mock('@/composables/useLocale', () => ({ useLocale: () => ({ t: () => 'Update validation is in progress' }) }))

afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

describe('update readiness', () => {
  it('shows pending validation and clears it only when the backend is ready', async () => {
    vi.useFakeTimers()
    api.mockResolvedValueOnce({ ok: true, update_pending: true }).mockResolvedValue({ ok: true, update_pending: false })
    const wrapper = mount(UpdateReadinessBanner)
    await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not poll an older backend that has no pending-update field', async () => {
    vi.useFakeTimers()
    api.mockResolvedValue({ ok: true })
    const wrapper = mount(UpdateReadinessBanner)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(5000)
    expect(api).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
