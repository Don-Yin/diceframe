<script setup lang="ts">
import { computed } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { spellCopy } from './spellCopy'
const props = defineProps<{ spells: Array<{ spell_ref: string; name: string; blocked_reason: string }> }>()
const { locale } = useLocale()
const copy = computed(() => spellCopy(locale.value))
const blocked = computed(() => props.spells.filter(spell => spell.blocked_reason))
function reason(key: string) { return copy.value.reasons[key as keyof typeof copy.value.reasons] || key }
</script>

<template>
  <ul v-if="blocked.length" class="spell-availability" data-testid="spell-availability">
    <li v-for="spell in blocked" :key="spell.spell_ref"><strong>{{ spell.name }}</strong><span>{{ reason(spell.blocked_reason) }}</span></li>
  </ul>
</template>

<style scoped>
.spell-availability{list-style:none;display:grid;gap:9px;padding:0;margin:8px 0 0}
li{display:grid;gap:4px;border-top:1px solid var(--df-border-soft);padding-top:9px;min-width:0}
strong{font-size:12px;color:var(--df-text-secondary)}span{font-size:11px;line-height:1.5;color:var(--df-text-muted);overflow-wrap:anywhere}
</style>
