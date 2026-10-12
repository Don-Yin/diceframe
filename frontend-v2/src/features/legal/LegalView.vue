<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NSpin } from 'naive-ui'
import { fetchLegalDocument, type LegalDocumentName } from '@/api/legal'
import { useLocale } from '@/composables/useLocale'
import { renderSafeMarkdown } from '@/utils/markdown'

const props = defineProps<{ document: LegalDocumentName }>()
const { locale, t } = useLocale()
const content = ref('')
const version = ref('')
const loading = ref(false)
const failed = ref(false)

const title = computed(() => t(props.document === 'terms' ? 'legalTermsTitle' : 'legalPrivacyTitle'))
const html = computed(() => renderSafeMarkdown(content.value))

async function load() {
  loading.value = true
  failed.value = false
  try {
    const result = await fetchLegalDocument(props.document, locale.value)
    content.value = result.content
    version.value = result.version
  } catch {
    failed.value = true
    content.value = ''
  } finally {
    loading.value = false
  }
}

function goBack() {
  if (window.history.length > 1) window.history.back()
  else window.location.hash = '#/overview'
}

onMounted(load)
watch(() => [props.document, locale.value], load)
</script>

<template>
  <main class="legal-page">
    <header class="legal-page-head">
      <div>
        <span>{{ t('legalDocumentLabel') }}</span>
        <h1>{{ title }}</h1>
        <small v-if="version">{{ t('legalVersionLabel', { version }) }}</small>
      </div>
      <NButton secondary @click="goBack">{{ t('back') }}</NButton>
    </header>
    <NSpin :show="loading">
      <article v-if="html" class="legal-document safe-markdown" v-html="html" />
      <section v-else-if="failed" class="legal-load-error">
        <p>{{ t('legalLoadFailed') }}</p>
        <NButton @click="load">{{ t('retry') }}</NButton>
      </section>
    </NSpin>
  </main>
</template>

<style scoped>
.legal-page {
  box-sizing: border-box;
  width: min(920px, calc(100% - 32px));
  min-height: 100vh;
  margin: 0 auto;
  padding: 34px 0 64px;
}

.legal-page-head {
  position: sticky;
  z-index: 2;
  top: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
  padding: 14px 18px;
  border: 1px solid var(--df-border-soft);
  border-radius: 10px;
  background: color-mix(in srgb, var(--df-canvas) 92%, transparent);
  backdrop-filter: blur(12px);
}

.legal-page-head span,
.legal-page-head small {
  color: var(--df-text-muted);
}

.legal-page-head h1 {
  margin: 3px 0;
  font-size: clamp(22px, 3vw, 32px);
}

.legal-document,
.legal-load-error {
  padding: clamp(20px, 4vw, 44px);
  border: 1px solid var(--df-border-soft);
  border-radius: 10px;
  background: var(--df-surface-1);
}

@media (max-width: 560px) {
  .legal-page { width: min(100% - 20px, 920px); padding-top: 10px; }
  .legal-page-head { align-items: center; padding: 12px; }
  .legal-document { padding: 18px 16px; }
}
</style>
