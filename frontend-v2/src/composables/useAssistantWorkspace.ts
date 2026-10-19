import { computed, onBeforeUnmount, ref } from 'vue'

const STORAGE_KEY = 'diceframe_assistant_workspace_collapsed'

function readPreference(): boolean | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === '1' ? true : value === '0' ? false : null
  } catch { return null }
}

export function useAssistantWorkspace() {
  const media = window.matchMedia?.('(max-width: 800px)')
  const narrow = ref(media?.matches ?? window.innerWidth <= 800)
  const preference = ref(readPreference())
  const collapsed = computed(() => preference.value ?? narrow.value)
  const resized = () => { narrow.value = media?.matches ?? window.innerWidth <= 800 }
  media?.addEventListener('change', resized)
  onBeforeUnmount(() => media?.removeEventListener('change', resized))

  function toggle() {
    preference.value = !collapsed.value
    try { localStorage.setItem(STORAGE_KEY, preference.value ? '1' : '0') } catch { /* Optional preference storage. */ }
  }

  return { collapsed, toggle }
}
