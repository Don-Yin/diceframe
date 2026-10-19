<script setup lang="ts">
import { computed } from 'vue'
import type { RuleSpecialStat } from '@/api/types'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ modelValue: RuleSpecialStat[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: RuleSpecialStat[]] }>()
const { locale } = useLocale()
const copy = computed(() => locale.value === 'zh-CN'
  ? { title: '额外资源', add: '添加资源', key: '标识，如 mp', name: '名称，如魔力', max: '上限', initial: '初始值（留空用默认）', remove: '删除', hint: '魔力、体力等资源在这里声明。保存规则不会重置已保存角色的当前数值，修改后请在角色管理中核对。用于战斗消耗时，还需在战斗扩展中显式声明。' }
  : { title: 'Additional resources', add: 'Add resource', key: 'ID, e.g. mp', name: 'Name, e.g. Mana', max: 'Maximum', initial: 'Initial (blank uses default)', remove: 'Delete', hint: 'Declare mana, stamina and similar resources here. Saving a rule does not reset existing character values; verify them in character management. Combat costs require an explicit combat-extension declaration.' })
function update(index: number, key: keyof RuleSpecialStat, value: string) {
  emit('update:modelValue', props.modelValue.map((stat, i) => {
    if (i !== index) return stat
    const next = { ...stat }
    if (key === 'initial' && !value.trim()) delete next.initial
    else if (key === 'initial' || key === 'max') next[key] = Number(value)
    else next[key] = value
    return next
  }))
}
</script>

<template>
  <section class="rule-editor-section rule-resources-editor">
    <div class="section-head"><strong>{{ copy.title }}</strong><button type="button" @click="emit('update:modelValue', [...modelValue, { key: '', name: '', max: 100 }])">+ {{ copy.add }}</button></div>
    <p class="muted">{{ copy.hint }}</p>
    <div v-for="(stat, index) in modelValue" :key="index" class="resource-row">
      <label><span>{{ copy.key }}</span><input :value="stat.key" @input="update(index, 'key', ($event.target as HTMLInputElement).value)"></label>
      <label><span>{{ copy.name }}</span><input :value="stat.name || ''" @input="update(index, 'name', ($event.target as HTMLInputElement).value)"></label>
      <label><span>{{ copy.max }}</span><input type="number" min="1" step="1" :value="stat.max ?? 99" @input="update(index, 'max', ($event.target as HTMLInputElement).value)"></label>
      <label><span>{{ copy.initial }}</span><input type="number" min="0" step="1" :value="stat.initial ?? ''" @input="update(index, 'initial', ($event.target as HTMLInputElement).value)"></label>
      <button type="button" class="danger" @click="emit('update:modelValue', modelValue.filter((_, i) => i !== index))">{{ copy.remove }}</button>
    </div>
  </section>
</template>

<style scoped>
.resource-row { display: grid; grid-template-columns: 1fr 1fr 100px 170px auto; gap: 8px; align-items: end; margin: 10px 0; }
label { display: grid; gap: 5px; min-width: 0; }
label span { font-size: 12px; color: var(--df-text-muted); }
input { width: 100%; min-width: 0; }
@media(max-width: 700px) { .resource-row { grid-template-columns: repeat(2, minmax(0, 1fr)); padding-bottom: 12px; border-bottom: 1px solid var(--df-border-soft); } .resource-row > button { justify-self: end; grid-column: 2; } }
</style>
