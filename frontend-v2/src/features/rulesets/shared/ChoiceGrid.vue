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
.ruleset-choice-card { display: grid; gap: 8px; min-height: 84px; padding: 13px; border: 1px solid var(--df-border-soft); border-radius: 13px; background: var(--df-surface-1); color: var(--df-text); text-align: left; cursor: pointer; transition: border-color .18s ease, background .18s ease, box-shadow .18s ease, transform .18s ease; }
.ruleset-choice-card:hover { border-color: var(--df-interactive); background: color-mix(in srgb, var(--df-interactive) 7%, var(--df-surface-1)); transform: translateY(-1px); }
.ruleset-choice-card.selected { border-color: var(--df-accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--df-accent) 18%, transparent); background: color-mix(in srgb, var(--df-accent) 12%, var(--df-surface-2)); }
.ruleset-choice-card:focus-visible { outline: 3px solid var(--df-interactive-strong); outline-offset: 2px; }
.choice-title { display: flex; justify-content: space-between; gap: 8px; }
.choice-title small { color: var(--df-text-muted); font-size: 10px; text-transform: uppercase; }
.choice-summary { color: var(--df-text-secondary); font-size: 12px; line-height: 1.55; }
.choice-items { display: grid; gap: 2px; color: var(--df-text-secondary); font-size: 12px; line-height: 1.4; }
.choice-items span { overflow-wrap: anywhere; }
.choice-items b { color: var(--df-accent-strong); font-weight: 600; }
code { color: var(--df-text-muted); font-size: 10px; overflow-wrap: anywhere; }
@media (prefers-reduced-motion: reduce) { .ruleset-choice-card { transition: none; } .ruleset-choice-card:hover { transform: none; } }
</style>
