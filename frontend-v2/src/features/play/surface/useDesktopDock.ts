import { onScopeDispose, ref } from 'vue'

export function useDesktopDock() {
  const media = typeof window.matchMedia === 'function' ? window.matchMedia('(min-width: 801px)') : null
  const docked = ref(media?.matches ?? true)
  const update = () => { docked.value = media?.matches ?? true }
  media?.addEventListener?.('change', update)
  onScopeDispose(() => media?.removeEventListener?.('change', update))
  return docked
}
