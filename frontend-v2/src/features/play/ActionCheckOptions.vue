<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useLocale } from '@/composables/useLocale'

defineProps<{ skills: string[]; modelValue: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const disclosure = ref<HTMLDetailsElement | null>(null)
function close(focus = false) {
  if (!disclosure.value?.open) return
  disclosure.value.open = false
  if (focus) disclosure.value.querySelector('summary')?.focus()
}
function outside(event: PointerEvent) {
  if (event.target instanceof Node && !disclosure.value?.contains(event.target)) close()
}
onMounted(() => document.addEventListener('pointerdown', outside))
onUnmounted(() => document.removeEventListener('pointerdown', outside))
function choose(event: Event) {
  emit('update:modelValue', (event.target as HTMLSelectElement).value)
  if (disclosure.value) disclosure.value.open = false
}
const { locale } = useLocale()
const copy = computed(() => locale.value === 'zh-CN'
  ? { title: '本次使用的技能（可选）', shortTitle: '本次技能', skill: '角色技能', automatic: '自动判断', hint: '明确选择后优先用于本次检定；加值仍由服务端按角色卡和规则计算，不会指定骰面或绕过规则。' }
  : { title: 'Skill for this action (optional)', shortTitle: 'Action skill', skill: 'Character skill', automatic: 'Choose automatically', hint: 'An explicit choice takes priority for this check. The server still calculates modifiers from the character and rules; this never specifies dice or bypasses rules.' })
</script>

<template>
  <details v-if="skills.length" ref="disclosure" class="action-check-options" @keydown.esc.stop.prevent="close(true)">
    <summary :title="`${copy.title}${modelValue ? ` · ${modelValue}` : ''}`" :aria-label="`${copy.title}${modelValue ? ` · ${modelValue}` : ''}`">{{ copy.shortTitle }}<span>{{ modelValue || copy.automatic }}</span></summary>
    <div class="action-check-menu">
      <label><span>{{ copy.skill }}</span><select :value="modelValue" :disabled="disabled" @change="choose"><option value="">{{ copy.automatic }}</option><option v-for="skill in skills" :key="skill" :value="skill">{{ skill }}</option></select></label>
      <p>{{ copy.hint }}</p>
    </div>
  </details>
</template>

<style scoped>
.action-check-options { position: relative; min-width: 0; margin: 0; }
summary { position: relative; display: grid; align-content: center; gap: 2px; box-sizing: border-box; height: 44px; padding: 5px 18px 5px 7px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-md); background: var(--df-surface-2); cursor: pointer; font-size: 11px; line-height: 1.35; color: var(--df-text-secondary); list-style: none; }
summary::-webkit-details-marker { display: none; }
summary::after { content: '⌄'; position: absolute; right: 6px; top: 50%; transform: translateY(-50%); }
summary span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--df-accent-strong); }
summary:hover, summary:focus-visible { border-color: var(--df-interactive); }
.action-check-menu { position: absolute; right: 0; bottom: calc(100% + 8px); z-index: 60; width: min(300px, calc(100vw - 24px)); padding: 12px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-md); background: var(--df-surface-1); box-shadow: var(--df-shadow-strong); }
label { display: grid; gap: 6px; font-size: 12px; }
select { width: 100%; min-width: 0; min-height: 40px; }
p { margin: 8px 0 0; color: var(--df-text-muted); font-size: 12px; line-height: 1.5; }
</style>
