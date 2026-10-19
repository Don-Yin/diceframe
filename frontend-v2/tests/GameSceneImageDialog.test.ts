import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import GameSceneImageDialog from '../src/components/common/GameSceneImageDialog.vue'

const mocks = vi.hoisted(() => ({ api: vi.fn(), resolve: vi.fn(), encode: vi.fn(), revoke: vi.fn(), success: vi.fn() }))
vi.mock('../src/api/client', () => ({ api: mocks.api, errorMessage: (cause: unknown) => String((cause as Error).message || cause) }))
vi.mock('../src/api/sceneImages', () => ({
  resolveGameSceneImageUrl: mocks.resolve, fileToBase64: mocks.encode, revokeSceneImageUrl: mocks.revoke,
}))
vi.mock('../src/composables/useToast', () => ({ useToast: () => ({ success: mocks.success }) }))

async function render() {
  const wrapper = mount(GameSceneImageDialog, {
    props: { gameKey: 'web|chosen|gm', ruleId: 'freeform_fantasy', gameName: 'Selected save' },
    global: { plugins: [i18n], stubs: {
      Modal: { name: 'Modal', template: '<div><slot /></div>' },
      AdventureSceneImagePicker: { name: 'AdventureSceneImagePicker', props: ['modelValue', 'defaultUrl'], template: '<div />' },
    } },
  })
  await flushPromises()
  return wrapper
}

describe('save cover editing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.api.mockReset()
    mocks.resolve.mockReset().mockResolvedValue('blob:default')
    mocks.encode.mockReset().mockResolvedValue('encoded-image')
    i18n.global.locale.value = 'zh-CN'
  })

  it('restores the selected save default through the existing game endpoint', async () => {
    const reference = { kind: 'builtin', id: 'mountain_city' }
    mocks.api.mockResolvedValue({ ok: true, scene_image: reference })
    const wrapper = await render()
    expect(mocks.resolve).toHaveBeenCalledWith('web|chosen|gm', 'freeform_fantasy', true)
    await wrapper.get('[data-testid="save-cover-save"]').trigger('click')
    await flushPromises()
    expect(mocks.api).toHaveBeenCalledWith('/games/web%7Cchosen%7Cgm/scene-image', {
      method: 'POST', body: JSON.stringify({ use_default: true }),
    })
    expect(wrapper.emitted('saved')).toEqual([['web|chosen|gm', reference]])
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
    expect(mocks.revoke).toHaveBeenCalledWith('blob:default')
  })

  it('keeps the uploaded draft after a rejected save and retries the same target', async () => {
    mocks.api.mockResolvedValueOnce({ ok: false, error: 'cover rejected' })
      .mockResolvedValueOnce({ ok: true, scene_image: { kind: 'upload', asset_id: 'new-cover' } })
    const wrapper = await render()
    const picker = wrapper.findComponent({ name: 'AdventureSceneImagePicker' })
    const file = new File(['image'], 'cover.png', { type: 'image/png' })
    picker.vm.$emit('update:modelValue', file)
    await wrapper.get('[data-testid="save-cover-save"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('cover rejected')
    expect(picker.props('modelValue')).toBe(file)
    expect(wrapper.emitted('close')).toBeUndefined()
    await wrapper.get('[data-testid="save-cover-save"]').trigger('click')
    await flushPromises()
    expect(JSON.parse(mocks.api.mock.calls[1][1].body)).toEqual({ file_data: 'encoded-image', file_name: 'cover.png' })
    expect(wrapper.emitted('saved')).toHaveLength(1)
    wrapper.unmount()
  })

  it('prevents dismissing or changing the draft while a write is pending', async () => {
    let resolve!: (value: unknown) => void
    mocks.api.mockImplementation(() => new Promise(done => { resolve = done }))
    const wrapper = await render()
    await wrapper.get('[data-testid="save-cover-save"]').trigger('click')
    await wrapper.get('[data-testid="save-cover-save"]').trigger('click')
    wrapper.findComponent({ name: 'Modal' }).vm.$emit('close')
    expect(mocks.api).toHaveBeenCalledTimes(1)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('close')).toBeUndefined()
    resolve({ ok: true, scene_image: { kind: 'builtin', id: 'mountain_city' } })
    await flushPromises()
    wrapper.unmount()
  })

  it('releases a late default preview after the dialog is gone', async () => {
    let resolve!: (url: string) => void
    mocks.resolve.mockImplementation(() => new Promise(done => { resolve = done }))
    const wrapper = await render()
    wrapper.unmount()
    resolve('blob:late-default')
    await flushPromises()
    expect(mocks.revoke).toHaveBeenCalledWith('blob:late-default')
    expect(wrapper.emitted('saved')).toBeUndefined()
  })
})
