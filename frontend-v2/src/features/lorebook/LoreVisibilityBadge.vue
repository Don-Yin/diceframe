<script setup lang="ts">
import { computed } from 'vue'
import type { LoreProjection } from '@/api/types'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ projection: LoreProjection | null }>()
const { t } = useLocale()

const label = computed(() => {
  const p = props.projection
  if (!p) return ''
  if (p.audience === 'public') return t('loreAudiencePublic')
  if (p.audience === 'gm') return t('loreAudienceGmSecret')
  return t('loreAudienceCharacterOnly', { names: p.subjects.join(t('listSeparator')) })
})
</script>

<template>
  <span v-if="projection" class="lore-visibility-badge" :class="`audience-${projection.audience}`">{{ label }}</span>
</template>
