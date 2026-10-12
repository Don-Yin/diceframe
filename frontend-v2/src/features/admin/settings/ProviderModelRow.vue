<script setup lang="ts">
import { NIcon, NSelect } from 'naive-ui'
import { TrashOutline } from '@vicons/ionicons5'
import type { CatalogModelRoleId } from '@/utils/providerModels'

type SelectOption = {
  label: string
  value: string
  disabled?: boolean
}

defineProps<{
  modelName: string
  capabilitySummary: string
  manualValue: string
  manualOptions: SelectOption[]
  assignmentValue: CatalogModelRoleId | null
  assignmentOptions: SelectOption[]
  assignmentPlaceholder: string
  assignmentLoading: boolean
  assignmentDisabled: boolean
  assignmentTitle: string
  removeTitle: string
}>()

const emit = defineEmits<{
  'update:manualValue': [value: string]
  'update:assignmentValue': [value: CatalogModelRoleId]
  remove: []
}>()
</script>

<template>
  <article class="provider-model-row">
    <span class="provider-model-orbit"><i /><i /></span>
    <div class="provider-model-copy">
      <strong>{{ modelName }}</strong>
      <small>{{ capabilitySummary }}</small>
    </div>
    <label class="provider-model-capability">
      <span>{{ $t('modelCapabilityManual') }}</span>
      <NSelect
        size="small"
        :value="manualValue"
        :options="manualOptions"
        @update:value="emit('update:manualValue', String($event || 'auto'))"
      />
    </label>
    <div class="provider-model-assignment">
      <span>{{ $t('providerModelAssignTo') }}</span>
      <NSelect
        size="small"
        :value="assignmentValue"
        :options="assignmentOptions"
        :placeholder="assignmentPlaceholder"
        :loading="assignmentLoading"
        :disabled="assignmentDisabled"
        :title="assignmentTitle"
        @update:value="$event && emit('update:assignmentValue', $event as CatalogModelRoleId)"
      />
    </div>
    <button type="button" class="provider-model-remove" :title="removeTitle" @click="emit('remove')">
      <NIcon :component="TrashOutline" />
    </button>
  </article>
</template>
