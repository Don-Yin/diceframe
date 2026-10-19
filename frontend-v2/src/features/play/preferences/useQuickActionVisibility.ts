import { computed, onMounted, onUnmounted, ref, watch, type Ref } from 'vue'

const PREFIX = 'diceframe:quick-action-visibility:v1:'

/** A personal display choice on this device; never changes table state or generation. */
export function useQuickActionVisibility(gameKey: Ref<string>, actorId: Ref<string>, tableDefault: Ref<boolean>) {
  const key = computed(() => PREFIX + encodeURIComponent(JSON.stringify([gameKey.value, actorId.value])))
  function read(): boolean | null {
    try {
      const stored = localStorage.getItem(key.value)
      return stored === 'true' ? true : stored === 'false' ? false : null
    } catch { return null }
  }
  const personal = ref(read())
  const visible = computed(() => personal.value ?? tableDefault.value)
  watch(key, () => { personal.value = read() }, { flush: 'sync' })
  function toggle() {
    personal.value = !visible.value
    try { localStorage.setItem(key.value, String(personal.value)) }
    catch { /* Display controls still work when browser storage is unavailable. */ }
  }
  function sync(event: StorageEvent) {
    if (event.key === key.value || event.key === null) personal.value = read()
  }
  onMounted(() => window.addEventListener('storage', sync))
  onUnmounted(() => window.removeEventListener('storage', sync))
  return { visible, toggle }
}
