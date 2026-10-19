<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useLocale } from '@/composables/useLocale'
import type { ScriptFiles } from './scriptTypes'
import AdventureResourcesForm from './AdventureResourcesForm.vue'
import GateEditor from './GateEditor.vue'
import ChoiceEditor from './ChoiceEditor.vue'
import { importCopy } from './importCopy'
import { narrativeRuntimeId } from './compatibility'

const props = defineProps<{ files: ScriptFiles }>()
const emit = defineEmits<{ pending: [value: boolean] }>()
const resourcePending = ref(false), gatePending = reactive<Record<string, boolean>>({})
watch(() => resourcePending.value || Object.values(gatePending).some(Boolean), value => emit('pending', value), { immediate: true })
const { t, locale } = useLocale()
const copy = computed(() => importCopy(locale.value))
const records = (kind: string) => Object.values(props.files).filter(value => value && typeof value === 'object' && value.kind === kind)
const graph = computed(() => props.files['adventure.json'])
const manifest = computed(() => props.files['manifest.json'])
const narrativeOnly = computed(() => (manifest.value.required_runtime as { id?: string } | undefined)?.id === narrativeRuntimeId)

function addScene() {
  const graphValue = graph.value
  let index = graphValue.nodes.length + 1
  while (graphValue.nodes.some(node => node.id === `n_${index}`)) index++
  const chapter = graphValue.chapters[0]?.id
  graphValue.nodes.push({ id: `n_${index}`, type: 'scene', name: t('scriptNewScene'), description: '', chapter_id: chapter, visibility: 'gm', transitions: [] })
}
function connectInOrder() {
  const nodes = graph.value.nodes.filter(node => node.type !== 'reference')
  nodes.slice(0, -1).forEach((node, index) => {
    if (!node.transitions.length && node.choice_mode !== 'exclusive') node.transitions.push({ to: nodes[index + 1]!.id })
  })
}
function addBranch(node: import('./scriptTypes').GraphNode) {
  const target = graph.value.nodes[0]?.id || ''
  node.transitions.push(node.choice_mode === 'exclusive' ? { to: target, choice_id: `choice_${crypto.randomUUID().replaceAll('-', '')}`, choice_label: target } : { to: target })
}
</script>

<template>
  <section class="graph-form">
    <p v-if="narrativeOnly" data-testid="adventure-profile">{{ locale === 'zh-CN' ? '通用剧情：可用于支持剧情图的规则。检定、战斗和奖励由本局规则处理；此包不自动结算专属机制。' : 'Universal story: works with rules that support story graphs. Checks, combat and rewards follow the game rules; this package does not automatically settle specific mechanics.' }}</p>
    <div class="graph-metadata">
      <label>{{ t('adventurePackageName') }}<input v-model="graph.name" data-testid="graph-name"></label>
      <label>{{ t('modulesVersionLabel') }}<input v-model="manifest.version"></label>
      <label>{{ t('adventureWorldPolicy') }}<select v-model="manifest.world_policy"><option value="portable">{{ t('adventurePolicyPortable') }}</option><option value="agnostic">{{ t('adventurePolicyAgnostic') }}</option><option value="fixed">{{ t('adventurePolicyFixed') }}</option></select></label>
      <label>{{ t('scriptRecommendedWorld') }}<input v-model="manifest.recommended_world_id"></label>
    </div>
    <label>{{ t('scriptStartScenes') }}<select v-model="graph.start_node_ids" multiple>
      <option v-for="node in graph.nodes" :key="node.id" :value="node.id">{{ node.name || node.id }}</option>
    </select></label>
    <label v-for="chapter in graph.chapters" :key="chapter.id">{{ t('adventureChapter') }}<input v-model="chapter.name"></label>
    <button type="button" data-testid="graph-connect-order" @click="connectInOrder">{{ copy.connect }}</button>
    <article v-for="node in graph.nodes" :key="node.id" class="graph-node">
      <header><strong>{{ node.id }}</strong><button type="button" @click="graph.nodes = graph.nodes.filter(item => item !== node)">{{ t('delete') }}</button></header>
      <div class="graph-metadata">
        <label>{{ t('name') }}<input v-model="node.name"></label>
        <label>{{ t('adventureChapter') }}<select v-model="node.chapter_id"><option v-for="chapter in graph.chapters" :key="chapter.id" :value="chapter.id">{{ chapter.name || chapter.id }}</option></select></label>
        <label>{{ t('scriptVisibility') }}<select v-model="node.visibility"><option value="gm">{{ t('scriptGmOnly') }}</option><option value="public">{{ t('scriptPublic') }}</option></select></label>
      </div>
      <label>{{ t('description') }}<textarea v-model="node.description" rows="5" data-testid="graph-node-description" /></label>
      <ChoiceEditor :node="node" @upgrade="graph.schema_version = 2" />
      <label>{{ copy.scene }}<select v-model="node.scene_ref"><option :value="undefined">—</option><option v-for="record in records('scene')" :key="record.id" :value="`scene:${record.id}`">{{ record.name || record.id }}</option></select></label>
      <label>{{ copy.npc }}<select :value="node.npc_refs || []" multiple data-testid="graph-npc-refs" @change="node.npc_refs = Array.from(($event.target as HTMLSelectElement).selectedOptions, option => option.value)"><option v-for="record in records('npc')" :key="record.id" :value="`npc:${record.id}`">{{ record.name || record.id }}</option></select></label>
      <label v-if="!narrativeOnly || node.encounter_ref">{{ copy.encounter_catalog }}<select v-model="node.encounter_ref" data-testid="graph-encounter-ref"><option :value="undefined">—</option><option v-for="record in records('encounter_catalog')" :key="record.id" :value="`encounter_catalog:${record.id}`">{{ record.name || record.id }}</option></select></label>
      <div v-for="(transition, index) in node.transitions" :key="index" class="graph-transition">
        <label>{{ t('scriptNextScene') }}<select v-model="transition.to"><option v-for="target in graph.nodes" :key="target.id" :value="target.id">{{ target.name || target.id }}</option></select></label>
        <button type="button" @click="node.transitions.splice(index, 1)">{{ t('delete') }}</button>
        <GateEditor :transition="transition" :allow-rules="!narrativeOnly" @pending="gatePending[`${node.id}_${index}`] = $event" />
      </div>
      <button type="button" @click="addBranch(node)">{{ t('scriptAddBranch') }}</button>
    </article>
    <button type="button" @click="addScene">{{ t('scriptAddScene') }}</button>
    <AdventureResourcesForm :files="files" @pending="resourcePending = $event" />
  </section>
</template>

<style scoped>
.graph-form { display: grid; gap: 1rem; min-width: 0; padding: .9rem; border: 1px solid color-mix(in srgb, var(--df-accent) 26%, var(--df-border-soft)); border-radius: var(--df-radius-md); background: var(--df-surface-2); }
.graph-metadata { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .75rem; }
label { display: grid; gap: .4rem; margin: 0; }
input, select, textarea { box-sizing: border-box; width: 100%; min-width: 0; }
.graph-node { display: grid; gap: .75rem; padding: 1rem; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); background: var(--df-surface-1); }
.graph-node header, .graph-transition { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem; }
.graph-transition label { flex: 1; }
</style>
