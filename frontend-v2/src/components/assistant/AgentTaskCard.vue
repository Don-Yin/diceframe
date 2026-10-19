<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { i18n } from '@/i18n'
import { assistantCopy, assistantKindLabel } from '@/features/assistant/copy'
import type { AssistantDraft } from '@/composables/useAssistant'

type DraftItem = { id?: string; name?: string; text?: string; target?: string; references?: unknown[]; [key: string]: unknown }

const props = withDefaults(defineProps<{
  draft: AssistantDraft
  busy?: boolean
  streaming?: boolean
}>(), { busy: false, streaming: false })
const emit = defineEmits<{
  edit: [draftId: string]
  review: [payload: { draft_id: string; draft: Record<string, unknown> }]
  save: [draftId: string]
}>()
const copy = computed(() => assistantCopy(String(i18n.global.locale.value)))
const items = ref<DraftItem[]>([])
const originalItems = ref('[]')

function draftRecord(): Record<string, unknown> {
  const review = props.draft.review && typeof props.draft.review === 'object' ? props.draft.review as Record<string, unknown> : {}
  return review.draft && typeof review.draft === 'object' && !Array.isArray(review.draft) ? review.draft as Record<string, unknown> : {}
}
function cloneItems(): DraftItem[] {
  const value = draftRecord().items
  if (!Array.isArray(value)) return []
  return value.filter(item => item && typeof item === 'object').map(item => ({ ...(item as DraftItem), references: Array.isArray((item as DraftItem).references) ? [...(item as DraftItem).references!] : (item as DraftItem).references }))
}
function sync() {
  items.value = cloneItems()
  originalItems.value = JSON.stringify(items.value)
}
sync()
watch(() => props.draft, sync, { deep: true })

const reviewRecord = computed(() => props.draft.review as Record<string, unknown>)
const blockers = computed(() => {
  const value = reviewRecord.value.blockers
  return Array.isArray(value) ? value.map(item => typeof item === 'string' ? item : JSON.stringify(item)).filter(Boolean) : []
})
const edited = computed(() => JSON.stringify(items.value) !== originalItems.value)
const reviewed = computed(() => reviewRecord.value.ok === true && blockers.value.length === 0)
const disabled = computed(() => props.busy || props.streaming)
const reviewDisabled = computed(() => disabled.value || !items.value.length || items.value.some(item => !String(item.name || '').trim() || !String(item.text || '').trim() || !String(item.target || '').trim()))
const saveDisabled = computed(() => disabled.value || edited.value || !reviewed.value)
function editedDraft(): Record<string, unknown> {
  const draft: Record<string, unknown> = { ...draftRecord(), items: items.value.map(item => ({ ...item })) }
  delete draft.name
  delete draft.text
  delete draft.target
  return draft
}
function review() {
  if (reviewDisabled.value) return
  emit('review', { draft_id: props.draft.draft_id, draft: editedDraft() })
}
function onItemEdit() { emit('edit', props.draft.draft_id) }
function save() {
  if (saveDisabled.value) return
  emit('save', props.draft.draft_id)
}
</script>

<template>
  <article class="agent-task-card" :data-agent-draft="draft.draft_id" :data-agent-edited="edited ? 'true' : undefined">
    <header><strong>{{ assistantKindLabel(String(i18n.global.locale.value), draft.review.kind) }}</strong><span v-if="edited" class="agent-task-edited">{{ copy.edited }}</span></header>
    <div v-for="(item, index) in items" :key="String(item.id || index)" class="agent-task-item">
      <div class="agent-task-item-heading"><strong>{{ item.name || `${copy.name} ${index + 1}` }}</strong></div>
      <label><span>{{ copy.name }}</span><input v-model="item.name" :disabled="disabled" :data-agent-item-name="index" @input="onItemEdit" /></label>
      <label><span>{{ copy.text }}</span><textarea v-model="item.text" :disabled="disabled" rows="3" :data-agent-item-text="index" @input="onItemEdit" /></label>
      <label><span>{{ copy.target }}</span><select v-model="item.target" :disabled="disabled" :data-agent-item-target="index" @change="onItemEdit"><option value="world">{{ copy.targetWorld }}</option><option value="lorebook">{{ copy.targetLorebook }}</option><option value="character_template">{{ copy.targetCharacter }}</option><option value="adventure">{{ copy.targetAdventure }}</option></select></label>
      <details v-if="item.references?.length"><summary>{{ copy.details }}</summary><pre>{{ JSON.stringify(item.references, null, 2) }}</pre></details>
    </div>
    <ul v-if="blockers.length" class="agent-task-blockers"><li v-for="blocker in blockers" :key="blocker">{{ blocker }}</li></ul>
    <footer><button type="button" data-agent-review :disabled="reviewDisabled" @click="review">{{ copy.review }}</button><button type="button" data-agent-save :disabled="saveDisabled" @click="save">{{ copy.save }}</button></footer>
  </article>
</template>

<style scoped>
.agent-task-card { display: grid; gap: .65rem; padding: .8rem; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-md); background: var(--df-surface-2); }
header, footer, .agent-task-item-heading { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
header span, small { color: var(--df-text-muted); font-size: .72rem; }
.agent-task-item { display: grid; gap: .5rem; padding: .65rem; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); background: var(--df-surface-1); }
label { display: grid; gap: .2rem; color: var(--df-text-muted); font-size: .75rem; }
label em { color: var(--df-accent-strong); font-style: normal; }
input, textarea, select { width: 100%; box-sizing: border-box; padding: .45rem .55rem; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); color: var(--df-text); background: var(--df-control-bg); font: inherit; }
button { padding: .4rem .65rem; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); color: var(--df-text-secondary); background: var(--df-control-bg); cursor: pointer; }
button:first-child { color: var(--df-on-accent); background: var(--df-interactive); }
button:disabled { cursor: not-allowed; opacity: .55; }
.agent-task-edited { color: var(--df-accent-strong); font-size: .72rem; }
.agent-task-blockers { margin: 0; padding-left: 1.2rem; color: var(--df-danger-strong); font-size: .78rem; }
pre { max-height: 10rem; overflow: auto; white-space: pre-wrap; }
</style>
