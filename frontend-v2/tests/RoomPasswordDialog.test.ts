import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RoomPasswordDialog from '../src/features/play/RoomPasswordDialog.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({ api: vi.fn(), toastSuccess: vi.fn() }))
vi.mock('../src/api/client', async original => ({ ...await original<typeof import('../src/api/client')>(), api: mocks.api }))
vi.mock('../src/composables/useToast', () => ({ useToast: () => ({ success: mocks.toastSuccess, error: vi.fn(), info: vi.fn(), warning: vi.fn() }) }))

const open = (hasPassword = false) => mount(RoomPasswordDialog, {
  props: { gameKey: 'room/key', hasPassword },
  global: { plugins: [i18n], stubs: { Modal: { template: '<div><button data-testid="modal-close" @click="$emit(\'close\')" /><slot /></div>' } } },
})

enableAutoUnmount(afterEach)

beforeEach(() => {
  i18n.global.locale.value = 'en'
  mocks.api.mockReset()
  mocks.api.mockResolvedValue({ ok: true })
  mocks.toastSuccess.mockReset()
})

describe('RoomPasswordDialog', () => {
  it('shows configured status without exposing the old password and does not request on open or cancel', async () => {
    const wrapper = open(true)
    expect(wrapper.text()).toContain('configured')
    expect(wrapper.text()).not.toContain('secret')
    expect(mocks.api).not.toHaveBeenCalled()
    await wrapper.get('[data-testid=room-password-cancel]').trigger('click')
    expect(mocks.api).not.toHaveBeenCalled()
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('keeps save disabled for an empty password and does not show remove when unconfigured', async () => {
    const wrapper = open()
    expect(wrapper.get('[data-testid=room-password-save]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid=room-password-remove]').exists()).toBe(false)
    await wrapper.get('[data-testid=room-password-save]').trigger('click')
    expect(mocks.api).not.toHaveBeenCalled()
  })

  it('validates blank and short passwords before sending', async () => {
    const wrapper = open()
    const input = wrapper.get('[data-testid=room-password-input]')
    await input.setValue('   ')
    await wrapper.get('[data-testid=room-password-save]').trigger('click')
    expect(wrapper.text()).toContain('cannot be only spaces')
    expect(mocks.api).not.toHaveBeenCalled()
    await input.setValue('short')
    await wrapper.get('[data-testid=room-password-save]').trigger('click')
    expect(wrapper.text()).toContain('at least 6')
    expect(mocks.api).not.toHaveBeenCalled()
  })

  it('sends an encoded game key and exact replacement payload, then emits changed and closes', async () => {
    const wrapper = open()
    await wrapper.get('[data-testid=room-password-input]').setValue('new pass')
    await wrapper.get('[data-testid=room-password-save]').trigger('click')
    await flushPromises()
    expect(mocks.api).toHaveBeenCalledWith('/games/room%2Fkey/room-password', {
      method: 'POST',
      body: JSON.stringify({ password: 'new pass' }),
    })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Room password updated')
  })

  it('removes a configured password only through the explicit remove action', async () => {
    const wrapper = open(true)
    await wrapper.get('[data-testid=room-password-remove]').trigger('click')
    await flushPromises()
    expect(mocks.api).toHaveBeenCalledWith('/games/room%2Fkey/room-password', {
      method: 'POST',
      body: JSON.stringify({ password: '' }),
    })
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Room password removed')
  })

  it('keeps application-level API failures visible and open', async () => {
    mocks.api.mockResolvedValueOnce({ ok: false })
    const wrapper = open()
    await wrapper.get('[data-testid=room-password-input]').setValue('new pass')
    await wrapper.get('[data-testid=room-password-save]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Setting failed')
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('guards duplicate submits while busy', async () => {
    let resolveRequest: (value: unknown) => void = () => undefined
    mocks.api.mockReturnValueOnce(new Promise(resolve => { resolveRequest = resolve }))
    const wrapper = open()
    await wrapper.get('[data-testid=room-password-input]').setValue('new pass')
    const save = wrapper.get('[data-testid=room-password-save]')
    await save.trigger('click')
    await save.trigger('click')
    await wrapper.get('[data-testid=modal-close]').trigger('click')
    expect(wrapper.emitted('close')).toBeUndefined()
    expect(mocks.api).toHaveBeenCalledTimes(1)
    resolveRequest({ ok: true })
    await flushPromises()
  })

  it('keeps API errors visible and remains open', async () => {
    mocks.api.mockRejectedValueOnce(new Error('server rejected password'))
    const wrapper = open()
    await wrapper.get('[data-testid=room-password-input]').setValue('new pass')
    await wrapper.get('[data-testid=room-password-save]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('server rejected password')
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.emitted('close')).toBeUndefined()
  })
})
