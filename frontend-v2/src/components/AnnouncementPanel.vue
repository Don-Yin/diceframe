<script setup lang="ts">
import { computed } from 'vue'
import { NModal } from 'naive-ui'
import { useLocale } from '@/composables/useLocale'
import { useAnnouncements } from '@/composables/useAnnouncements'
import { renderSafeMarkdown } from '@/utils/markdown'

defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()
const { t } = useLocale()
const { content, stale } = useAnnouncements()

const html = computed(() => {
  return renderSafeMarkdown(content.value || '')
})
</script>
<template>
  <NModal
    :show="show"
    preset="card"
    :title="t('officialAnnouncement')"
    style="max-width: 520px;"
    @update:show="(v: boolean) => emit('update:show', v)"
  >
    <div v-if="html" class="announcement-panel-body safe-markdown" v-html="html" />
    <p v-else class="muted">{{ t('noAnnouncement') }}</p>
    <p v-if="stale && html" class="cached-hint">{{ t('announcementCached') }}</p>
  </NModal>
</template>

<style scoped>
.cached-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: #8a8a8a;
}
</style>
