<script setup lang="ts">
import { computed, ref } from 'vue'
import Modal from '@/components/ui/Modal.vue'
import { api, errorMessage } from '@/api/client'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import { roomPasswordProblem, roomPasswordProblemMessage } from '@/utils/roomPassword'

const props = defineProps<{ gameKey: string; hasPassword: boolean }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const { t } = useLocale()
const toast = useToast()

const password = ref('')
const busy = ref(false)
const error = ref('')
const status = computed(() => props.hasPassword ? t('roomPasswordConfigured') : t('roomPasswordUnconfigured'))

function close() {
  if (!busy.value) emit('close')
}

function validate(): boolean {
  const problem = roomPasswordProblem(password.value)
  if (!problem) return true
  const [key, params] = roomPasswordProblemMessage(problem)
  error.value = t(key, params)
  return false
}

async function submit(value: string) {
  if (busy.value) return
  password.value = value
  error.value = ''
  if (value !== '' && !validate()) return
  busy.value = true
  try {
    const result = await api<{ ok?: boolean }>(`/games/${encodeURIComponent(props.gameKey)}/room-password`, {
      method: 'POST',
      body: JSON.stringify({ password: value }),
    })
    if (result?.ok === false) throw new Error(t('settingFailed'))
    toast.success(value ? t('roomPasswordUpdated') : t('roomPasswordCleared'))
    emit('changed')
    emit('close')
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    busy.value = false
  }
}

function save() {
  if (!password.value) return
  void submit(password.value)
}

function remove() {
  if (!props.hasPassword) return
  void submit('')
}
</script>

<template>
  <Modal :title="t('roomPassword')" @close="close">
    <section class="room-password-dialog">
      <p data-testid="room-password-status">{{ status }}</p>
      <p class="hint">{{ t('roomPasswordDialogHint') }}</p>
      <label>
        {{ t('roomPasswordNewLabel') }}
        <input
          v-model="password"
          data-testid="room-password-input"
          type="password"
          autocomplete="new-password"
          :placeholder="t('roomPasswordNewPlaceholder')"
          :disabled="busy"
        >
      </label>
      <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
      <div class="actions">
        <button data-testid="room-password-cancel" type="button" :disabled="busy" @click="close">{{ t('roomPasswordCancel') }}</button>
        <button v-if="props.hasPassword" class="danger" data-testid="room-password-remove" type="button" :disabled="busy" @click="remove">{{ t('roomPasswordRemove') }}</button>
        <button class="primary" data-testid="room-password-save" type="button" :disabled="busy || !password" @click="save">{{ busy ? t('saving') : t('roomPasswordSave') }}</button>
      </div>
    </section>
  </Modal>
</template>

<style scoped>
.room-password-dialog, label { display: grid; gap: .65rem; }
input { width: 100%; box-sizing: border-box; }
.actions { display: flex; gap: .65rem; justify-content: flex-end; flex-wrap: wrap; }
.error-banner { color: var(--df-danger-strong); }
</style>
