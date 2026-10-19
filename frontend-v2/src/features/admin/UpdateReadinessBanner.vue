<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/api/client'
import { useLocale } from '@/composables/useLocale'

const { t } = useLocale()
const pending = ref(false)
let active = true
let timer: ReturnType<typeof setTimeout> | undefined

async function check() {
  try {
    const result = await api<{ update_pending?: boolean }>('/system/update/health')
    if (!active) return
    pending.value = Boolean(result?.update_pending)
  } catch {
    if (!active) return
  }
  if (pending.value) timer = setTimeout(() => { void check() }, 2000)
}

onMounted(() => { void check() })
onBeforeUnmount(() => { active = false; clearTimeout(timer) })
</script>

<template>
  <div v-if="pending" class="update-readiness-banner" role="status" aria-live="polite">
    {{ t('updateDataValidating') }}
  </div>
</template>

<style scoped>
.update-readiness-banner{position:fixed;bottom:calc(5rem + env(safe-area-inset-bottom));left:50%;transform:translateX(-50%);z-index:60;width:max-content;max-width:calc(100vw - 2rem);padding:12px 18px;border:1px solid var(--df-border);border-radius:8px;background:var(--df-surface-2);color:var(--df-text);box-shadow:var(--df-shadow);font-size:14px;pointer-events:none}
</style>
