<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import { useLocale } from '@/composables/useLocale'
import { gamePreferencesCopy } from '@/features/game-preferences/copy'
import type { GamePreferenceResponse } from '@/features/game-preferences/model'

const props = defineProps<{ gameKey: string }>()
const emit = defineEmits<{ changed: [] }>()
const { locale } = useLocale()
const c = computed(() => gamePreferencesCopy(locale.value))
const canManage = ref(false), busy = ref(false), message = ref(''), error = ref('')
const endpoint = () => `/games/${encodeURIComponent(props.gameKey)}/preferences`
watch(() => props.gameKey, async () => {
  canManage.value = false
  try { canManage.value = (await api<GamePreferenceResponse>(endpoint())).can_save_defaults === true }
  catch { /* The preference panels own the visible load error. */ }
}, { immediate: true })
async function perform(kind: 'save' | 'apply') {
  if (busy.value) return
  busy.value = true; message.value = ''; error.value = ''
  try {
    if (kind === 'save') {
      const current = await api<GamePreferenceResponse>(endpoint())
      if (!current.ok || !current.defaults) throw new Error(current.error || c.value.failed)
      const patch = { ...current.preferences }
      if (!current.push_supported) delete (patch as Partial<typeof patch>).push_enabled
      await api('/config', { method: 'POST', body: JSON.stringify({ game_defaults: { ...current.defaults, ...patch } }) })
      message.value = c.value.saved
    } else {
      const result = await api<GamePreferenceResponse>(endpoint(), { method: 'POST', body: JSON.stringify({ apply_defaults: true }) })
      if (!result.ok) throw new Error(result.error || c.value.failed)
      message.value = c.value.applied
      if (result.resume?.ok === false) error.value = c.value.resumeFailed
      emit('changed')
    }
  } catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}
</script>

<template>
  <section class="game-default-actions" data-testid="game-default-actions">
    <h4>{{ c.current }}</h4><p class="muted">{{ c.currentHint }}</p>
    <template v-if="canManage">
      <button type="button" :disabled="busy" data-testid="save-current-game-defaults" @click="perform('save')">{{ c.saveCurrent }}</button>
      <button type="button" :disabled="busy" data-testid="apply-game-defaults" @click="perform('apply')">{{ c.apply }}</button>
      <RouterLink :to="{ name: 'settings', query: { section: 'game', focus: 'game-defaults' } }">{{ c.manage }}</RouterLink>
    </template>
    <p v-if="message" role="status">{{ message }}</p><p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.game-default-actions { display: grid; gap: 10px; min-width: 0; padding-bottom: 14px; border-bottom: 1px solid var(--df-border-soft); }
h4, p { margin: 0; }
p, a { font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
[role='status'] { color: var(--df-success); }
[role='alert'] { color: var(--df-danger-strong); }
</style>
