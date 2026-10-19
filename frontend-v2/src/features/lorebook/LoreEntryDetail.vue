<script setup lang="ts">
import type { LoreEntry, LoreProjection } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import LoreVisibilityBadge from './LoreVisibilityBadge.vue'
defineProps<{ entry: LoreEntry; projection: LoreProjection | null; typeLabel: string; activationLabel: string }>()
const emit = defineEmits<{ edit: []; remove: [] }>()
const { t } = useLocale()
</script>

<template>
  <section class="lore-entry-detail" data-testid="lore-entry-detail" :aria-label="entry.name">
    <header><div><span class="badge">{{ typeLabel }}</span><h2>{{ entry.name || t('unnamedLoreEntry') }}</h2></div><LoreVisibilityBadge :projection="projection" /></header>
    <p class="lore-detail-content">{{ entry.content || t('noContent') }}</p>
    <dl><div><dt>{{ t('loreActivationMode') }}</dt><dd>{{ activationLabel }}</dd></div><div v-if="entry.keywords?.length"><dt>{{ t('keywords') }}</dt><dd>{{ Array.isArray(entry.keywords) ? entry.keywords.join(t('listSeparator')) : entry.keywords }}</dd></div></dl>
    <div class="actions"><button class="primary" data-testid="lore-detail-edit" @click="emit('edit')">{{ t('edit') }}</button><button class="danger" @click="emit('remove')">{{ t('delete') }}</button></div>
  </section>
</template>
