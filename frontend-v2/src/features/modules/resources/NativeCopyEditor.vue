<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { NativePayload } from '@/api/moduleResources'
import { useLocale } from '@/composables/useLocale'
import AdventureGraphForm from '@/features/adventures/AdventureGraphForm.vue'
import type { ScriptFiles } from '@/features/adventures/scriptTypes'
import { resourceCopy } from './copy'
const props = defineProps<{ payload: NativePayload; target: string }>()
const emit = defineEmits<{ replace: [value: NativePayload]; pending: [value: boolean] }>()
const { locale } = useLocale()
const copy = computed(() => resourceCopy(locale.value))
const object = (value: unknown): NativePayload => value && typeof value === 'object' && !Array.isArray(value) ? value as NativePayload : {}
const core = computed(() => props.target === 'world' ? object(props.payload.definition)
  : props.target === 'lorebook' ? object(object(props.payload.data).lorebook)
  : props.target === 'adventure' ? object(object(props.payload.files)['adventure.json']) : props.payload)
const nameOwner = computed(() => props.target === 'adventure' && core.value.tutorial ? object(core.value.tutorial) : core.value)
const nameKey = computed(() => props.target === 'world' ? 'world_name' : props.target === 'character_template' ? 'character_name' : 'name')
const name = computed({ get: () => String(nameOwner.value[nameKey.value] || ''), set: value => { nameOwner.value[nameKey.value] = value } })
const textKey = computed(() => props.target === 'character_template' ? 'background' : 'description')
const text = computed({ get: () => String(core.value[textKey.value] || ''), set: value => { core.value[textKey.value] = value } })
const book = computed(() => props.target === 'world' ? object(props.payload.book) : core.value)
const bookCore = computed(() => book.value.spec === 'lorebook_v3' ? object(object(book.value.data).lorebook) : book.value)
const entries = computed(() => Array.isArray(bookCore.value.entries) ? bookCore.value.entries as NativePayload[] : [])
function setEntry(index: number, key: string, event: Event) { entries.value[index]![key] = (event.target as HTMLInputElement).value }
function addEntry() {
  if (!Array.isArray(bookCore.value.entries)) bookCore.value.entries = []
  ;(bookCore.value.entries as NativePayload[]).push({ id: crypto.randomUUID().replaceAll('-', ''), name: '', content: '', keys: [] })
}
const graphFiles = computed(() => props.target === 'adventure' && Array.isArray(core.value.nodes) && Array.isArray(core.value.chapters) ? props.payload.files as ScriptFiles : null)
const raw = ref(''), error = ref('')
const resourcePending = ref(false)
watch(() => props.payload, value => { raw.value = JSON.stringify(value, null, 2) }, { deep: true, immediate: true })
watch(() => resourcePending.value || raw.value !== JSON.stringify(props.payload, null, 2), value => emit('pending', value), { immediate: true })
function apply() {
  try { const value: unknown = JSON.parse(raw.value); if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(copy.value.invalid); emit('replace', value as NativePayload); error.value = '' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : copy.value.invalid }
}
</script>
<template>
  <div class="native-editor">
    <template v-if="!['portrait', 'scene_image'].includes(target)">
      <label>{{ copy.name }}<input v-model="name" data-testid="fork-name"></label>
      <label v-if="target !== 'adventure' && target !== 'lorebook'">{{ copy.text }}<textarea v-model="text" rows="5" data-testid="fork-text" /></label>
      <section v-if="target === 'world' || target === 'lorebook'">
        <h3>{{ copy.entries }}</h3>
        <article v-for="(entry, index) in entries" :key="index" class="book-entry">
          <input :value="String(entry.name || '')" :aria-label="copy.name" @input="setEntry(index, 'name', $event)">
          <textarea :value="String(entry.content || '')" :aria-label="copy.text" rows="4" @input="setEntry(index, 'content', $event)" />
          <button type="button" @click="entries.splice(index, 1)">{{ copy.remove }}</button>
        </article>
        <button type="button" @click="addEntry">{{ copy.add }}</button>
      </section>
      <AdventureGraphForm v-if="graphFiles" :files="graphFiles" @pending="resourcePending = $event" />
      <details><summary>{{ copy.advanced }}</summary>
        <textarea v-model="raw" rows="12" :aria-label="copy.advanced" />
        <button type="button" @click="apply">{{ copy.apply }}</button>
        <p v-if="error" role="alert">{{ error }}</p>
      </details>
    </template>
  </div>
</template>
<style scoped>
.native-editor, label, .book-entry { display: grid; gap: .6rem; min-width: 0; }
.book-entry { margin-bottom: .8rem; padding: .7rem; border: 1px solid var(--df-border-soft); border-radius: .5rem; }
input, textarea { width: 100%; min-width: 0; box-sizing: border-box; } textarea { resize: vertical; }
</style>
