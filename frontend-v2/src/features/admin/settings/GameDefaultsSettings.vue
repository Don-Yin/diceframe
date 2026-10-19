<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton } from 'naive-ui'
import type { GamePreferences } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { errorMessage } from '@/api/client'
import GamePreferenceFields from '@/features/game-preferences/GamePreferenceFields.vue'
import { gamePreferencesCopy } from '@/features/game-preferences/copy'
import { defaultGamePreferences } from '@/features/game-preferences/model'

const store = useSettingsStore()
const { locale } = useLocale()
const c = computed(() => gamePreferencesCopy(locale.value))
const values = computed(() => ({ ...defaultGamePreferences(), ...store.config.game_defaults }))
const quickActionsSupported = computed(() => typeof store.config.game_defaults?.quick_actions_enabled === 'boolean')
const busy = ref(false), message = ref(''), error = ref('')
function serverValues(values: GamePreferences): Partial<GamePreferences> {
  const result: Partial<GamePreferences> = { ...values }
  if (!quickActionsSupported.value) delete result.quick_actions_enabled
  return result
}
function change(patch: Partial<GamePreferences>) {
  store.setConfigField('game_defaults', serverValues({ ...values.value, ...patch }))
  message.value = ''
}
async function save() {
  busy.value = true; error.value = ''; message.value = ''
  try {
    store.setConfigField('game_defaults', serverValues(values.value))
    await store.saveSection(['game_defaults'])
    message.value = c.value.saved
  } catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}
</script>

<template>
  <section id="settings-game-defaults" class="settings-general-group" data-testid="game-defaults-settings">
    <header class="game-defaults-intro"><h3>{{ c.title }}</h3><p>{{ c.hint }}</p></header>
    <GamePreferenceFields :value="values" settings-layout :quick-actions-supported="quickActionsSupported" :disabled="busy || store.loading" @update="change">
      <template #footer><footer class="advanced-save-row defaults-footer"><span v-if="message" role="status">{{ message }}</span><span v-if="error" role="alert">{{ error }}</span><NButton type="primary" :loading="busy" :disabled="store.loading" data-testid="save-game-defaults" @click="save">{{ c.save }}</NButton></footer></template>
    </GamePreferenceFields>
  </section>
</template>

<style scoped>
.game-defaults-intro h3 { margin: 0; }
.game-defaults-intro p { margin: 6px 0 0; color: var(--df-text-muted); font-size: 12px; line-height: 1.6; }
.defaults-footer { flex-wrap: wrap; align-items: center; }
[role='status'] { color: var(--df-success); font-size: 12px; }
[role='alert'] { color: var(--df-danger-strong); overflow-wrap: anywhere; }
</style>
