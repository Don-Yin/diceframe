<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { importCopy } from './importCopy'
export type Gate = { type: string; id?: string; key?: string; value: unknown }
const props = defineProps<{ transition: { conditions?: Gate[] }; allowRules?: boolean }>()
const emit = defineEmits<{ pending: [value: boolean] }>()
const transition = computed(() => props.transition)
const { locale } = useLocale()
const copy = computed(() => importCopy(locale.value)), invalidValues = ref(new Map<Gate, string>())
const error = computed(() => invalidValues.value.size ? copy.value.value : '')
const types = ['world.fact_equals', 'world.entity_status', 'world.relation_status', 'world.process_status', 'adventure.milestone', 'adventure.objective_status', 'rules.outcome', 'rules.party_level', 'rules.item_possession']
const availableTypes = (gate: Gate) => types.filter(type => props.allowRules !== false || !type.startsWith('rules.') || type === gate.type)
watch(error, value => emit('pending', !!value), { immediate: true })
watch(transition, () => { invalidValues.value.clear() })
onBeforeUnmount(() => emit('pending', false))
function add() { (transition.value.conditions ||= []).push({ type: 'adventure.objective_status', id: '', value: 'completed' }) }
function changeType(gate: Gate, event: Event) { gate.type = (event.target as HTMLSelectElement).value; delete gate.id; delete gate.key; if (gate.type === 'world.fact_equals') gate.key = ''; else gate.id = '' }
function changeValue(gate: Gate, event: Event) {
  const value = (event.target as HTMLInputElement).value
  try { gate.value = JSON.parse(value); invalidValues.value.delete(gate) }
  catch { invalidValues.value.set(gate, value) }
}
function remove(gate: Gate, index: number) { invalidValues.value.delete(gate); transition.value.conditions?.splice(index, 1) }
</script>
<template>
  <section class="gate-editor"><strong>{{ copy.gates }}</strong>
    <div v-for="(gate, index) in transition.conditions || []" :key="index" class="gate-row">
      <label>{{ copy.type }}<select :value="gate.type" @change="changeType(gate, $event)"><option v-for="type in availableTypes(gate)" :key="type">{{ type }}</option></select></label>
      <label>{{ copy.identity }}<input v-if="gate.type === 'world.fact_equals'" v-model="gate.key"><input v-else v-model="gate.id"></label>
      <label>{{ copy.value }}<input :value="invalidValues.get(gate) ?? JSON.stringify(gate.value)" @input="changeValue(gate, $event)"></label>
      <button @click="remove(gate, index)">{{ copy.remove }}</button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p><button @click="add">{{ copy.addGate }}</button>
  </section>
</template>
<style scoped>
.gate-editor, label { display: grid; gap: .4rem; min-width: 0; } .gate-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .5rem; padding: .5rem; border: 1px solid var(--df-border-soft); }
input, select { width: 100%; box-sizing: border-box; min-width: 0; }
</style>
