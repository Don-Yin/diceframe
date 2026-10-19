<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import Modal from '@/components/ui/Modal.vue'
import { useLocale } from '@/composables/useLocale'
import ReviewPlanOverview from './ReviewPlanOverview.vue'
import { textReviewCopy, textForkCopy } from './textCopy'
import type { ReviewPlan, ReviewRef } from './types'
type Target = 'world' | 'lorebook' | 'character_template' | 'adventure'
type Draft = { source_id: string; copy_id?: string; filename: string; language: string; items: Array<{ id: string; name: string; text: string; target: Target; references: ReviewRef[] }> }
type Preview = { ok: boolean; draft: Draft; blockers: string[]; plan_digest: string; commit_plan: ReviewPlan }
type Result = { ok: boolean; partial?: boolean; recovery_required?: boolean; error?: string; results: Array<{ id: string; target: Target; ok: boolean; error?: string }> }
const emit = defineEmits<{ close: []; saved: [] }>()
const { locale } = useLocale()
const copy = computed(() => textReviewCopy(locale.value))
const targets: Target[] = ['world', 'lorebook', 'character_template', 'adventure']
const source = ref(''), filename = ref('notes.txt'), error = ref('')
const draft = ref<Draft | null>(null), preview = ref<Preview | null>(null), result = ref<Result | null>(null)
const busy = ref(false), reviewed = ref(false), started = ref(false)
const checkedSnapshot = ref('')
const current = computed(() => JSON.stringify(draft.value))
const valid = computed(() => preview.value && checkedSnapshot.value === current.value && !preview.value.blockers.length)
const canSave = computed(() => reviewed.value && valid.value && !result.value?.ok && !result.value?.recovery_required && !busy.value)
const requestBody = ref('')
async function selectFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || started.value) return
  if (file.size > 512 * 1024) { error.value = 'Maximum file size: 512 KiB'; return }
  source.value = await file.text(); filename.value = file.name
  draft.value = null; preview.value = null; reviewed.value = false
}
async function review(validate = false) {
  if (started.value) return
  busy.value = true; error.value = ''; reviewed.value = false
  try {
    const checked = await api<Preview>(`/content-review/${validate ? 'review' : 'preview'}`, {
      method: 'POST', body: JSON.stringify(validate ? draft.value : { text: source.value, filename: filename.value, language: locale.value }),
    })
    if (!checked.ok) throw new Error('Content review failed')
    draft.value = checked.draft; preview.value = checked; checkedSnapshot.value = current.value
  } catch (cause) { checkedSnapshot.value = ''; error.value = errorMessage(cause) }
  finally { busy.value = false }
}
async function save() {
  if (!canSave.value || !preview.value || !draft.value) return
  if (!started.value) requestBody.value = JSON.stringify({ ...draft.value, reviewed: true, plan_digest: preview.value.plan_digest })
  started.value = true; busy.value = true; error.value = ''
  try {
    result.value = await api<Result>('/content-review/commit', { method: 'POST', body: requestBody.value })
    if (result.value.error) error.value = result.value.error
    if (result.value.ok) emit('saved')
  } catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}
async function fork() {
  if (!draft.value || started.value || busy.value) return
  draft.value.copy_id = crypto.randomUUID().replaceAll('-', '')
  await review(true)
}
</script>
<template>
  <Modal :title="copy.title" dialog-class="content-text-dialog" @close="emit('close')">
    <section class="text-review">
      <p>{{ copy.hint }}</p>
      <label>{{ copy.source }}<input type="file" accept=".md,.txt" :disabled="started || busy" @change="selectFile"></label>
      <textarea v-model="source" data-testid="text-source" :disabled="started || busy" :aria-label="copy.source" rows="6" />
      <button data-testid="text-preview" :disabled="!source.trim() || started || busy" @click="review()">{{ copy.preview }}</button>
      <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
      <template v-if="draft && preview">
        <fieldset v-for="(item, index) in draft.items" :key="item.id" :disabled="started || busy" class="fragment">
          <legend>{{ index + 1 }} · {{ item.name }}</legend>
          <label>{{ copy.target }}<select v-model="item.target" data-testid="fragment-target"><option v-for="target in targets" :key="target" :value="target">{{ copy[target] }}</option></select></label>
          <label>{{ copy.name }}<input v-model="item.name" data-testid="fragment-name"></label>
          <label>{{ copy.text }}<textarea v-model="item.text" data-testid="fragment-text" rows="5" :disabled="started || busy" /></label>
          <button :disabled="draft.items.length <= 1" @click="draft.items.splice(index, 1)">{{ copy.remove }}</button>
        </fieldset>
        <ReviewPlanOverview :plan="preview.commit_plan" />
        <p v-if="checkedSnapshot !== current" role="status">{{ copy.changed }}</p>
        <ul v-if="checkedSnapshot === current && preview.blockers.length" class="error-banner" role="alert"><li v-for="blocker in preview.blockers" :key="blocker">{{ blocker }}</li></ul>
        <button v-if="preview.blockers.some(blocker => blocker.includes('already exists'))" :disabled="started || busy" @click="fork">{{ textForkCopy(locale) }}</button>
        <button data-testid="text-validate" :disabled="started || busy" @click="review(true)">{{ copy.validate }}</button>
        <label class="reviewed"><input v-model="reviewed" type="checkbox" data-testid="text-reviewed" :disabled="started || busy">{{ copy.reviewed }}</label>
        <p v-if="started && !result?.ok" role="status">{{ copy.partial }}</p>
        <ul v-if="result" data-testid="text-results"><li v-for="row in result.results" :key="row.id">{{ draft.items.find(item => item.id === row.id)?.name }} · {{ row.ok ? copy.saved : copy.failed }} {{ row.error }}</li></ul>
        <p v-if="result?.ok" role="status">{{ copy.finished }}</p>
        <button class="primary" data-testid="text-commit" :disabled="!canSave" @click="save">{{ started ? copy.retry : copy.commit }}</button>
      </template>
    </section>
  </Modal>
</template>
<style scoped>
.text-review, .fragment, label { display: grid; gap: .65rem; min-width: 0; }
.fragment { border: 1px solid var(--border-color); padding: .8rem; border-radius: .5rem; }
input, select, textarea { width: 100%; min-width: 0; box-sizing: border-box; }
textarea { resize: vertical; }
.reviewed { display: flex; align-items: center; }
.reviewed input { width: auto; }
</style>
