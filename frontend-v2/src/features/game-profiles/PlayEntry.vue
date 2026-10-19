<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, errorMessage } from '@/api/client'
import { useLocale } from '@/composables/useLocale'
import { readCurrentGame } from '@/stores/gameContext'
import ProfileBoard from './ProfileBoard.vue'
import type { ProfileView } from './types'
const PlayView = defineAsyncComponent(() => import('@/features/play/PlayView.vue').then(module => module.default))
const route = useRoute(), { t } = useLocale(), loading = ref(false), error = ref(''), state = ref<ProfileView | null>(null)
const key = computed(() => String(route.query.game || readCurrentGame() || ''))
let epoch = 0, resolvedPath = ''
async function load() {
  const current = ++epoch
  loading.value = !!key.value; error.value = ''; state.value = null
  try {
    if (key.value) {
      const base = `/games/${encodeURIComponent(key.value)}`
      const detail = await api<{ game_profile?: object | null }>(base)
      if (current !== epoch) return
      if (detail.game_profile) {
        const value = await api<ProfileView>(`${base}/profile`)
        if (current === epoch) state.value = value.profile ? value : null
      }
      if (current === epoch) resolvedPath = route.fullPath
    }
  } catch (cause) { if (current === epoch) error.value = errorMessage(cause) }
  finally { if (current === epoch) loading.value = false }
}
watch(() => route.fullPath, () => {
  if (route.name === 'play' && (route.fullPath !== resolvedPath || error.value)) void load()
}, { immediate: true })
</script>
<template>
  <section v-if="loading" class="view" role="status">{{ t('refresh') }}…</section>
  <section v-else-if="error" class="view"><p role="alert">{{ error }}</p><button @click="load">{{ t('refresh') }}</button></section>
  <ProfileBoard v-else-if="state" :key="key" :game-key="key" :initial="state" />
  <PlayView v-else />
</template>
