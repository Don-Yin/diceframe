<script setup lang="ts">
import { NButton, NInput, NSelect } from 'naive-ui'
import type { TestResult } from '@/api/types'
import type { ProviderTestKind } from '@/utils/providerModels'
import { useLocale } from '@/composables/useLocale'
import TestResultCard from '@/components/admin/TestResultCard.vue'

defineProps<{
  modelValue: string
  modelPlaceholder: string
  modeValue: string
  modeOptions: Array<{ label: string; value: string }>
  actionLabel: string
  testing: boolean
  saving: boolean
  canSave: boolean
  showResult: boolean
  result: TestResult | null
  resultKind: ProviderTestKind
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:modeValue': [value: string]
  test: []
  save: []
  remove: []
}>()

const { t } = useLocale()
</script>

<template>
  <section class="provider-editor-section provider-test-section">
    <label class="provider-field">
      <span>{{ t('providerTestModel') }}</span>
      <NInput
        size="large"
        :value="modelValue"
        :placeholder="modelPlaceholder"
        @update:value="emit('update:modelValue', String($event))"
      />
    </label>
    <label class="provider-field">
      <span>{{ t('providerTestType') }}</span>
      <NSelect
        size="large"
        :value="modeValue"
        :options="modeOptions"
        @update:value="emit('update:modeValue', String($event || 'auto'))"
      />
    </label>
    <div class="provider-test-actions">
      <NButton size="large" :loading="testing" @click="emit('test')">{{ actionLabel }}</NButton>
      <NButton size="large" type="primary" :loading="saving" :disabled="!canSave" @click="emit('save')">
        {{ t('providerSave') }}
      </NButton>
      <NButton size="large" quaternary type="error" @click="emit('remove')">
        {{ t('providerRemove') }}
      </NButton>
    </div>
    <TestResultCard v-if="showResult && result" :result="result" :kind="resultKind" />
  </section>
</template>
