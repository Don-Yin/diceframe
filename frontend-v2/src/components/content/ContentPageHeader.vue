<script setup lang="ts">
defineProps<{ kicker: string; title: string; description: string; headingAriaLabel?: string }>()
</script>

<template>
  <header class="content-page-heading">
    <div class="content-page-heading-copy">
      <p class="eyebrow content-page-heading-kicker">{{ kicker }}</p>
      <div v-if="$slots['title-actions']" class="content-page-heading-title-row">
        <h1 :aria-label="headingAriaLabel">{{ title }}</h1>
        <slot name="title-actions" />
      </div>
      <h1 v-else :aria-label="headingAriaLabel">{{ title }}</h1>
      <p class="view-intro">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="content-page-heading-actions"><slot name="actions" /></div>
  </header>
</template>

<style scoped>
.content-page-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; min-width: 0; margin-bottom: 20px; padding: 12px 0 18px; border-bottom: 1px solid var(--df-border-soft); }
.content-page-heading-copy { min-width: 0; max-width: 760px; }
.content-page-heading-kicker { margin: 0 0 7px; color: var(--df-interactive-strong); font-size: 10px; font-weight: 700; letter-spacing: .16em; }
.content-page-heading-title-row { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.content-page-heading h1 { margin: 0; font: 700 clamp(28px, 3vw, 42px)/1.15 var(--df-font-title); letter-spacing: -.02em; }
.content-page-heading .view-intro { margin: 8px 0 0; max-width: 68ch; color: var(--df-text-muted); font-size: 14px; line-height: 1.55; }
.content-page-heading-actions { flex: 0 1 auto; min-width: 0; }
@media (max-width: 760px) { .content-page-heading { align-items: stretch; flex-direction: column; gap: 12px; padding-top: 8px; } .content-page-heading-actions { width: 100%; } }
</style>
