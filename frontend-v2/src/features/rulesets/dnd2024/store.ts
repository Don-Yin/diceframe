import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { JsonObject } from '@/api/types'

const STORAGE_PREFIX = 'diceframe_ruleset_builder_'

export const useDnd2024BuilderStore = defineStore('dnd2024-builder', () => {
  const draft = ref<JsonObject>({})
  const storageKey = ref('')
  let stop: (() => void) | undefined

  function open(ruleId: string, language: string, initial?: JsonObject): void {
    storageKey.value = `${STORAGE_PREFIX}${ruleId}_${language || 'default'}`
    let restored: JsonObject = {}
    try {
      const raw = localStorage.getItem(storageKey.value)
      const parsed = raw ? JSON.parse(raw) : null
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) restored = parsed
    } catch { /* ignore a damaged local draft */ }
    draft.value = initial && Object.keys(initial).length ? initial : restored
    stop?.()
    stop = watch(draft, (value) => {
      try { localStorage.setItem(storageKey.value, JSON.stringify(value)) } catch { /* quota */ }
    }, { deep: true })
  }

  function clear(): void {
    if (storageKey.value) localStorage.removeItem(storageKey.value)
    stop?.()
    stop = undefined
    storageKey.value = ''
  }

  return { draft, open, clear }
})
