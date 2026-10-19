<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NIcon, NInputNumber } from 'naive-ui'
import { ChevronDownOutline, OptionsOutline } from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { useToast } from '@/composables/useToast'
import { errorMessage } from '@/api/client'
import GenerationTuning from './GenerationTuning.vue'
import { generationSettingsCopy } from './generationSettingsCopy'

const props = defineProps<{ disabled?: boolean }>()
const { locale, t } = useLocale()
const store = useSettingsStore()
const toast = useToast()
const copy = computed(() => generationSettingsCopy(locale.value))
const saving = ref(false)
const locked = computed(() => props.disabled || saving.value)
const tokenFields = [
  { key: 'narrative_max_tokens', label: 'narrativeTokens', hint: 'narrativeTokensHint' },
  { key: 'character_gen_max_tokens', label: 'characterGenTokens', hint: 'characterGenTokensHint' },
  { key: 'summary_max_tokens', label: 'summaryTokens', hint: 'summaryTokensHint' },
  { key: 'brief_max_tokens', label: 'briefTokens', hint: 'briefTokensHint' },
  { key: 'analysis_max_tokens', label: 'analysisTokens', hint: 'analysisTokensHint' },
  { key: 'text_gen_max_tokens', label: 'textGenTokens', hint: 'textGenTokensHint' },
] as const

async function save() {
  saving.value = true
  try {
    await store.saveSection(['llm_generation_options', 'context_recent_rounds', 'model_request_timeout_seconds', ...tokenFields.map(field => field.key)])
    toast.success(t('settingsSaved'))
  } catch (error) { toast.error(errorMessage(error)) }
  finally { saving.value = false }
}
</script>

<template>
  <details class="model-role-card generation-settings">
    <summary>
      <NIcon :component="OptionsOutline" class="generation-settings-icon" />
      <div><strong>{{ copy.advancedTitle }}</strong><p>{{ copy.advancedHint }}</p></div>
      <NIcon :component="ChevronDownOutline" class="generation-settings-chevron" />
    </summary>
    <div class="generation-settings-body">
      <GenerationTuning embedded :disabled="locked" />
      <section id="settings-generation" class="generation-budgets">
        <header><h4>{{ t('generationParams') }}</h4><p>{{ t('generationParamsHint') }}</p></header>
        <div class="generation-budget-row token-row">
          <div><strong>{{ t('modelRequestTimeout') }}</strong><small>{{ t('modelRequestTimeoutHint') }}</small></div>
          <div class="generation-budget-input"><NInputNumber :value="Number(store.config.model_request_timeout_seconds ?? 120)" :min="10" :max="600" :step="10" :disabled="locked" @update:value="store.setConfigField('model_request_timeout_seconds', $event ?? 0)" /><span>{{ t('secondsUnit') }}</span></div>
        </div>
        <div v-for="field in tokenFields" :id="`settings-${field.key}`" :key="field.key" class="generation-budget-row token-row">
          <div><strong>{{ t(field.label) }}</strong><small>{{ t(field.hint) }}</small></div>
          <div class="generation-budget-input"><NInputNumber :value="Number(store.config[field.key] ?? 0)" :step="256" :disabled="locked" @update:value="store.setConfigField(field.key, $event ?? 0)" /><span>Token</span></div>
        </div>
      </section>
      <footer class="generation-settings-save"><NButton type="primary" :loading="saving" :disabled="locked" @click="save">{{ t('saveAction') }}</NButton></footer>
    </div>
  </details>
</template>

<style scoped>
.generation-settings { margin-top: 20px; box-shadow: none; }
.generation-settings > summary { display: flex; gap: 12px; cursor: pointer; min-width: 0; }
summary > div { flex: 1; min-width: 0; }
summary strong { color: var(--df-text); font-size: 14px; }
summary p { color: var(--df-text-muted); font-size: 12px; line-height: 1.6; }
.generation-settings-icon { flex: 0 0 auto; font-size: 20px; color: var(--df-interactive); }
.generation-settings-chevron { flex: 0 0 auto; transition: transform .18s ease; }
.generation-settings[open] .generation-settings-chevron { transform: rotate(180deg); }
.generation-settings-body { display: grid; gap: 24px; margin-top: 20px; min-width: 0; }
.generation-budgets { display: grid; gap: 16px; min-width: 0; padding-top: 22px; border-top: 1px solid var(--df-border-soft); }
header h4 { margin: 0; font-size: 14px; color: var(--df-text); }
header p { margin: 6px 0 0; font-size: 12px; line-height: 1.6; }
.generation-budget-row { display: grid; grid-template-columns: minmax(0, 1fr) 220px; align-items: center; gap: 18px; }
.generation-budget-row > div:first-child { display: grid; gap: 5px; min-width: 0; }
.generation-budget-row strong { font-size: 12px; color: var(--df-text-secondary); }
.generation-budget-row small { color: var(--df-text-muted); font-size: 12px; line-height: 1.5; }
.generation-budget-input { display: grid; grid-template-columns: minmax(0, 1fr) 40px; align-items: center; gap: 8px; min-width: 0; }
.generation-budget-input :deep(.n-input-number) { width: 100%; min-width: 0; }
.generation-budget-input span { color: var(--df-text-muted); font-size: 12px; }
.generation-settings-save { display: flex; justify-content: flex-end; padding-top: 18px; border-top: 1px solid var(--df-border-soft); }
@media (max-width: 640px) { .generation-budget-row { grid-template-columns: minmax(0, 1fr); gap: 10px; } }
</style>
