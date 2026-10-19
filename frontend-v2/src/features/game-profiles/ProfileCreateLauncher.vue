<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '@/api/client'
import { useLocale } from '@/composables/useLocale'
import Modal from '@/components/ui/Modal.vue'
import { rememberCurrentGame } from '@/stores/gameContext'
import { profileCopy } from './copy'
const { locale } = useLocale(), copy = computed(() => profileCopy(locale.value)), router = useRouter()
const open = ref(false), busy = ref(false), names = ref('Leader\nScout'), error = ref('')
async function start(profileId: string) {
  busy.value = true; error.value = ''
  try {
    const result = await api<{ ok: boolean; game_key: string }>('/game-profiles/create', { method: 'POST', body: JSON.stringify({ profile_id: profileId, name: profileId === 'core:demo-heist' ? copy.value.heist : copy.value.survival, names: names.value.split('\n').map(name => name.trim()).filter(Boolean), language: locale.value }) })
    rememberCurrentGame(result.game_key)
    await router.push({ name: 'play', query: { game: result.game_key } })
  } catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}
</script>
<template>
  <button type="button" data-testid="profile-launcher" @click="open = true">{{ copy.title }}</button>
  <Modal v-if="open" :title="copy.title" @close="open = false">
    <section class="profile-create"><p>{{ copy.hint }}</p><label>{{ copy.names }}<textarea v-model="names" rows="4" data-testid="profile-names" /></label>
      <p v-if="error" role="alert">{{ error }}</p>
      <button type="button" :disabled="busy" data-testid="profile-create-heist" @click="start('core:demo-heist')">{{ copy.start }}: {{ copy.heist }}</button>
      <button type="button" :disabled="busy" data-testid="profile-create-survival" @click="start('core:demo-survival')">{{ copy.start }}: {{ copy.survival }}</button>
    </section>
  </Modal>
</template>
<style scoped>.profile-create, label { display: grid; gap: 1rem; } textarea { width: 100%; box-sizing: border-box; } button { white-space: normal; }</style>
