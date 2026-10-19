<script setup lang="ts">
import { computed } from 'vue'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ modelValue: string; worlds: Array<{ id: string; name: string; language: string }> }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const { locale } = useLocale()
const copy = computed(() => {
  const all = {
    'zh-CN': { mode: '资料使用方式', inherit: '沿用当前世界', blank: '新世界 · 空白资料', reference: '新世界 · 引用资料', world: '来源世界' },
    en: { mode: 'Book source', inherit: 'Use this world', blank: 'New world · blank books', reference: 'New world · referenced books', world: 'Source world' },
    de: { mode: 'Buchquelle', inherit: 'Diese Welt verwenden', blank: 'Neue Welt · leere Bücher', reference: 'Neue Welt · Buchverweise', world: 'Quellwelt' },
    ja: { mode: '資料の使用方法', inherit: '現在の世界を使う', blank: '新しい世界 · 空白の資料', reference: '新しい世界 · 資料を参照', world: '参照元の世界' },
    ru: { mode: 'Источник книг', inherit: 'Использовать этот мир', blank: 'Новый мир · пустые книги', reference: 'Новый мир · ссылки на книги', world: 'Исходный мир' },
  }
  return all[locale.value as keyof typeof all] || all.en
})
const sourceMode = computed({
  get: () => props.modelValue.startsWith('copy:') ? 'reference' : props.modelValue,
  set: (value: string) => {
    if (value === 'reference') {
      const world = props.worlds[0]
      if (world) emit('update:modelValue', `copy:${world.id}`)
    } else if (value === '__builtin__' || value === '__blank__') emit('update:modelValue', value)
  },
})
const referenceWorld = computed({
  get: () => props.modelValue.startsWith('copy:') ? props.modelValue.slice(5) : '',
  set: (value: string) => {
    if (props.worlds.some(world => world.id === value)) emit('update:modelValue', `copy:${value}`)
  },
})
</script>

<template>
  <div class="create-book-source-fields">
    <label><span>{{ copy.mode }}</span><select v-model="sourceMode" data-testid="lore-source-mode">
      <option value="__builtin__">{{ copy.inherit }}</option>
      <option value="__blank__">{{ copy.blank }}</option>
      <option value="reference" :disabled="!worlds.length">{{ copy.reference }}</option>
    </select></label>
    <label v-if="sourceMode === 'reference'"><span>{{ copy.world }}</span><select v-model="referenceWorld" data-testid="lore-source-world">
      <option v-for="world in worlds" :key="world.id" :value="world.id">{{ world.name }} · {{ world.language }}</option>
    </select></label>
  </div>
</template>

<style scoped>
.create-book-source-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:12px}
label{display:grid;gap:6px;min-width:0}label>span{font-size:12px;color:var(--df-text-secondary)}select{width:100%;min-width:0}
@media(max-width:620px){.create-book-source-fields{grid-template-columns:minmax(0,1fr)}}
</style>
