<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NInputNumber } from 'naive-ui'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import { errorMessage } from '@/api/client'
import { generationSettingsCopy } from './generationSettingsCopy'

defineProps<{ embedded?: boolean; disabled?: boolean }>()
const store = useSettingsStore()
const { locale } = useLocale()
const toast = useToast()
const copy = computed(() => generationSettingsCopy(locale.value))
const saving = ref(false)
const options = computed(() => store.config.llm_generation_options || {})
const fields = [
  { key: 'temperature', min: 0, max: 2 }, { key: 'top_p', min: 0, max: 1 },
  { key: 'frequency_penalty', min: -2, max: 2 }, { key: 'presence_penalty', min: -2, max: 2 },
] as const
function setOption(key: typeof fields[number]['key'], value: number | null) {
  const next = { ...options.value }
  if (value === null) delete next[key]
  else next[key] = value
  store.setConfigField('llm_generation_options', next)
}
async function save() {
  saving.value = true
  try { await store.saveSection(['llm_generation_options', 'context_recent_rounds']); toast.success(copy.value.saved) }
  catch (error) { toast.error(errorMessage(error)) }
  finally { saving.value = false }
}
</script>

<template>
  <section id="settings-generation-options" class="generation-tuning">
    <header><h4>{{ copy.title }}</h4><p>{{ copy.hint }}</p></header>
    <div class="generation-options-grid">
      <label v-for="field in fields" :key="field.key"><span>{{ copy[field.key] }}</span><NInputNumber :value="options[field.key] ?? null" :min="field.min" :max="field.max" :step="0.1" :placeholder="copy.default" clearable :disabled="saving || disabled" @update:value="setOption(field.key, $event)" /></label>
    </div>
    <label id="settings-history-rounds" class="generation-history"><span>{{ copy.history }}</span><NInputNumber :value="Number(store.config.context_recent_rounds ?? 0)" :min="0" :max="100" :precision="0" :disabled="saving || disabled" @update:value="store.setConfigField('context_recent_rounds', $event ?? 0)" /><small>{{ copy.historyHint }}</small></label>
    <footer v-if="!embedded"><NButton type="primary" :loading="saving" @click="save">{{ copy.save }}</NButton></footer>
  </section>
</template>

<style scoped>
.generation-tuning { min-width: 0; }
header h4 { margin: 0; color: var(--df-text); font-size: 14px; }
header p, small { margin: 6px 0 0; color: var(--df-text-muted); font-size: 12px; line-height: 1.6; }
.generation-options-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin: 18px 0; }
label { display: grid; gap: 8px; min-width: 0; color: var(--df-text-secondary); font-size: 12px; }
label :deep(.n-input-number) { width: 100%; min-width: 0; }
.generation-history { max-width: 100%; }
.generation-history :deep(.n-input-number) { max-width: 220px; }
footer { display: flex; justify-content: flex-end; margin-top: 18px; }
@media(max-width: 560px) { .generation-options-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
