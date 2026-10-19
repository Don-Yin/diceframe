import { nextTick, watch, type Ref } from 'vue'

/** The game tool drawer owns focus until closed; nested dialogs own theirs. */
export function usePlayDrawerFocus(open: Ref<boolean>, drawer: Ref<HTMLElement | null>) {
  watch(open, async value => {
    if (!value) return
    await nextTick()
    drawer.value?.querySelector<HTMLElement>('.rail-toggle')?.focus()
  })
  function trapTab(event: KeyboardEvent) {
    if (!open.value || event.key !== 'Tab' || !drawer.value) return
    if (document.querySelector('[role="dialog"][aria-modal="true"]')) return
    const controls = Array.from(drawer.value.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]',
    )).filter(element => element.getClientRects().length && !element.closest('[inert]'))
    const first = controls[0], last = controls[controls.length - 1]
    if (!first) { event.preventDefault(); drawer.value.focus(); return }
    const outside = !drawer.value.contains(document.activeElement)
    if (event.shiftKey && (outside || document.activeElement === first)) {
      event.preventDefault(); last?.focus()
    } else if (!event.shiftKey && (outside || document.activeElement === last)) {
      event.preventDefault(); first.focus()
    }
  }
  return { trapTab }
}
