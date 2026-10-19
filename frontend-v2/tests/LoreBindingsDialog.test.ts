import { mount } from '@vue/test-utils'
import { afterEach, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import LoreBindingsDialog from '../src/features/lorebook/LoreBindingsDialog.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

it('renders usage scope management through the themed Modal and closes on Escape', async () => {
  const wrapper = mount(LoreBindingsDialog, {
    attachTo: document.body,
    props: {
      open: true,
      bookName: '港口资料册',
      worldId: 'world-1',
      worldName: '测试世界',
      gameKey: 'game-1',
      bindings: [{ id: 'binding-1', book_id: 'book-1', scope_kind: 'world', scope_id: 'world-1', role: 'primary' }],
    },
    global: { plugins: [i18n] },
  })
  await wrapper.vm.$nextTick()

  const dialog = document.body.querySelector('.lore-bindings-dialog')
  expect(dialog?.closest('.modal')).toBeTruthy()
  expect(dialog?.getAttribute('role')).toBe('dialog')
  expect(dialog?.getAttribute('aria-labelledby')).toBeTruthy()
  expect(dialog?.querySelector('h2')?.textContent).toContain('港口资料册')
  expect(document.activeElement).toBe(dialog?.querySelector('input[value="world"]'))

  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await wrapper.vm.$nextTick()
  expect(wrapper.emitted('close')).toHaveLength(1)
  wrapper.unmount()
})
