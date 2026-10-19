<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useLocale } from '@/composables/useLocale'
import type { ScriptDraft, ScriptRef } from './scriptTypes'
import { importCopy } from './importCopy'
import { narrativeRuntimeId } from './compatibility'
const props = defineProps<{ draft: ScriptDraft }>()
const emit = defineEmits<{ prose: [index: number] }>()
const draft = computed(() => props.draft)
const { locale, t } = useLocale()
const copy = computed(() => importCopy(locale.value))
const selections = reactive<Record<number, { resource: string; node: string }>>({})
const choice = (index: number) => selections[index] ||= { resource: '', node: '' }
const resources = computed(() => Object.values(props.draft.files).filter(value => value && typeof value === 'object' && ['npc', 'scene', 'map_location', 'encounter_catalog'].includes(value.kind)))
const matching = (reference: ScriptRef) => resources.value.filter(value => value.kind === reference.kind
  && !(value.kind === 'encounter_catalog' && (props.draft.files['manifest.json'].required_runtime as { id?: string } | undefined)?.id === narrativeRuntimeId))
function map(index: number) {
  const selected = choice(index), reference = props.draft.references[index]
  if (!reference || !selected.resource || !selected.node) return
  const resource = matching(reference).find(value => value.id === selected.resource), node = props.draft.files['adventure.json'].nodes.find(node => node.id === selected.node)
  if (!resource || !node) return
  draft.value.references[index] = { source_kind: 'adventure', source_id: draft.value.directory_id, kind: resource.kind, id: resource.id }
  const ref = `${resource.kind}:${resource.id}`
  if (resource.kind === 'npc') node.npc_refs = [...new Set([...(Array.isArray(node.npc_refs) ? node.npc_refs : []), ref])]
  if (resource.kind === 'scene') node.scene_ref = ref
  if (resource.kind === 'encounter_catalog') node.encounter_ref = ref
  // Map locations stay reviewed references; native scene JSON owns their links.
}
</script>
<template>
  <section v-if="draft.references.length" class="reference-map"><header><div><h3>{{ copy.refs }}</h3><p>{{ copy.hint }}</p></div><span class="reference-map-count">{{ draft.references.length }}</span></header>
    <div v-for="(reference, index) in draft.references" :key="index" class="reference-row">
      <strong class="reference-source">{{ reference.kind }}:{{ reference.id }}</strong>
      <select v-model="choice(index).resource"><option value="">{{ copy.pick }}</option><option v-for="resource in matching(reference)" :key="resource.id" :value="resource.id">{{ resource.name || resource.id }}</option></select>
      <label>{{ copy.node }}<select v-model="choice(index).node"><option value="">{{ copy.pick }}</option><option v-for="node in draft.files['adventure.json'].nodes" :key="node.id" :value="node.id">{{ node.name || node.id }}</option></select></label>
      <button :disabled="!choice(index).resource || !choice(index).node" @click="map(index)">{{ copy.map }}</button>
      <div class="reference-actions"><button data-testid="script-reference-prose" @click="emit('prose', index)">{{ t('scriptKeepProse') }}</button></div>
    </div>
  </section>
</template>
<style scoped>
.reference-map { display: grid; gap: .7rem; min-width: 0; padding: .9rem; border: 1px solid color-mix(in srgb, var(--df-accent) 26%, var(--df-border-soft)); border-radius: var(--df-radius-md); background: var(--df-surface-2); }
header { display: flex; align-items: start; justify-content: space-between; gap: .75rem; }
h3 { margin: 0; color: var(--df-accent-strong); font-size: 1rem; }
p { margin: .3rem 0 0; color: var(--df-text-muted); font-size: .82rem; line-height: 1.5; }
.reference-map-count { display: inline-grid; min-width: 1.7rem; min-height: 1.7rem; place-items: center; border: 1px solid var(--df-border-soft); border-radius: 999px; color: var(--df-accent-strong); background: var(--df-surface-1); font-size: .75rem; }
.reference-row { display: grid; gap: .65rem; min-width: 0; padding: .8rem; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); background: var(--df-surface-1); }
.reference-source { color: var(--df-text); font-size: .88rem; overflow-wrap: anywhere; }
.reference-row label { display: grid; gap: .35rem; margin: 0; }
.reference-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .5rem; }
select { width: 100%; min-width: 0; }
</style>
