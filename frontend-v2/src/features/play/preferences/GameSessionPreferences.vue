<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { GamePreferences } from '@/api/types'
import { api, errorMessage } from '@/api/client'
import { useLocale } from '@/composables/useLocale'
import GamePreferenceFields from '@/features/game-preferences/GamePreferenceFields.vue'
import { gamePreferencesCopy } from '@/features/game-preferences/copy'
import { defaultGamePreferences, type GamePreferenceResponse } from '@/features/game-preferences/model'

const props = withDefaults(defineProps<{ gameKey: string; revision: number; section?: 'checks' | 'actions' }>(), { section: 'checks' })
const emit = defineEmits<{ changed: [] }>()
const { locale } = useLocale()
const c = computed(() => gamePreferencesCopy(locale.value))
const state = ref<GamePreferenceResponse | null>(null), busy = ref(false), error = ref(''), message = ref('')
const values = computed(() => ({ ...defaultGamePreferences(), ...state.value?.preferences }))
const quickActionsSupported = computed(() => typeof state.value?.preferences?.quick_actions_enabled === 'boolean')
const endpoint = () => `/games/${encodeURIComponent(props.gameKey)}/preferences`
let generation = 0
async function load() {
  const current = ++generation
  busy.value = true; error.value = ''
  try {
    const response = await api<GamePreferenceResponse>(endpoint())
    if (current === generation) { state.value = response; if (!response.ok) error.value = response.error || c.value.failed }
  } catch (e) { if (current === generation) error.value = errorMessage(e) }
  finally { if (current === generation) busy.value = false }
}
async function change(patch: Partial<GamePreferences>) {
  if (busy.value) return
  if ('quick_actions_enabled' in patch && !quickActionsSupported.value) return
  const key = props.gameKey
  const previous = state.value
  if (previous) state.value = { ...previous, preferences: { ...previous.preferences, ...patch } }
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api<GamePreferenceResponse>(endpoint(), { method: 'POST', body: JSON.stringify({ preferences: patch }) })
    if (key !== props.gameKey) return
    if (!result.ok) throw new Error(result.error || c.value.failed)
    state.value = result
    message.value = c.value.currentSaved
    if (result.resume?.ok === false) error.value = c.value.resumeFailed
    emit('changed')
  } catch (e) {
    if (key === props.gameKey) { state.value = previous; error.value = errorMessage(e) }
  }
  finally { if (key === props.gameKey) busy.value = false }
}
watch(() => [props.gameKey, props.revision], () => { void load() }, { immediate: true })
</script>

<template>
  <section class="game-session-preferences" :data-testid="section === 'actions' ? 'game-action-preferences' : 'game-check-preferences'" :aria-busy="busy">
    <GamePreferenceFields v-if="state?.ok" :value="values" :scope="section" :push-supported="state.push_supported" :quick-actions-supported="quickActionsSupported" :disabled="busy" @update="change" />
    <p v-else-if="busy" class="muted">{{ c.loading }}</p>
    <p v-if="error" role="alert">{{ error }} <button type="button" @click="load">{{ c.retry }}</button></p>
    <p v-if="message" role="status">{{ message }}</p>
  </section>
</template>

<style scoped>
.game-session-preferences { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--df-border-soft); border-radius: 8px; min-width: 0; }
p { margin: 0; font-size: 12px; overflow-wrap: anywhere; }
[role='status'] { color: var(--df-success); }
[role='alert'] { color: var(--df-danger-strong); }
</style>
