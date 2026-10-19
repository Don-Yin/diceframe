import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import Modal from '../src/components/ui/Modal.vue'

afterEach(() => { document.body.innerHTML = '' })

describe('shared modal access', () => {
  it('retains default backdrop behavior and allows a picker to opt into dismissal', async () => {
    const wrapper = mount(Modal, { attachTo: document.body, props: { title: 'Picker' }, global: { plugins: [i18n], stubs: { Teleport: true } } })
    await wrapper.get('.modal').trigger('click')
    expect(wrapper.emitted('close')).toBeUndefined()
    await wrapper.setProps({ closeOnBackdrop: true })
    await wrapper.get('.dialog').trigger('click')
    expect(wrapper.emitted('close')).toBeUndefined()
    await wrapper.get('.modal').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('announces its title as a dialog and restores focus to the opener', () => {
    const opener = document.createElement('button')
    document.body.append(opener)
    opener.focus()
    const wrapper = mount(Modal, { attachTo: document.body, props: { title: 'Create a Book' }, slots: { default: '<input autofocus aria-label="name" />' }, global: { plugins: [i18n] } })
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!
    expect(dialog).not.toBeNull()
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(document.getElementById(dialog.getAttribute('aria-labelledby')!)?.textContent).toBe('Create a Book')
    expect(document.activeElement?.tagName).toBe('INPUT')
    wrapper.unmount()
    expect(document.activeElement).toBe(opener)
  })

  it('closes only the top dialog on Escape and removes keyboard handling on unmount', () => {
    const options = { attachTo: document.body, global: { plugins: [i18n] } }
    const outer = mount(Modal, { ...options, props: { title: 'Checks' } })
    const inner = mount(Modal, { ...options, props: { title: 'Request' } })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(inner.emitted('close')).toHaveLength(1)
    expect(outer.emitted('close')).toBeUndefined()
    inner.unmount()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(outer.emitted('close')).toHaveLength(1)
    outer.unmount()
  })
})
