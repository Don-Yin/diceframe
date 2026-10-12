<script setup lang="ts">
import type { RulesetChoice } from '@/api/types'

withDefaults(defineProps<{
  modelValue?: string
  choices: RulesetChoice[]
  sourceVisible?: boolean
  compact?: boolean
}>(), { modelValue: '', sourceVisible: false, compact: false })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div :class="['ruleset-choice-grid', { compact }]">
    <button
      v-for="choice in choices"
      :key="choice.ref"
      type="button"
      :data-choice-ref="choice.ref"
      :class="['ruleset-choice-card', { selected: modelValue === choice.ref }]"
      :aria-pressed="modelValue === choice.ref"
      @click="emit('update:modelValue', choice.ref)"
    >
      <span class="choice-title"><b>{{ choice.name }}</b><small>{{ choice.automation_level }}</small></span>
      <span v-if="choice.summary" class="choice-summary">{{ choice.summary }}</span>
      <span v-if="choice.items?.length" class="choice-items">
        <span v-for="item in choice.items" :key="item.ref">{{ item.name }}<b v-if="item.quantity > 1"> ×{{ item.quantity }}</b></span>
      </span>
      <code v-if="sourceVisible">{{ choice.source_ref }}</code>
    </button>
  </div>
</template>

<style scoped>
.ruleset-choice-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }
.ruleset-choice-grid.compact { grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); }
.ruleset-choice-card { display: grid; gap: 8px; min-height: 84px; padding: 13px; border: 1px solid #394659; border-radius: 13px; background: #121a25; color: #e8edf5; text-align: left; cursor: pointer; }
.ruleset-choice-card:hover { border-color: #8d713f; transform: translateY(-1px); }
.ruleset-choice-card.selected { border-color: #d3a653; box-shadow: 0 0 0 2px rgb(211 166 83 / 18%); background: #211c17; }
.ruleset-choice-card:focus-visible { outline: 3px solid #e2b35e; outline-offset: 2px; }
.choice-title { display: flex; justify-content: space-between; gap: 8px; }
.choice-title small { color: #9ba7ba; font-size: 10px; text-transform: uppercase; }
.choice-summary { color: #aeb8c8; font-size: 12px; line-height: 1.55; }
.choice-items { display: grid; gap: 2px; color: #d3dbe4; font-size: 12px; line-height: 1.4; }
.choice-items span { overflow-wrap: anywhere; }
.choice-items b { color: #e0b766; font-weight: 600; }
code { color: #8b97aa; font-size: 10px; overflow-wrap: anywhere; }
:global(body.light .ruleset-choice-card) { border-color: #c3b7a4; background: #fff; color: #302b25; }
:global(body.light .ruleset-choice-card.selected) { border-color: #a8752c; background: #fff4dc; }
:global(body.light .ruleset-choice-card .choice-title small), :global(body.light .ruleset-choice-card .choice-summary), :global(body.light .ruleset-choice-card code) { color: #514b43; }
:global(body.light .ruleset-choice-card .choice-items) { color: #403a33; }
@media (prefers-reduced-motion: reduce) { .ruleset-choice-card { transition: none; } .ruleset-choice-card:hover { transform: none; } }
</style>
