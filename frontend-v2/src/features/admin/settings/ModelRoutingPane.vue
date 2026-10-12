<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NIcon, NInput, NInputNumber, NModal, NSwitch } from 'naive-ui'
import { AlertCircleOutline, CheckmarkCircleOutline, CubeOutline, ImageOutline, MicOutline, ServerOutline, SparklesOutline, VolumeHighOutline } from '@vicons/ionicons5'
import { api, errorMessage } from '@/api/client'
import HelpButton from '@/components/common/HelpButton.vue'
import TestResultCard from '@/components/admin/TestResultCard.vue'
import { useLocale } from '@/composables/useLocale'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { modelCapability, type ModelCapability } from '@/utils/providerModels'
import type { AppConfig, TestResult } from '@/api/types'

defineProps<{
  supported: boolean
  saving: boolean
  embeddingTesting: boolean
  embeddingResult: TestResult | null
}>()

const emit = defineEmits<{
  save: []
  'open-providers': []
  'toggle-and-save': [key: keyof AppConfig, value: boolean]
  'test-embedding': []
}>()

const store = useSettingsStore()
const { locale, t } = useLocale()
const providers = computed(() => store.config.ai_providers || [])
const openAiProviders = computed(() => providers.value.filter(provider => provider.api_format === 'openai'))
const ttsProvider = computed(() => String(store.config.tts_provider || 'browser'))
const asrProvider = computed(() => String(store.config.asr_provider || 'disabled'))
type ImagePromptField = 'style_prefix' | 'manual_rules' | 'manual_prompt' | 'auto_rules' | 'auto_prompt'
type ImagePromptConfigKey = 'imagegen_style_prefix' | 'imagegen_manual_rules' | 'imagegen_manual_prompt' | 'imagegen_auto_rules' | 'imagegen_auto_prompt'
const promptConfigKeys: Record<ImagePromptField, ImagePromptConfigKey> = {
  style_prefix: 'imagegen_style_prefix',
  manual_rules: 'imagegen_manual_rules',
  manual_prompt: 'imagegen_manual_prompt',
  auto_rules: 'imagegen_auto_rules',
  auto_prompt: 'imagegen_auto_prompt',
}
const optimizingField = ref<ImagePromptField | null>(null)
const optimizerError = ref('')
const optimizerPreview = ref<null | {
  field: ImagePromptField
  source: string
  optimized: string
  stale: boolean
}>(null)

const selectedImageProvider = computed(() => providers.value.find(
  provider => provider.id === String(store.config.imagegen_provider_ref || ''),
))
const imagePromptLimit = computed(() => {
  if (String(store.config.imagegen_provider || '') === 'minimax') return 1500
  const provider = selectedImageProvider.value
  if (String(store.config.imagegen_model || '') !== 'image-01') return 12000
  try {
    const hostname = new URL(String(provider?.base_url || '')).hostname.toLowerCase()
    return ['api.minimax.cn', 'api.minimaxi.com'].includes(hostname) ? 1500 : 12000
  } catch {
    return 12000
  }
})

function promptFieldValue(field: ImagePromptField): string {
  return String(store.config[promptConfigKeys[field]] || '')
}

function staticPromptChars(mode: 'manual' | 'auto'): number {
  const useManual = mode === 'manual' || !!store.config.imagegen_auto_use_manual_prompt
  const values = [
    promptFieldValue('style_prefix'),
    promptFieldValue(useManual ? 'manual_rules' : 'auto_rules'),
    promptFieldValue(useManual ? 'manual_prompt' : 'auto_prompt'),
  ].map(value => value.trim()).filter(Boolean)
  return values.join('\n\n').length
}

const manualStaticChars = computed(() => staticPromptChars('manual'))
const autoStaticChars = computed(() => staticPromptChars('auto'))

async function optimizePrompt(field: ImagePromptField) {
  const source = promptFieldValue(field).trim()
  if (!source || optimizingField.value) return
  optimizingField.value = field
  optimizerError.value = ''
  try {
    const result = await api<{ ok: boolean; text: string }>('/image-prompts/optimize', {
      method: 'POST',
      body: JSON.stringify({ field, text: source, language: locale.value }),
    })
    optimizerPreview.value = {
      field,
      source,
      optimized: String(result.text || '').trim(),
      stale: promptFieldValue(field).trim() !== source,
    }
  } catch (error: unknown) {
    optimizerError.value = errorMessage(error)
  } finally {
    optimizingField.value = null
  }
}

function applyOptimizedPrompt() {
  const preview = optimizerPreview.value
  if (!preview || preview.stale) return
  setString(promptConfigKeys[preview.field], preview.optimized)
  optimizerPreview.value = null
}
function eventValue(event: Event): string {
  return (event.target as HTMLSelectElement | null)?.value || ''
}

function setString(key: keyof AppConfig, value: string | number) {
  store.setConfigField(key, String(value).trim())
}

function setNumber(key: keyof AppConfig, value: string | number | null) {
  if (value != null) store.setConfigField(key, Number(value))
}

function savedModels(providerId: string, capability?: ModelCapability): string[] {
  const provider = providers.value.find(item => item.id === providerId)
  const models = provider?.models || []
  return capability
    ? models.filter(model => modelCapability(model, provider?.model_capabilities?.[model]) === capability)
    : models
}

function setRoleProvider(
  providerKey: keyof AppConfig,
  modelKey: keyof AppConfig,
  providerId: string,
  capability: ModelCapability,
) {
  setString(providerKey, providerId)
  const models = savedModels(providerId, capability)
  const current = String((store.config as Record<string, unknown>)[modelKey] || '')
  if (!models.includes(current)) setString(modelKey, models[0] || '')
}

function setTtsProvider(value: string) {
  setString('tts_provider', value)
  if (value === 'browser' || value === 'edge-tts') setString('tts_provider_ref', '')
  const voice = String(store.config.tts_default_voice || '')
  if (value === 'edge-tts' && !voice.endsWith('Neural')) setString('tts_default_voice', 'zh-CN-XiaoxiaoNeural')
  else if (value === 'openai-compatible' && voice.endsWith('Neural')) setString('tts_default_voice', 'alloy')
}

function setAsrProvider(value: string) {
  setString('asr_provider', value)
  if (value === 'disabled') setString('asr_provider_ref', '')
}
</script>

<template>
  <div class="settings-pane model-routing-pane">
    <header class="model-routing-header">
      <div><h3>{{ t('modelRoutingTitle') }}</h3><p>{{ t('modelRoutingHint') }}</p></div>
      <div class="model-routing-actions">
        <HelpButton :title="t('modelRoutingHelpTitle')">
          <h4>{{ t('modelRoutingHelpMainTitle') }}</h4><p>{{ t('modelRoutingHelpMainText') }}</p>
          <h4>{{ t('modelRoutingHelpFallbackTitle') }}</h4><p>{{ t('modelRoutingHelpFallbackText') }}</p>
          <h4>{{ t('modelRoutingHelpOptionalTitle') }}</h4><p>{{ t('modelRoutingHelpOptionalText') }}</p>
          <h4>{{ t('modelRoutingHelpExampleTitle') }}</h4><p>{{ t('modelRoutingHelpExampleText') }}</p>
        </HelpButton>
        <NButton class="model-routing-save" type="success" :loading="saving" :disabled="!supported" @click="emit('save')">
          <template #icon><NIcon :component="CheckmarkCircleOutline" /></template>{{ t('modelRoutingSave') }}
        </NButton>
      </div>
    </header>

    <div v-if="!supported" class="provider-backend-warning compact">
      <NIcon :component="AlertCircleOutline" /><div><strong>{{ t('providerBackendOutdatedTitle') }}</strong><p>{{ t('providerBackendOutdated') }}</p></div>
    </div>
    <div v-else-if="!providers.length" class="model-routing-empty">
      <NIcon :component="ServerOutline" /><div><strong>{{ t('modelRoutingNoProviders') }}</strong><p>{{ t('modelRoutingNoProvidersHint') }}</p></div>
      <NButton @click="emit('open-providers')">{{ t('providerAdd') }}</NButton>
    </div>

    <div v-if="supported" class="model-routing-grid" :class="{ 'is-saving': saving }">
      <article class="model-role-card model-role-card-main">
        <header><NIcon :component="SparklesOutline" /><div><h4>{{ t('modelRoleMain') }}</h4><p>{{ t('modelRoleMainHint') }}</p></div></header>
        <label><span>{{ t('providerName') }}</span><select :value="store.config.llm_provider_ref || ''" @change="setRoleProvider('llm_provider_ref', 'model', eventValue($event), 'chat')"><option value="">{{ t('modelRoutingChooseProvider') }}</option><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name || provider.id }}</option></select></label>
        <label><span>{{ t('model') }}</span><select :value="store.config.model || ''" :disabled="!store.config.llm_provider_ref" @change="setString('model', eventValue($event))"><option value="">{{ t('modelRoutingChooseModel') }}</option><option v-for="model in savedModels(String(store.config.llm_provider_ref || ''), 'chat')" :key="model" :value="model">{{ model }}</option></select></label>
        <div class="model-fallback-grid">
          <section v-for="slot in [1, 2]" :key="slot" class="model-fallback-slot">
            <header><strong>{{ t(slot === 1 ? 'fallbackSlot1' : 'fallbackSlot2') }}</strong><NSwitch :value="!!store.config[slot === 1 ? 'fallback1_enabled' : 'fallback2_enabled']" :disabled="saving" @update:value="emit('toggle-and-save', slot === 1 ? 'fallback1_enabled' : 'fallback2_enabled', $event)" /></header>
            <label><span>{{ t('providerName') }}</span><select :value="store.config[slot === 1 ? 'fallback1_provider_ref' : 'fallback2_provider_ref'] || ''" :disabled="!store.config[slot === 1 ? 'fallback1_enabled' : 'fallback2_enabled']" @change="setRoleProvider(slot === 1 ? 'fallback1_provider_ref' : 'fallback2_provider_ref', slot === 1 ? 'fallback1_model' : 'fallback2_model', eventValue($event), 'chat')"><option value="">{{ t('modelRoutingChooseProvider') }}</option><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name || provider.id }}</option></select></label>
            <label><span>{{ t('model') }}</span><select :value="store.config[slot === 1 ? 'fallback1_model' : 'fallback2_model'] || ''" :disabled="!store.config[slot === 1 ? 'fallback1_enabled' : 'fallback2_enabled'] || !store.config[slot === 1 ? 'fallback1_provider_ref' : 'fallback2_provider_ref']" @change="setString(slot === 1 ? 'fallback1_model' : 'fallback2_model', eventValue($event))"><option value="">{{ t('modelRoutingChooseModel') }}</option><option v-for="model in savedModels(String(store.config[slot === 1 ? 'fallback1_provider_ref' : 'fallback2_provider_ref'] || ''), 'chat')" :key="model" :value="model">{{ model }}</option></select></label>
          </section>
        </div>
      </article>

      <div class="model-capability-grid">
        <div class="model-capability-column">
          <article class="model-role-card model-role-card-embedding">
            <header><NIcon :component="CubeOutline" /><div><h4>{{ t('modelRoleEmbedding') }}</h4><p>{{ t('modelRoleEmbeddingHint') }}</p></div><HelpButton :title="t('embeddingHelpTitle')"><h4>{{ t('embeddingHelpWhatTitle') }}</h4><p>{{ t('embeddingHelpWhatText') }}</p><h4>{{ t('embeddingHelpChooseTitle') }}</h4><p>{{ t('embeddingHelpChooseBefore') }} <code>bge-m3</code>{{ t('embeddingHelpChooseAfter') }} <code>text-embedding-3-small</code>, <code>gte-large</code>, <code>nomic-embed-text</code>{{ t('embeddingHelpChooseSuffix') }}</p><h4>{{ t('embeddingHelpConfigTitle') }}</h4><p>{{ t('embeddingHelpCentralized') }}</p><h4>{{ t('test') }}</h4><p>{{ t('embeddingHelpTest') }}</p></HelpButton></header>
            <label class="model-role-enabled"><span>{{ t('vectorMemory') }}</span><NSwitch :value="!!store.config.embedding_enabled" :disabled="saving" @update:value="emit('toggle-and-save', 'embedding_enabled', $event)" /></label>
            <label><span>{{ t('providerName') }}</span><select :value="store.config.embedding_provider_ref || ''" :disabled="!store.config.embedding_enabled" @change="setRoleProvider('embedding_provider_ref', 'embedding_model', eventValue($event), 'embedding')"><option value="">{{ t('modelRoutingChooseProvider') }}</option><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name || provider.id }}</option></select></label>
            <label><span>{{ t('model') }}</span><select :value="store.config.embedding_model || ''" :disabled="!store.config.embedding_enabled || !store.config.embedding_provider_ref" @change="setString('embedding_model', eventValue($event))"><option value="">{{ t('modelRoutingChooseModel') }}</option><option v-for="model in savedModels(String(store.config.embedding_provider_ref || ''), 'embedding')" :key="model" :value="model">{{ model }}</option></select></label>
            <label><span>{{ t('maxInput') }}</span><NInputNumber :value="store.config.embedding_max_input ?? 0" :min="0" :disabled="!store.config.embedding_enabled" @update:value="setNumber('embedding_max_input', $event)" /></label>
            <p class="model-role-field-hint">{{ t('maxInputHint') }}</p><div class="model-role-actions"><NButton :loading="embeddingTesting" :disabled="!store.config.embedding_enabled" @click="emit('test-embedding')">{{ t('testEmbeddingConnection') }}</NButton></div>
            <TestResultCard v-if="embeddingResult" :result="embeddingResult" kind="embedding" />
          </article>
          <article class="model-role-card">
            <header><NIcon :component="VolumeHighOutline" /><div><h4>{{ t('modelRoleTts') }}</h4><p>{{ t('modelRoleTtsHint') }}</p></div></header>
            <label><span>{{ t('modelRoutingMode') }}</span><select :value="store.config.tts_provider || 'browser'" @change="setTtsProvider(eventValue($event))"><option value="browser">{{ t('ttsProviderBrowser') }}</option><option value="edge-tts">{{ t('ttsProviderEdge') }}</option><option value="openai-compatible">{{ t('ttsProviderOpenAI') }}</option><option value="gpt-sovits">GPT-SoVITS</option></select></label>
            <template v-if="ttsProvider === 'openai-compatible' || ttsProvider === 'gpt-sovits'"><label><span>{{ t('providerName') }}</span><select :value="store.config.tts_provider_ref || ''" @change="setRoleProvider('tts_provider_ref', 'tts_model', eventValue($event), 'tts')"><option value="">{{ t('modelRoutingChooseProvider') }}</option><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name || provider.id }}</option></select></label><label><span>{{ t('model') }}</span><select :value="store.config.tts_model || ''" :disabled="!store.config.tts_provider_ref" @change="setString('tts_model', eventValue($event))"><option value="">{{ t('modelRoutingChooseModel') }}</option><option v-for="model in savedModels(String(store.config.tts_provider_ref || ''), 'tts')" :key="model" :value="model">{{ model }}</option></select></label></template>
          </article>
        </div>
        <div class="model-capability-column">
          <article class="model-role-card">
            <header><NIcon :component="ImageOutline" /><div><h4>{{ t('modelRoleImagegen') }}</h4><p>{{ t('modelRoleImagegenHint') }}</p></div></header>
            <label class="model-role-enabled"><span>{{ t('enabled') }}</span><NSwitch :value="!!store.config.imagegen_enabled" :disabled="saving" @update:value="emit('toggle-and-save', 'imagegen_enabled', $event)" /></label>
            <label class="model-role-enabled"><span>{{ t('imagegenAutoScene') }}</span><NSwitch :value="!!store.config.imagegen_auto_scene" :disabled="saving || !store.config.imagegen_enabled" @update:value="emit('toggle-and-save', 'imagegen_auto_scene', $event)" /></label>
            <label class="model-role-enabled"><span>{{ t('imagegenManualScene') }}</span><NSwitch :value="!!store.config.imagegen_manual_scene" :disabled="saving || !store.config.imagegen_enabled" @update:value="emit('toggle-and-save', 'imagegen_manual_scene', $event)" /></label>
             <div class="model-role-enabled"><span>{{ t('imagegenAutoStoryboard') }}<HelpButton compact :title="t('imagegenAutoStoryboardHelp')" button-label="?" /></span><NSwitch :value="!!store.config.imagegen_auto_storyboard" :disabled="saving || !store.config.imagegen_enabled" @update:value="emit('toggle-and-save', 'imagegen_auto_storyboard', $event)" /></div>
            <label><span>{{ t('providerName') }}</span><select :value="store.config.imagegen_provider_ref || ''" :disabled="!store.config.imagegen_enabled" @change="setRoleProvider('imagegen_provider_ref', 'imagegen_model', eventValue($event), 'image')"><option value="">{{ t('modelRoutingChooseProvider') }}</option><option v-for="provider in openAiProviders" :key="provider.id" :value="provider.id">{{ provider.name || provider.id }}</option></select></label>
            <label><span>{{ t('model') }}</span><select :value="store.config.imagegen_model || ''" :disabled="!store.config.imagegen_enabled || !store.config.imagegen_provider_ref" @change="setString('imagegen_model', eventValue($event))"><option value="">{{ t('modelRoutingChooseModel') }}</option><option v-for="model in savedModels(String(store.config.imagegen_provider_ref || ''), 'image')" :key="model" :value="model">{{ model }}</option></select></label>
            <div class="imagegen-style-field imagegen-prompt-field">
              <div class="imagegen-prompt-field-head"><span>{{ t('imagegenStylePrefix') }}</span><NButton size="tiny" secondary :loading="optimizingField === 'style_prefix'" :disabled="!store.config.imagegen_enabled || !promptFieldValue('style_prefix').trim() || !!optimizingField" @click="optimizePrompt('style_prefix')"><template #icon><NIcon :component="SparklesOutline" /></template>{{ t('imagegenOptimizePrompt') }}</NButton></div>
              <NInput type="textarea" :value="String(store.config.imagegen_style_prefix || '')" :disabled="!store.config.imagegen_enabled" :placeholder="t('imagegenStylePrefixPlaceholder')" :autosize="{ minRows: 3, maxRows: 8 }" @update:value="setString('imagegen_style_prefix', $event)" />
            </div>
            <details class="imagegen-advanced-settings">
              <summary>{{ t('imagegenAdvancedSettings') }}</summary>
              <div class="imagegen-advanced-fields">
                <label class="model-role-enabled"><span>{{ t('imagegenAutoUseManualPrompt') }}</span><NSwitch :value="!!store.config.imagegen_auto_use_manual_prompt" :disabled="saving || !store.config.imagegen_enabled" @update:value="emit('toggle-and-save', 'imagegen_auto_use_manual_prompt', $event)" /></label>
                <div class="imagegen-prompt-field"><div class="imagegen-prompt-field-head"><span>{{ t('imagegenManualRules') }}</span><NButton size="tiny" secondary :loading="optimizingField === 'manual_rules'" :disabled="!store.config.imagegen_enabled || !promptFieldValue('manual_rules').trim() || !!optimizingField" @click="optimizePrompt('manual_rules')"><template #icon><NIcon :component="SparklesOutline" /></template>{{ t('imagegenOptimizePrompt') }}</NButton></div><NInput type="textarea" :value="String(store.config.imagegen_manual_rules || '')" :disabled="!store.config.imagegen_enabled" :placeholder="t('imagegenManualRulesPlaceholder')" :autosize="{ minRows: 3, maxRows: 8 }" @update:value="setString('imagegen_manual_rules', $event)" /></div>
                <div class="imagegen-prompt-field"><div class="imagegen-prompt-field-head"><span>{{ t('imagegenManualPrompt') }}</span><NButton size="tiny" secondary :loading="optimizingField === 'manual_prompt'" :disabled="!store.config.imagegen_enabled || !promptFieldValue('manual_prompt').trim() || !!optimizingField" @click="optimizePrompt('manual_prompt')"><template #icon><NIcon :component="SparklesOutline" /></template>{{ t('imagegenOptimizePrompt') }}</NButton></div><NInput type="textarea" :value="String(store.config.imagegen_manual_prompt || '')" :disabled="!store.config.imagegen_enabled" :placeholder="t('imagegenManualPromptPlaceholder')" :autosize="{ minRows: 3, maxRows: 8 }" @update:value="setString('imagegen_manual_prompt', $event)" /></div>
                <p v-if="store.config.imagegen_auto_use_manual_prompt" class="imagegen-reuse-hint">{{ t('imagegenAutoUsesManualHint') }}</p>
                <template v-else>
                  <div class="imagegen-prompt-field"><div class="imagegen-prompt-field-head"><span>{{ t('imagegenAutoRules') }}</span><NButton size="tiny" secondary :loading="optimizingField === 'auto_rules'" :disabled="!store.config.imagegen_enabled || !promptFieldValue('auto_rules').trim() || !!optimizingField" @click="optimizePrompt('auto_rules')"><template #icon><NIcon :component="SparklesOutline" /></template>{{ t('imagegenOptimizePrompt') }}</NButton></div><NInput type="textarea" :value="String(store.config.imagegen_auto_rules || '')" :disabled="!store.config.imagegen_enabled" :placeholder="t('imagegenAutoRulesPlaceholder')" :autosize="{ minRows: 3, maxRows: 8 }" @update:value="setString('imagegen_auto_rules', $event)" /></div>
                  <div class="imagegen-prompt-field"><div class="imagegen-prompt-field-head"><span>{{ t('imagegenAutoPrompt') }}</span><NButton size="tiny" secondary :loading="optimizingField === 'auto_prompt'" :disabled="!store.config.imagegen_enabled || !promptFieldValue('auto_prompt').trim() || !!optimizingField" @click="optimizePrompt('auto_prompt')"><template #icon><NIcon :component="SparklesOutline" /></template>{{ t('imagegenOptimizePrompt') }}</NButton></div><NInput type="textarea" :value="String(store.config.imagegen_auto_prompt || '')" :disabled="!store.config.imagegen_enabled" :placeholder="t('imagegenAutoPromptPlaceholder')" :autosize="{ minRows: 3, maxRows: 8 }" @update:value="setString('imagegen_auto_prompt', $event)" /></div>
                </template>
                <div class="imagegen-budget" :class="{ warning: manualStaticChars > imagePromptLimit / 2 || autoStaticChars > imagePromptLimit / 2 }">
                  <span>{{ t('imagegenPromptBudget', { limit: imagePromptLimit }) }}</span>
                  <small>{{ t('imagegenManualStaticChars', { count: manualStaticChars }) }} · {{ t('imagegenAutoStaticChars', { count: autoStaticChars }) }}</small>
                  <small>{{ t('imagegenPromptBudgetHint') }}</small>
                </div>
                <p v-if="optimizerError" class="imagegen-optimizer-error">{{ optimizerError }}</p>
                <label><span>{{ t('imagegenSquareSize') }}</span><NInput :value="String(store.config.imagegen_square_size || '')" :disabled="!store.config.imagegen_enabled" :placeholder="t('imagegenDefaultSizeHint')" @update:value="setString('imagegen_square_size', $event)" /><small>{{ t('imagegenDefaultSizeHint') }}</small></label>
                <label><span>{{ t('imagegenLandscapeSize') }}</span><NInput :value="String(store.config.imagegen_landscape_size || '')" :disabled="!store.config.imagegen_enabled" :placeholder="t('imagegenDefaultSizeHint')" @update:value="setString('imagegen_landscape_size', $event)" /><small>{{ t('imagegenDefaultSizeHint') }}</small></label>
                <label><span>{{ t('imagegenQuality') }}</span><NInput :value="String(store.config.imagegen_quality || '')" :disabled="!store.config.imagegen_enabled" @update:value="setString('imagegen_quality', $event)" /></label>
                <label><span>{{ t('imagegenTimeout') }}</span><NInputNumber :value="Number(store.config.imagegen_timeout_seconds || 120)" :min="5" :max="300" :disabled="!store.config.imagegen_enabled" @update:value="setNumber('imagegen_timeout_seconds', $event)" /></label>
              </div>
            </details>
          </article>
          <article class="model-role-card">
            <header><NIcon :component="MicOutline" /><div><h4>{{ t('modelRoleAsr') }}</h4><p>{{ t('modelRoleAsrHint') }}</p></div></header>
            <label><span>{{ t('modelRoutingMode') }}</span><select :value="store.config.asr_provider || 'disabled'" @change="setAsrProvider(eventValue($event))"><option value="disabled">{{ t('asrProviderDisabled') }}</option><option value="openai-compatible">{{ t('asrProviderOpenAI') }}</option></select></label>
            <template v-if="asrProvider === 'openai-compatible'"><label><span>{{ t('providerName') }}</span><select :value="store.config.asr_provider_ref || ''" @change="setRoleProvider('asr_provider_ref', 'asr_model', eventValue($event), 'asr')"><option value="">{{ t('modelRoutingChooseProvider') }}</option><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name || provider.id }}</option></select></label><label><span>{{ t('model') }}</span><select :value="store.config.asr_model || ''" :disabled="!store.config.asr_provider_ref" @change="setString('asr_model', eventValue($event))"><option value="">{{ t('modelRoutingChooseModel') }}</option><option v-for="model in savedModels(String(store.config.asr_provider_ref || ''), 'asr')" :key="model" :value="model">{{ model }}</option></select></label></template>
          </article>
        </div>
      </div>
    </div>
    <NModal :show="!!optimizerPreview" preset="card" class="imagegen-optimizer-modal" :title="t('imagegenOptimizePreview')" @update:show="!$event && (optimizerPreview = null)">
      <div v-if="optimizerPreview" class="imagegen-optimizer-preview">
        <label><span>{{ t('imagegenOptimizeOriginal') }} ({{ optimizerPreview.source.length }})</span><NInput type="textarea" :value="optimizerPreview.source" readonly :autosize="{ minRows: 4, maxRows: 10 }" /></label>
        <label><span>{{ t('imagegenOptimizeResult') }} ({{ optimizerPreview.optimized.length }})</span><NInput type="textarea" :value="optimizerPreview.optimized" readonly :autosize="{ minRows: 4, maxRows: 10 }" /></label>
        <p v-if="optimizerPreview.stale" class="imagegen-optimizer-error">{{ t('imagegenOptimizeStale') }}</p>
        <footer><NButton @click="optimizerPreview = null">{{ t('cancel') }}</NButton><NButton type="primary" :disabled="optimizerPreview.stale" @click="applyOptimizedPrompt">{{ t('imagegenUseOptimized') }}</NButton></footer>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.imagegen-style-field :deep(.n-input),
.imagegen-style-field :deep(textarea) { width: 100%; max-width: 100%; min-width: 0; box-sizing: border-box; }
.imagegen-style-field { display: grid; gap: 6px; min-width: 0; }
.imagegen-advanced-settings { margin-top: 4px; border: 1px solid var(--df-border-soft); border-radius: 8px; padding: 8px 10px; }
.imagegen-advanced-settings > summary { cursor: pointer; color: var(--df-text); font-weight: 700; }
.imagegen-advanced-fields { display: grid; gap: 8px; margin-top: 10px; }
.imagegen-advanced-fields > label { display: grid; gap: 6px; min-width: 0; }
.imagegen-advanced-fields :deep(.n-input),
.imagegen-advanced-fields :deep(.n-input-number) { width: 100%; max-width: 100%; min-width: 0; }
.imagegen-advanced-fields small { color: var(--df-text-muted); font-size: 11px; }
.imagegen-prompt-field { display: grid; gap: 6px; min-width: 0; }
.imagegen-prompt-field-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.imagegen-prompt-field-head > span { min-width: 0; color: var(--df-text); overflow-wrap: anywhere; }
.imagegen-prompt-field-head :deep(.n-button) { flex: 0 0 auto; }
.imagegen-reuse-hint { margin: 0; color: var(--df-text-muted); font-size: 12px; }
.imagegen-budget { display: grid; gap: 3px; padding: 8px 0; color: var(--df-text-muted); border-top: 1px solid var(--df-border-soft); }
.imagegen-budget.warning { color: var(--df-warning, #a16207); }
.imagegen-budget small { color: inherit; }
.imagegen-optimizer-error { margin: 0; color: var(--df-danger, #c2413a); font-size: 12px; }
.imagegen-optimizer-modal { width: min(720px, calc(100vw - 24px)); }
.imagegen-optimizer-preview { display: grid; gap: 12px; }
.imagegen-optimizer-preview label { display: grid; gap: 6px; min-width: 0; }
.imagegen-optimizer-preview footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>
