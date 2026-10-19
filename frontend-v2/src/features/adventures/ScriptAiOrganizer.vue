<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { errorMessage } from '@/api/client'
import { useLocale } from '@/composables/useLocale'
import { organizeScript, type AiImportProgress } from './scriptAi'
import { aiImportCopy } from './aiImportCopy'
import type { ScriptDraft, ScriptPreview } from './scriptTypes'

const props = defineProps<{ draft: ScriptDraft; disabled?: boolean }>()
const emit = defineEmits<{ apply: [preview: ScriptPreview]; running: [value: boolean] }>()
const { locale } = useLocale()
const copy = computed(() => aiImportCopy(locale.value))
const consent = ref(false), instructions = ref(''), running = ref(false), cancelled = ref(false), error = ref('')
const result = ref<ScriptPreview | null>(null)
const progress = ref<AiImportProgress>({ stage: 'preparing', completed: 0, total: 1 })
const sourceSnapshot = ref('')
let controller: AbortController | null = null, generation = 0
const snapshot = computed(() => JSON.stringify(props.draft))
const stale = computed(() => !!result.value && snapshot.value !== sourceSnapshot.value)
const scenes = computed(() => result.value?.draft.files['adventure.json'].nodes.filter(node => node.type === 'scene') || [])
const resourceCount = computed(() => Object.keys(result.value?.draft.files || {}).filter(path => path.startsWith('content/')).length)
const stageText = computed(() => progress.value.stage === 'organizing'
  ? copy.value.organizing.replace('{current}', String(progress.value.current || 1)).replace('{total}', String(progress.value.chunks || 1))
  : copy.value[progress.value.stage])

async function start() {
  if (!consent.value || running.value || props.disabled) return
  const current = ++generation
  controller = new AbortController()
  const signal = controller.signal
  sourceSnapshot.value = snapshot.value
  result.value = null; error.value = ''; cancelled.value = false
  progress.value = { stage: 'preparing', completed: 0, total: 1 }
  running.value = true; emit('running', true)
  try {
    const preview = await organizeScript(JSON.parse(sourceSnapshot.value), instructions.value, locale.value, signal, value => {
      if (current === generation && !signal.aborted) progress.value = value
    })
    if (current === generation && !signal.aborted) result.value = preview
  } catch (cause) {
    if (current === generation && !signal.aborted) error.value = errorMessage(cause)
  } finally {
    if (current === generation) { running.value = false; controller = null; emit('running', false) }
  }
}
function cancel() {
  ++generation
  controller?.abort(); controller = null
  running.value = false; cancelled.value = true; result.value = null
  emit('running', false)
}
function apply() {
  if (!result.value || stale.value || props.disabled) return
  const preview = result.value
  result.value = null
  emit('apply', preview)
}
watch(snapshot, () => { if (running.value) cancel() })
onBeforeUnmount(() => { ++generation; controller?.abort() })
</script>

<template>
  <section class="script-ai" data-testid="script-ai-organizer">
    <h3>{{ copy.title }}</h3>
    <p class="script-ai-cost">{{ copy.intro }}</p>
    <label class="script-ai-instructions">{{ copy.instructions }}<textarea v-model="instructions" rows="2" maxlength="2000" :placeholder="copy.placeholder" :disabled="running || disabled" /></label>
    <label class="script-ai-consent"><input v-model="consent" type="checkbox" data-testid="script-ai-consent" :disabled="running || disabled">{{ copy.consent }}</label>
    <div class="script-ai-actions">
      <button v-if="!running" type="button" class="primary" data-testid="script-ai-start" :disabled="!consent || disabled" @click="start">{{ copy.start }}</button>
      <button v-else type="button" data-testid="script-ai-cancel" @click="cancel">{{ copy.cancel }}</button>
    </div>
    <div v-if="running" class="script-ai-progress" role="status" aria-live="polite">
      <p>{{ stageText }}</p>
      <progress :value="progress.completed" :max="progress.total" :aria-label="copy.progress" />
      <span>{{ progress.completed }} / {{ progress.total }} · {{ Math.floor(progress.completed / progress.total * 100) }}%</span>
    </div>
    <p v-if="cancelled" role="status">{{ copy.cancelled }}</p>
    <p v-if="error" class="error-banner" role="alert">{{ copy.failed }} {{ error }}</p>
    <div v-if="result" class="script-ai-result" data-testid="script-ai-result">
      <p>{{ stale ? copy.stale : copy.ready }}</p>
      <p>{{ copy.scenes }}：{{ scenes.length }} · {{ copy.resources }}：{{ resourceCount }}</p>
      <details><summary>{{ copy.result }}</summary><ul><li v-for="scene in scenes" :key="scene.id"><strong>{{ scene.name }}</strong><p>{{ scene.description }}</p></li></ul></details>
      <p class="muted">{{ copy.source }}</p>
      <div class="script-ai-actions"><button type="button" class="primary" data-testid="script-ai-apply" :disabled="stale || disabled" @click="apply">{{ copy.apply }}</button><button type="button" @click="result = null">{{ copy.discard }}</button></div>
    </div>
  </section>
</template>

<style scoped>
.script-ai { display: grid; gap: .65rem; padding: .9rem; border: 1px solid color-mix(in srgb, var(--df-interactive) 40%, var(--df-border-soft)); border-radius: var(--df-radius-md); background: var(--df-surface-2); min-width: 0; }
.script-ai h3, .script-ai p { margin: 0; }
.script-ai-cost { color: var(--df-text-secondary); font-size: .86rem; line-height: 1.6; }
.script-ai-instructions { display: grid; gap: .35rem; margin: 0; }
.script-ai-instructions textarea { box-sizing: border-box; width: 100%; min-width: 0; }
.script-ai-consent { display: flex; align-items: flex-start; gap: .5rem; margin: 0; font-size: .86rem; }
.script-ai-consent input { width: auto; flex: 0 0 auto; margin-top: .2rem; }
.script-ai-actions { display: flex; flex-wrap: wrap; gap: .5rem; }
.script-ai-progress { display: grid; gap: .35rem; }
.script-ai-progress p::before { content: ''; display: inline-block; width: 7px; height: 7px; margin-right: .45rem; border-radius: 50%; background: var(--df-interactive); animation: ai-working 1.4s ease-in-out infinite; }
.script-ai-progress progress { width: 100%; height: 12px; appearance: none; border: 0; border-radius: 12px; overflow: hidden; background: var(--df-control-bg); accent-color: var(--df-interactive); }
.script-ai-progress progress::-webkit-progress-bar { background: var(--df-control-bg); }
.script-ai-progress progress::-webkit-progress-value { background: var(--df-interactive); border-radius: 12px; }
.script-ai-progress progress::-moz-progress-bar { background: var(--df-interactive); border-radius: 12px; }
.script-ai-progress span { color: var(--df-text-muted); font-size: .8rem; }
.script-ai-result { display: grid; gap: .6rem; padding-top: .7rem; border-top: 1px solid var(--df-border-soft); }
.script-ai-result ul { display: grid; gap: .7rem; padding-left: 1.3rem; max-height: 300px; overflow-y: auto; }
.script-ai-result li p { white-space: pre-wrap; overflow-wrap: anywhere; font-size: .86rem; color: var(--df-text-secondary); }
@media (max-width: 620px) { .script-ai-actions > button { width: 100%; } }
@keyframes ai-working { 50% { opacity: .35; } }
@media (prefers-reduced-motion: reduce) { .script-ai-progress p::before { animation: none; } }
</style>
