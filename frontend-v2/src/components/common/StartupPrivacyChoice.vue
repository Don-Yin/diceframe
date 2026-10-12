<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { HubPreferences } from '@/api/types'
import { NButton, NCheckbox, NModal, NSwitch } from 'naive-ui'
import { errorMessage } from '@/api/client'
import { pluginApi } from '@/api/plugins'
import { useLocale } from '@/composables/useLocale'

const emit = defineEmits<{ settled: [] }>()
const { locale, t } = useLocale()

const show = ref(false)
const telemetryEnabled = ref(false)
const legalAccepted = ref(false)
const legalDocuments = ref<HubPreferences['legal_documents'] | null>(null)
const saving = ref(false)
const saveError = ref('')
const expandedSection = ref<'terms' | 'privacy' | ''>('')
let settled = false

function settle() {
  if (settled) return
  settled = true
  emit('settled')
}

function toggleSection(section: 'terms' | 'privacy') {
  expandedSection.value = expandedSection.value === section ? '' : section
}

async function continueStartup() {
  if (!legalAccepted.value || !legalDocuments.value) {
    saveError.value = t('startupLegalRequired')
    return
  }
  saving.value = true
  saveError.value = ''
  try {
    await pluginApi.updateHubPreferences(telemetryEnabled.value, legalDocuments.value, locale.value)
    show.value = false
    settle()
  } catch (error: unknown) {
    saveError.value = errorMessage(error) || t('startupPrivacySaveFailed')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const preferences = await pluginApi.hubPreferences(locale.value)
    if (preferences.legal_accepted && preferences.choice_made) {
      settle()
      return
    }
    legalDocuments.value = preferences.legal_documents
    legalAccepted.value = preferences.legal_accepted
    telemetryEnabled.value = preferences.choice_made
      ? preferences.telemetry_enabled
      : false
    show.value = true
  } catch {
    settle()
  }
})
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    class="startup-privacy-modal"
    :title="t('startupPrivacyTitle')"
    :mask-closable="false"
    :close-on-esc="false"
    :closable="false"
  >
    <p class="startup-privacy-intro">{{ t('startupPrivacyIntro') }}</p>

    <div class="startup-legal-links" :aria-label="t('startupLegalDetails')">
      <button type="button" @click="toggleSection('terms')">{{ t('startupTermsTitle') }}</button>
      <span aria-hidden="true">·</span>
      <button type="button" @click="toggleSection('privacy')">{{ t('startupPrivacyPolicyTitle') }}</button>
    </div>
    <section v-if="expandedSection === 'terms'" class="startup-legal-summary">
      <h3>{{ t('startupTermsTitle') }}</h3>
      <p>{{ t('startupTermsSummary') }}</p>
      <a href="/#/legal/terms" target="_blank" rel="noopener">{{ t('startupViewFullTerms') }}</a>
    </section>
    <section v-else-if="expandedSection === 'privacy'" class="startup-legal-summary">
      <h3>{{ t('startupPrivacyPolicyTitle') }}</h3>
      <p>{{ t('startupPrivacyPolicySummary') }}</p>
      <a href="/#/legal/privacy" target="_blank" rel="noopener">{{ t('startupViewFullPrivacy') }}</a>
    </section>

    <NCheckbox v-model:checked="legalAccepted" class="startup-legal-consent">
      <span>{{ t('startupLegalConsentPrefix') }}</span>
      <a href="/#/legal/terms" target="_blank" rel="noopener" @click.stop>{{ t('legalTermsTitle') }}</a>
      <span>{{ t('startupLegalConsentMiddle') }}</span>
      <a href="/#/legal/privacy" target="_blank" rel="noopener" @click.stop>{{ t('legalPrivacyTitle') }}</a>
    </NCheckbox>

    <div class="startup-telemetry-row">
      <div>
        <strong>{{ t('hubTelemetryChoiceTitle') }}</strong>
        <small>{{ t('hubTelemetryChoiceSummary') }}</small>
      </div>
      <NSwitch v-model:value="telemetryEnabled" :aria-label="t('hubTelemetryChoiceTitle')" />
    </div>

    <p v-if="saveError" class="startup-privacy-error" role="alert">{{ saveError }}</p>

    <template #footer>
      <div class="startup-privacy-footer">
        <small>{{ t('startupPrivacyChangeLater') }}</small>
        <NButton
          type="primary"
          :loading="saving"
          :disabled="!legalAccepted"
          data-testid="startup-privacy-continue"
          @click="continueStartup"
        >
          {{ t('startupContinue') }}
        </NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
:global(.startup-privacy-modal) {
  width: min(560px, calc(100vw - 28px));
}

.startup-privacy-intro {
  margin: 0;
  color: var(--df-text-secondary);
  line-height: 1.7;
}

.startup-legal-links {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 12px;
  color: var(--df-text-muted);
  font-size: 12px;
}

.startup-legal-links button {
  padding: 0;
  border: 0;
  color: var(--df-text-muted);
  background: transparent;
  font: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.startup-legal-links button:hover {
  color: var(--df-interactive-strong);
}

.startup-legal-summary {
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
  background: var(--df-surface-2);
}

.startup-legal-summary h3,
.startup-legal-summary p {
  margin: 0;
}

.startup-legal-summary a,
.startup-legal-consent a {
  color: var(--df-interactive-strong);
  text-underline-offset: 3px;
}

.startup-legal-consent {
  margin-top: 16px;
}

.startup-legal-summary h3 {
  font-size: 13px;
}

.startup-legal-summary p {
  margin-top: 6px;
  color: var(--df-text-muted);
  font-size: 12px;
  line-height: 1.65;
}

.startup-telemetry-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 18px;
  padding: 12px 14px;
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
  background: color-mix(in srgb, var(--df-surface-2) 72%, transparent);
}

.startup-telemetry-row > div {
  display: grid;
  gap: 4px;
}

.startup-telemetry-row strong {
  font-size: 13px;
}

.startup-telemetry-row small,
.startup-privacy-footer small {
  color: var(--df-text-muted);
  line-height: 1.55;
}

.startup-privacy-error {
  margin: 12px 0 0;
  color: var(--df-danger);
  font-size: 12px;
}

.startup-privacy-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

@media (max-width: 520px) {
  .startup-telemetry-row,
  .startup-privacy-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .startup-telemetry-row :deep(.n-switch) {
    align-self: flex-end;
  }
}
</style>
