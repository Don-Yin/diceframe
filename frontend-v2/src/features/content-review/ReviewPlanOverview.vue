<script setup lang="ts">
import { computed } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { reviewCopy } from './copy'
import { reviewRefLabel, type ReviewPlan } from './types'
import { textReviewCopy } from './textCopy'
const props = defineProps<{ plan?: ReviewPlan }>()
const { locale } = useLocale()
const copy = computed(() => reviewCopy(locale.value))
const actionLabel = (action?: string) => action === 'update' ? copy.value.update : action === 'skip' ? copy.value.skip : copy.value.create
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
function title(index: number) {
  const draft = props.plan?.drafts?.[index]
  const payload = draft?.payload || {}
  const fragment = object(payload.fragment)
  const graph = object(object(payload.files)['adventure.json'])
  const name = fragment.name || payload.name || payload.character_name || graph.name || draft?.ref.id || ''
  const kind = draft?.ref.kind
  const labels = textReviewCopy(locale.value)
  const target = kind === 'world' || kind === 'lorebook' || kind === 'character_template' || kind === 'adventure' ? labels[kind] : kind
  return `${String(name)}${target ? ` · ${target}` : ''}`
}
</script>
<template>
  <section v-if="plan" class="review-plan" data-testid="review-plan">
    <h3>{{ copy.title }}</h3>
    <ol v-if="plan.operations?.length" class="review-plan-operations">
      <li v-for="(operation, index) in plan.operations" :key="index">
        <span class="review-plan-action">{{ actionLabel(operation.action) }}</span><span class="review-plan-separator">—</span><strong>{{ title(index) || reviewRefLabel(operation.draft_ref) }}</strong>
        <span v-if="operation.existing_ref"> ({{ copy.existing }})</span>
      </li>
    </ol>
    <details v-for="(draft, index) in plan.drafts || []" :key="index" class="review-plan-detail">
      <summary>{{ copy.details }} — {{ title(index) }}</summary>
      <p>{{ reviewRefLabel(draft.ref) }}</p>
      <pre>{{ JSON.stringify({ payload: draft.payload, provenance: draft.provenance }, null, 2) }}</pre>
      <h4 v-if="draft.references?.length">{{ copy.references }}</h4>
      <ul><li v-for="reference in draft.references || []" :key="reviewRefLabel(reference)">{{ reviewRefLabel(reference) }}</li></ul>
    </details>
    <div v-if="plan.unresolved_references?.length" class="error-banner" role="alert">
      <strong>{{ copy.unresolved }}</strong>
      <ul><li v-for="reference in plan.unresolved_references" :key="reviewRefLabel(reference)">{{ reviewRefLabel(reference) }}</li></ul>
    </div>
  </section>
</template>
<style scoped>
.review-plan { display: grid; gap: .7rem; min-width: 0; overflow-wrap: anywhere; padding: .9rem; border: 1px solid color-mix(in srgb, var(--df-accent) 26%, var(--df-border-soft)); border-radius: var(--df-radius-md); background: var(--df-surface-2); }
h3 { margin: 0; color: var(--df-accent-strong); font-size: 1rem; }
h4, ol, ul { margin: 0; }
.review-plan-operations { display: grid; gap: .45rem; padding-left: 1.35rem; }
.review-plan-operations li { padding: .55rem .65rem; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); background: var(--df-surface-1); color: var(--df-text-secondary); }
.review-plan-action { display: inline-flex; margin-right: .35rem; padding: .2rem .45rem; border-radius: 999px; color: var(--df-on-accent); background: var(--df-interactive); font-size: .72rem; font-weight: 750; }
.review-plan-separator { margin-right: .35rem; color: var(--df-text-muted); }
.review-plan-detail { border-top: 1px solid var(--df-border-soft); padding-top: .6rem; }
.review-plan-detail summary { color: var(--df-text-secondary); cursor: pointer; font-weight: 650; }
.review-plan-detail p { margin: .5rem 0; color: var(--df-text-muted); font-size: .82rem; }
pre { margin: .5rem 0 0; padding: .7rem; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 18rem; overflow: auto; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); background: var(--df-control-bg); color: var(--df-text-secondary); }
</style>
