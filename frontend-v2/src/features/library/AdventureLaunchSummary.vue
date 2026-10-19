<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { NIcon } from 'naive-ui'
import { BookOutline } from '@vicons/ionicons5'
import type { AdventureSummary } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import { libraryCopy } from './copy'

const props = defineProps<{ adventure: AdventureSummary; ruleName?: string }>()
const { locale } = useLocale()
const copy = computed(() => libraryCopy(locale.value))
const source = computed(() => props.adventure.source_kind === 'plugin' ? copy.value.package
  : props.adventure.source_kind === 'user' || props.adventure.custom ? copy.value.user : copy.value.builtin)
</script>

<template>
  <section class="content-launch-summary" data-testid="create-adventure-summary">
    <span class="library-card-emblem" aria-hidden="true"><NIcon :component="BookOutline" /></span>
    <div class="content-launch-story"><span class="eyebrow">{{ copy.adventures }}</span><h2>{{ adventure.name }}</h2><p>{{ adventure.summary }}</p><div class="content-launch-facts"><span>{{ ruleName || adventure.required_runtime?.id || copy.unknownRuntime }}</span><span>{{ source }}<template v-if="adventure.source_id"> · {{ adventure.source_id }}</template></span><span>{{ copy.version }} {{ adventure.version }}</span></div></div>
    <RouterLink class="content-button" :to="{ name: 'library' }">{{ copy.backLibrary }}</RouterLink>
  </section>
</template>
