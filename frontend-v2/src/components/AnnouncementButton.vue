<script setup lang="ts">
import { NButton, NIcon } from 'naive-ui'
import { MegaphoneOutline } from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'
import { useAnnouncements } from '@/composables/useAnnouncements'

defineEmits<{ open: [] }>()
const { t } = useLocale()
const { hasUnread } = useAnnouncements()
</script>
<template>
  <NButton
    circle
    quaternary
    class="theme-toggle"
    :title="t('viewAnnouncement')"
    @click="$emit('open')"
  >
    <template #icon>
      <NIcon size="18">
        <MegaphoneOutline />
      </NIcon>
    </template>
    <i v-if="hasUnread" class="nav-update-dot" :aria-label="t('newAnnouncement')" />
  </NButton>
</template>
