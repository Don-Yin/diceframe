<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/api/client'
import type { KpQuestionResponse } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import Modal from '@/components/ui/Modal.vue'

const props = defineProps<{ gameKey: string }>()
const emit = defineEmits<{ close: []; shared: [] }>()
const { t } = useLocale()

const question = ref('')
const answer = ref('')
const error = ref('')
const busy = ref(false)
const shareWithParty = ref(false)

async function submit(): Promise<void> {
  const text = question.value.trim()
  if (!text || busy.value) return
  busy.value = true
  answer.value = ''
  error.value = ''
  try {
    const response = await api<KpQuestionResponse>(
      `/games/${encodeURIComponent(props.gameKey)}/kp-question`,
      {
        method: 'POST',
        body: JSON.stringify({
          question: text,
          visibility: shareWithParty.value ? 'party' : 'private',
        }),
      },
    )
    answer.value = response.answer
    if (response.visibility === 'party') emit('shared')
  } catch (cause: unknown) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Modal :title="t('kpQuestionTitle')" dialog-class="kp-question-dialog" @close="emit('close')">
    <p class="kp-question-boundary">{{ t('kpQuestionBoundary') }}</p>
    <label class="kp-question-field">
      <span>{{ t('kpQuestionLabel') }}</span>
      <textarea
        v-model="question"
        maxlength="1000"
        :disabled="busy"
        :placeholder="t('kpQuestionPlaceholder')"
        autofocus
        @keydown.ctrl.enter.prevent="submit"
      />
    </label>
    <label class="kp-question-visibility">
      <input v-model="shareWithParty" type="checkbox" :disabled="busy" />
      <span>
        <strong>{{ t('kpQuestionShare') }}</strong>
        <small>{{ shareWithParty ? t('kpQuestionPartyBoundary') : t('kpQuestionPrivateBoundary') }}</small>
      </span>
    </label>
    <div v-if="answer" class="kp-question-answer" aria-live="polite">
      <strong>{{ t('kpQuestionAnswer') }}</strong>
      <p>{{ answer }}</p>
    </div>
    <p v-if="error" class="kp-question-error" role="alert">{{ error }}</p>
    <template #actions>
      <button type="button" :disabled="busy" @click="emit('close')">{{ t('close') }}</button>
      <button type="button" class="primary" :disabled="busy || !question.trim()" @click="submit">
        {{ busy ? t('kpQuestionAsking') : t('kpQuestionSubmit') }}
      </button>
    </template>
  </Modal>
</template>

<style scoped>
.kp-question-boundary {
  margin: 0 0 14px;
  padding: 9px 11px;
  border: 1px solid color-mix(in srgb, var(--df-interactive) 30%, var(--df-border-soft));
  border-radius: var(--df-radius-md);
  color: var(--df-text-secondary);
  background: color-mix(in srgb, var(--df-interactive) 7%, var(--df-surface-1));
  font-size: 13px;
  line-height: 1.6;
}

.kp-question-field {
  display: grid;
  gap: 7px;
}

.kp-question-visibility {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin-top: 12px;
  padding: 10px 11px;
  border-radius: var(--df-radius-md);
  background: var(--df-surface-raised);
  cursor: pointer;
}

.kp-question-visibility input { margin-top: 3px; }
.kp-question-visibility span { display: grid; gap: 2px; }
.kp-question-visibility small { color: var(--df-text-secondary); line-height: 1.5; }

.kp-question-field > span,
.kp-question-answer > strong {
  color: var(--df-text);
  font-weight: 700;
}

.kp-question-field textarea {
  min-height: 110px;
  max-height: 260px;
  resize: vertical;
}

.kp-question-answer {
  margin-top: 14px;
  padding: 12px 14px;
  border-left: 3px solid var(--df-interactive);
  border-radius: var(--df-radius-md);
  background: color-mix(in srgb, var(--df-interactive) 9%, var(--df-surface-raised));
}

.kp-question-answer p {
  margin: 7px 0 0;
  color: var(--df-text);
  line-height: 1.7;
  white-space: pre-wrap;
}

.kp-question-error {
  margin: 10px 0 0;
  color: var(--df-danger-strong);
}
</style>
