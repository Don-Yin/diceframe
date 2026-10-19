import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WorldMaterialsDialog from '../src/features/worlds/WorldMaterialsDialog.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api, errorMessage: (cause: unknown) => String((cause as Error)?.message || cause) }
})

function openDialog() {
  return mount(WorldMaterialsDialog, {
    props: { worldId: 'source-world', worldName: '来源世界' },
    global: { plugins: [i18n] },
  })
}

function createButton() {
  return new DOMWrapper(document.querySelector<HTMLButtonElement>('.dialog button.primary')!)
}

describe('WorldMaterialsDialog', () => {
  beforeEach(() => { mocks.api.mockReset(); i18n.global.locale.value = 'zh-CN' })
  afterEach(() => { document.body.innerHTML = '' })

  it('requires an explicit click and prevents duplicate writes while creating a copy', async () => {
    let finish!: (value: unknown) => void
    mocks.api.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = openDialog()
    await flushPromises()
    expect(mocks.api).not.toHaveBeenCalled()
    await createButton().trigger('click')
    await createButton().trigger('click')
    expect(mocks.api).toHaveBeenCalledTimes(1)
    expect(JSON.parse(mocks.api.mock.calls[0][1].body)).toEqual({ template_id: 'source-world' })
    finish({ ok: true, world_id: 'own-copy' })
    await flushPromises()
    expect(wrapper.emitted('created')).toEqual([['own-copy']])
    wrapper.unmount()
  })

  it('does not navigate when a creation result arrives after cancellation', async () => {
    let finish!: (value: unknown) => void
    mocks.api.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = openDialog()
    await createButton().trigger('click')
    document.querySelector<HTMLButtonElement>('.modal-x')!.click()
    finish({ ok: true, world_id: 'own-copy' })
    await flushPromises()
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.emitted('created')).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps the dialog open after a failed copy and permits retrying', async () => {
    mocks.api.mockRejectedValueOnce(new Error('copy failed')).mockResolvedValueOnce({ ok: true, world_id: 'own-copy' })
    const wrapper = openDialog()
    await createButton().trigger('click')
    await flushPromises()
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('copy failed')
    expect(createButton().attributes('disabled')).toBeUndefined()
    expect(wrapper.emitted('created')).toBeUndefined()
    await createButton().trigger('click')
    await flushPromises()
    expect(wrapper.emitted('created')).toEqual([['own-copy']])
    wrapper.unmount()
  })
})
