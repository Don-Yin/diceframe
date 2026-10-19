<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { errorMessage } from '@/api/client'
import { resourceApi, type ResourceSelector, type ForkDraft, type ForkReview } from '@/api/moduleResources'
import Modal from '@/components/ui/Modal.vue'
import { useLocale } from '@/composables/useLocale'
import ReviewPlanOverview from '@/features/content-review/ReviewPlanOverview.vue'
import NativeCopyEditor from './NativeCopyEditor.vue'
import { resourceCopy } from './copy'
const props = defineProps<{ moduleId: string; selector: ResourceSelector }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const { locale } = useLocale()
const copy = computed(() => resourceCopy(locale.value))
const draft = ref<ForkDraft | null>(null), preview = ref<ForkReview | null>(null)
const checked = ref(''), reviewed = ref(false), busy = ref(false), error = ref(''), started = ref(false), saved = ref(false)
const pending = ref(false)
const snapshot = computed(() => JSON.stringify(draft.value))
const valid = computed(() => !pending.value && checked.value === snapshot.value && !!preview.value && !preview.value.blockers.length)
const targetLabel = computed(() => copy.value[preview.value?.target as 'world'] || preview.value?.target)
async function review() {
  if (busy.value || started.value) return
  busy.value = true; reviewed.value = false; error.value = ''
  try {
    const result = draft.value ? await resourceApi.review(props.moduleId, draft.value) : await resourceApi.preview(props.moduleId, props.selector, locale.value)
    if (!result.ok) throw new Error('Review failed')
    draft.value = result.draft; preview.value = result; checked.value = snapshot.value
  } catch (cause) { checked.value = ''; error.value = errorMessage(cause) }
  finally { busy.value = false }
}
async function save() {
  if (!valid.value || !reviewed.value || busy.value || started.value || !preview.value || !draft.value) return
  started.value = true; busy.value = true; error.value = ''
  try { const result = await resourceApi.commit(props.moduleId, draft.value, preview.value.plan_digest); if (!result.ok) throw new Error(result.error || 'Save failed'); saved.value = true; emit('saved') }
  catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}
onMounted(review)
</script>
<template>
  <Modal :title="copy.copy" dialog-class="module-fork-dialog" @close="emit('close')">
    <div class="fork-dialog">
      <p>{{ copy.hint }}</p>
      <p v-if="error" role="alert" class="error-text">{{ error }}</p>
      <template v-if="draft && preview">
        <p>{{ copy.target }}: {{ targetLabel }}</p>
        <fieldset :disabled="busy || started"><NativeCopyEditor :payload="draft.payload" :target="preview.target" @replace="draft.payload = $event" @pending="pending = $event" /></fieldset>
        <ReviewPlanOverview :plan="preview.commit_plan" />
        <p v-if="checked !== snapshot || pending" role="status">{{ copy.changed }}</p>
        <ul v-if="checked === snapshot && preview.blockers.length" role="alert"><li v-for="blocker in preview.blockers" :key="blocker">{{ blocker }}</li></ul>
        <button data-testid="fork-review" :disabled="busy || started || pending" @click="review">{{ copy.validate }}</button>
        <label class="reviewed"><input v-model="reviewed" type="checkbox" :disabled="busy || started" data-testid="fork-reviewed">{{ copy.reviewed }}</label>
        <p v-if="started && !busy && !saved" role="status">{{ copy.uncertain }}</p>
        <p v-if="saved" role="status" data-testid="fork-saved">{{ copy.saved }}</p>
        <button data-testid="fork-save" :disabled="!valid || !reviewed || busy || started" @click="save">{{ copy.save }}</button>
      </template>
    </div>
  </Modal>
</template>
<style scoped>
.fork-dialog { display: grid; gap: .8rem; min-width: 0; }
fieldset { border: none; padding: 0; min-width: 0; }
.reviewed { display: flex; align-items: center; gap: .5rem; }
</style>
