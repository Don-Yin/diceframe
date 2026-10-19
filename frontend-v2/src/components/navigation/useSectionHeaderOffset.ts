import { computed, onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/** Anchor sticky children to the visible bottom edge of the application header. */
export function useSectionHeaderOffset(navigation: Ref<HTMLElement | null>) {
  const height = ref(68)
  const navigationHeight = ref(56)
  let header: HTMLElement | null = null
  let observer: ResizeObserver | undefined
  let frame: number | undefined
  const measure = () => {
    height.value = header ? Math.max(0, Math.min(window.innerHeight, header.getBoundingClientRect().bottom)) : 0
    if (navigation.value) navigationHeight.value = navigation.value.getBoundingClientRect().height
  }
  const scheduleMeasure = () => {
    if (frame !== undefined) return
    frame = window.requestAnimationFrame(() => {
      frame = undefined
      measure()
    })
  }
  onMounted(() => {
    header = document.querySelector<HTMLElement>('.app-header')
    measure()
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(measure)
      if (header) observer.observe(header)
      if (navigation.value) observer.observe(navigation.value)
    }
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', scheduleMeasure, { passive: true, capture: true })
  })
  onBeforeUnmount(() => {
    observer?.disconnect()
    window.removeEventListener('resize', measure)
    window.removeEventListener('scroll', scheduleMeasure, true)
    if (frame !== undefined) window.cancelAnimationFrame(frame)
  })
  return computed(() => ({ '--section-header-height': `${height.value}px`, '--section-navigation-height': `${navigationHeight.value}px` }))
}
