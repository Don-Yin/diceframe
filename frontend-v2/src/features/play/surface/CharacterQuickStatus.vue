<script setup lang="ts">
import { computed } from 'vue'
import type { Player, RuleMeta } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import PortraitImage from '@/components/PortraitImage.vue'
import { getResourceValue } from '@/utils/ruleSchema'
import { buildSpecialStats, primaryResourceList } from '@/utils/play'

const props = defineProps<{ player?: Player; ruleMeta?: RuleMeta }>()
const emit = defineEmits<{ open: [] }>()
const { t } = useLocale()
const resources = computed(() => {
  const cs = props.player?.character_sheet || {}
  const hp = cs.resources?.hp || typeof cs.hp === 'number' ? [{ key: 'hp', label: 'HP', ...getResourceValue(cs, 'hp') }] : []
  return [...hp, ...buildSpecialStats(cs, props.ruleMeta?.rule_special_stats).map(stat => ({ ...stat, label: stat.name })),
    ...primaryResourceList(cs, props.ruleMeta)].slice(0, 3)
})
</script>

<template>
  <button v-if="player" type="button" class="play-quick-status" data-testid="play-quick-status" @click="emit('open')" :aria-label="t('characterStatus')">
    <PortraitImage :portrait="player.character_sheet?.portrait" :rule-id="ruleMeta?.rule_id" :seed="player.user_id" :name="player.character_name" :size="22" />
    <strong>{{ player.character_name }}</strong>
    <span v-for="resource in resources" :key="resource.key">{{ resource.label }} <b>{{ resource.current }}<template v-if="resource.max"> / {{ resource.max }}</template></b></span>
  </button>
</template>
