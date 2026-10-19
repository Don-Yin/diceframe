<script setup lang="ts">
import { computed } from 'vue'
import { useLocale } from '@/composables/useLocale'
import type { GraphNode } from './scriptTypes'
import { choiceCopy } from './choiceCopy'
const props = defineProps<{ node: GraphNode }>()
const emit = defineEmits<{ upgrade: [] }>()
const node = computed(() => props.node), { locale } = useLocale()
const copy = computed(() => choiceCopy(locale.value))
function change(event: Event) {
  const exclusive = (event.target as HTMLSelectElement).value === 'exclusive'
  if (exclusive) {
    emit('upgrade'); node.value.choice_mode = 'exclusive'
    for (const transition of node.value.transitions) {
      transition.choice_id ||= `choice_${crypto.randomUUID().replaceAll('-', '')}`
      transition.choice_label ||= transition.to
    }
  } else {
    delete node.value.choice_mode
    for (const transition of node.value.transitions) { delete transition.choice_id; delete transition.choice_label }
  }
}
</script>
<template>
  <section class="choice-editor">
    <label>{{ copy.mode }}<select :value="node.choice_mode || 'parallel'" data-testid="graph-choice-mode" @change="change"><option value="parallel">{{ copy.parallel }}</option><option value="exclusive">{{ copy.exclusive }}</option></select></label>
    <label v-for="transition in node.choice_mode === 'exclusive' ? node.transitions : []" :key="transition.choice_id">{{ copy.label }}<input v-model="transition.choice_label" data-testid="graph-choice-label" maxlength="256"></label>
  </section>
</template>
<style scoped>
.choice-editor, label { display: grid; gap: .5rem; min-width: 0; } select, input { width: 100%; min-width: 0; box-sizing: border-box; }
</style>
