<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useLocale } from '@/composables/useLocale'
import type { NativePayload } from '@/api/moduleResources'
import { importCopy } from './importCopy'
import { narrativeRuntimeId } from './compatibility'
const props = defineProps<{ files: Record<string, unknown> }>()
const emit = defineEmits<{ pending: [value: boolean] }>()
// The owning editor passes a mutable draft, matching AdventureGraphForm.
const files = computed(() => props.files)
const { locale, t } = useLocale()
const copy = computed(() => importCopy(locale.value))
const object = (value: unknown): NativePayload => value && typeof value === 'object' && !Array.isArray(value) ? value as NativePayload : {}
const allKinds = ['npc', 'item', 'scene', 'map_location', 'encounter_catalog'] as const
const narrativeOnly = computed(() => object(object(props.files['manifest.json']).required_runtime).id === narrativeRuntimeId)
const kinds = computed(() => allKinds.filter(value => !narrativeOnly.value || value !== 'encounter_catalog'))
const kind = ref<typeof allKinds[number]>('npc'), selected = ref(''), raw = ref(''), error = ref('')
const resources = computed(() => Object.entries(props.files).filter(([path, value]) => path.startsWith('content/') && !!object(value).kind))
const current = computed(() => object(props.files[selected.value]))
const name = computed({ get: () => String(current.value.name || ''), set: value => { current.value.name = value } })
const description = computed({ get: () => String(current.value.description || ''), set: value => { current.value.description = value } })
watch(current, value => { raw.value = JSON.stringify(value, null, 2); error.value = '' }, { deep: true, immediate: true })
watch(() => !!selected.value && raw.value !== JSON.stringify(current.value, null, 2), value => emit('pending', value), { immediate: true })
function add() {
  const id = 'r_' + crypto.randomUUID().replaceAll('-', '')
  const path = `content/${kind.value}/${id}.json`
  files.value[path] = { schema_version: 1, kind: kind.value, id, source_ref: String(object(files.value['adventure.json']).source_ref || object(files.value['manifest.json']).adventure_id), automation_level: 'reference', visibility: 'gm', name: copy.value[kind.value], description: '', ...(kind.value === 'encounter_catalog' ? { presets: [] } : {}) }
  selected.value = path
}
function apply() {
  try {
    const value: unknown = JSON.parse(raw.value), row = object(value)
    if (!value || Array.isArray(value) || row.kind !== current.value.kind || row.id !== current.value.id) throw new Error(copy.value.invalid)
    files.value[selected.value] = row; error.value = ''
  } catch (cause) { error.value = cause instanceof Error ? cause.message : copy.value.invalid }
}
function remove(path: string) { delete files.value[path]; if (selected.value === path) selected.value = '' }
</script>
<template>
  <section class="adventure-resources">
    <h3>{{ copy.resources }}</h3><p>{{ copy.reference }}</p>
    <div class="resource-actions"><select v-model="kind" data-testid="resource-kind"><option v-for="value in kinds" :key="value" :value="value">{{ copy[value] }}</option></select><button data-testid="resource-add" @click="add">{{ copy.add }}</button></div>
    <ul><li v-for="[path, value] in resources" :key="path"><strong>{{ object(value).name || object(value).id }}</strong><small>{{ object(value).kind }}</small><button data-testid="resource-edit" @click="selected = path">{{ copy.edit }}</button><button @click="remove(path)">{{ copy.remove }}</button></li></ul>
    <div v-if="selected && files[selected]" class="resource-editor">
      <label>{{ t('name') }}<input v-model="name" data-testid="resource-name"></label>
      <label>{{ t('description') }}<textarea v-model="description" rows="5" data-testid="resource-description" /></label>
      <details><summary>{{ copy.native }}</summary><textarea v-model="raw" rows="12" data-testid="resource-json" :aria-label="copy.native" /><button data-testid="resource-json-apply" @click="apply">{{ copy.apply }}</button></details>
      <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    </div>
  </section>
</template>
<style scoped>
.adventure-resources, .resource-editor, label { display: grid; gap: .6rem; min-width: 0; }
.resource-actions, li { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; } ul { list-style: none; padding: 0; display: grid; gap: .5rem; } li strong { flex: 1; overflow-wrap: anywhere; min-width: 0; }
input, textarea, select { width: 100%; box-sizing: border-box; min-width: 0; } .resource-actions select { width: auto; flex: 1; } textarea { resize: vertical; }
</style>
