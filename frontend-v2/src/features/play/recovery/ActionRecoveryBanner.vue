<script setup lang="ts">
import { computed } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { actionRecoveryCopy } from './copy'

const props = defineProps<{ message: string; requiresRefresh: boolean }>()
const emit = defineEmits<{ refresh: []; focus: [] }>()
const { locale } = useLocale()
const copy = computed(() => actionRecoveryCopy[locale.value] || actionRecoveryCopy.en)
</script>

<template>
  <div class="action-recovery-bar" data-testid="action-recovery" role="alert" aria-live="polite">
    <p>{{ props.message }}</p>
    <div class="action-recovery-actions">
      <button v-if="props.requiresRefresh" type="button" data-testid="action-recovery-refresh" @click="emit('refresh')">{{ copy.refresh }}</button>
      <button v-else type="button" data-testid="action-recovery-focus" @click="emit('focus')">{{ copy.edit }}</button>
    </div>
  </div>
</template>

<style scoped>
.action-recovery-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--df-accent) 48%, var(--df-border-soft));
  border-left: 3px solid var(--df-accent);
  border-radius: var(--df-radius-md);
  color: var(--df-text-secondary);
  background: color-mix(in srgb, var(--df-accent) 9%, var(--df-surface-2));
}

.action-recovery-bar p {
  min-width: 0;
  margin: 0;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.action-recovery-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 6px;
}

.action-recovery-actions button {
  min-height: 34px;
  white-space: nowrap;
}

@media (max-width: 560px) {
  .action-recovery-bar {
    flex-direction: column;
  }

  .action-recovery-actions,
  .action-recovery-actions button {
    width: 100%;
  }
}
</style>
