<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { errorMessage } from '@/api/client'
import { resourceApi, type ModuleResource, type ResourceSnapshot } from '@/api/moduleResources'
import { useLocale } from '@/composables/useLocale'
import ModuleForkDialog from './ModuleForkDialog.vue'
import { resourceCopy } from './copy'
import { contentKindLabel } from '../copy'
const props = defineProps<{ moduleId: string }>()
const { locale } = useLocale()
const copy = computed(() => resourceCopy(locale.value))
const resources = ref<ModuleResource[]>([]), selected = ref<ResourceSnapshot | null>(null)
const query = ref(''), kind = ref(''), error = ref(''), busy = ref(false), imageUrl = ref(''), fork = ref(false)
let sequence = 0, readSequence = 0
const kinds = computed(() => [...new Set(resources.value.map(row => row.kind))].sort())
const rows = computed(() => resources.value.filter(row => (!kind.value || row.kind === kind.value) && `${row.title} ${row.description} ${row.kind} ${contentKindLabel(row.kind, locale.value)}`.toLowerCase().includes(query.value.toLowerCase())))
const imageKinds = ['portrait_asset', 'scene_image_asset', 'map_icon', 'map_scene']
function clearImage() { if (imageUrl.value) URL.revokeObjectURL(imageUrl.value); imageUrl.value = '' }
async function load() {
  const current = ++sequence; ++readSequence; clearImage(); selected.value = null; fork.value = false; resources.value = []; error.value = ''; kind.value = ''; query.value = ''; busy.value = true
  try { const result = await resourceApi.list(props.moduleId); if (current === sequence) resources.value = result.resources }
  catch (cause) { if (current === sequence) error.value = errorMessage(cause) }
  finally { if (current === sequence) busy.value = false }
}
async function open(row: ModuleResource) {
  const current = ++readSequence; const id = props.moduleId; clearImage(); selected.value = null; error.value = ''; busy.value = true
  try {
    const result = await resourceApi.read(id, row.selector, locale.value)
    if (current !== readSequence) return
    selected.value = result.resource
    if (imageKinds.includes(row.kind)) {
      const response = await resourceApi.asset(id, row.selector); const blob = await response.blob()
      if (current === readSequence) imageUrl.value = URL.createObjectURL(blob)
    }
  } catch (cause) { if (current === readSequence) error.value = errorMessage(cause) }
  finally { if (current === readSequence) busy.value = false }
}
watch(() => [props.moduleId, locale.value], load, { immediate: true })
onBeforeUnmount(() => { ++sequence; ++readSequence; clearImage() })
</script>
<template>
  <section class="resource-browser">
    <h2>{{ copy.title }}</h2><p>{{ copy.hint }}</p>
    <div class="resource-filter"><input v-model="query" data-testid="resource-search" :placeholder="copy.search" :aria-label="copy.search"><select v-model="kind" :aria-label="copy.all"><option value="">{{ copy.all }}</option><option v-for="value in kinds" :key="value" :value="value">{{ contentKindLabel(value, locale) }}</option></select></div>
    <p v-if="error" role="alert" class="error-text">{{ error }}</p>
    <p v-if="!busy && !rows.length">{{ copy.empty }}</p>
    <ul class="resource-list"><li v-for="row in rows" :key="JSON.stringify(row.selector)"><div><strong>{{ row.title }}</strong><small>{{ contentKindLabel(row.kind, locale) }}</small><p v-if="row.description">{{ row.description }}</p></div><button data-testid="resource-open" @click="open(row)">{{ copy.open }}</button></li></ul>
    <article v-if="selected" class="resource-details">
      <h3>{{ selected.title }}</h3><p>{{ copy.readonly }}</p>
      <img v-if="imageUrl" :src="imageUrl" :alt="copy.image">
      <button v-if="selected.fork_target" data-testid="resource-fork" @click="fork = true">{{ copy.fork }}</button><p v-else>{{ copy.noFork }}</p>
      <details open><summary>{{ copy.native }}</summary><pre>{{ JSON.stringify(selected.payload, null, 2) }}</pre></details>
    </article>
    <ModuleForkDialog v-if="fork && selected" :key="JSON.stringify(selected.selector)" :module-id="moduleId" :selector="selected.selector" @close="fork = false" />
  </section>
</template>
<style scoped>
.resource-browser { margin-top: 1.5rem; min-width: 0; }
.resource-filter { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; }
.resource-filter input { flex: 1 1 16rem; min-width: 0; }
.resource-filter select { flex: 0 1 14rem; min-width: 10rem; }
.resource-list { list-style: none; display: grid; gap: .6rem; padding: 0; }
.resource-list li { display: flex; flex-wrap: wrap; justify-content: space-between; gap: .7rem; padding: .7rem; border: 1px solid var(--df-border-soft); border-radius: .5rem; }
.resource-list li div { min-width: 0; flex: 1; overflow-wrap: anywhere; } small { display: block; color: var(--df-text-muted); }
.resource-details { padding: .8rem; border: 1px solid var(--df-border-soft); border-radius: .5rem; min-width: 0; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 32rem; overflow-y: auto; } img { display: block; max-width: 100%; max-height: 26rem; margin-bottom: .7rem; }
@media (max-width: 480px) {
  .resource-filter input, .resource-filter select { flex: 1 1 100%; width: 100%; min-height: 44px; }
}
</style>
