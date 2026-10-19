<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import ContentPageHeader from '@/components/content/ContentPageHeader.vue'
import { useLocale } from '@/composables/useLocale'
import { creatorCopy, type CreatorCardId } from './copy'
import ContentTextReviewDialog from '@/features/content-review/ContentTextReviewDialog.vue'
import CreatorPackageExportDialog from './CreatorPackageExportDialog.vue'

const { locale } = useLocale()
const copy = computed(() => creatorCopy(locale.value))

const storyCards: CreatorCardId[] = ['adventures']
const foundationCards: CreatorCardId[] = ['worlds', 'lorebook', 'rules']
const sourceCards: CreatorCardId[] = ['modules']
const toolCards: CreatorCardId[] = ['textReview']
const textReviewOpen = ref(false)
const packageExportOpen = ref(false)
const packageCards: CreatorCardId[] = ['package']

const routeFor: Record<CreatorCardId, string> = {
  adventures: 'adventures',
  worlds: 'worlds',
  lorebook: 'lorebook',
  rules: 'rules',
  modules: 'modules',
  textReview: '', package: '',
}

const cardIndex: Record<CreatorCardId, string> = {
  adventures: '01', worlds: '02', lorebook: '03', rules: '04', modules: '05', textReview: '06', package: '07',
}
</script>

<template>
  <section class="view creator-workshop" data-testid="creator-workshop">
    <ContentPageHeader kicker="CREATOR STUDIO" :title="copy.title" :description="copy.intro" />

    <section v-for="(ids, group) in { story: storyCards, foundation: foundationCards, source: sourceCards, tools: toolCards, packaging: packageCards }" :key="group" class="creator-group">
      <header class="creator-group-heading">
        <h2>{{ group === 'story' ? copy.storyGroup : group === 'foundation' ? copy.foundationGroup : group === 'source' ? copy.sourceGroup : group === 'tools' ? copy.toolGroup : copy.cards.package.title }}</h2>
      </header>
      <div class="creator-card-grid">
        <component
          v-for="id in ids"
          :key="id"
          :is="id === 'textReview' || id === 'package' ? 'button' : RouterLink"
          class="creator-card"
          :data-testid="`creator-card-${id}`"
          v-bind="id === 'textReview' || id === 'package' ? {} : { to: { name: routeFor[id] } }"
          type="button"
          @click="id === 'textReview' ? (textReviewOpen = true) : id === 'package' ? (packageExportOpen = true) : undefined"
        >
          <span class="creator-card-index" aria-hidden="true">{{ cardIndex[id] }}</span>
          <span class="creator-card-copy">
            <strong>{{ copy.cards[id].title }}</strong>
            <span>{{ copy.cards[id].description }}</span>
          </span>
          <span class="creator-card-action">{{ copy.cards[id].action }} <span aria-hidden="true">→</span></span>
        </component>
      </div>
    </section>
    <ContentTextReviewDialog v-if="textReviewOpen" @close="textReviewOpen = false" />
    <CreatorPackageExportDialog v-if="packageExportOpen" @close="packageExportOpen = false" />
  </section>
</template>

<style scoped>
.creator-workshop { display: grid; gap: 1.7rem; }
.creator-group { display: grid; gap: .75rem; }
.creator-group-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
.creator-group-heading h2 { margin: 0; font-size: 1.05rem; }
.creator-card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .85rem; }
.creator-card { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .85rem; align-content: start; padding: 1.05rem; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-lg); color: var(--df-text); background: var(--df-surface-1); text-decoration: none; transition: border-color 120ms ease, background-color 120ms ease, transform 120ms ease; text-align: left; font: inherit; cursor: pointer; }
.creator-card:hover, .creator-card:focus-visible { border-color: var(--df-interactive); background: var(--df-surface-2); transform: translateY(-1px); }
.creator-card-index { color: var(--df-accent-strong); font: 700 .76rem/1 ui-monospace, SFMono-Regular, Consolas, monospace; }
.creator-card-copy { display: grid; gap: .4rem; min-width: 0; }
.creator-card-copy strong { font-size: 1rem; }
.creator-card-copy span { color: var(--df-text-muted); line-height: 1.5; }
.creator-card-action { grid-column: 2; color: var(--df-interactive-strong); font-size: .84rem; font-weight: 700; }
@media (max-width: 640px) {
  .creator-card-grid { grid-template-columns: 1fr; }
  .creator-card { padding: .95rem; }
}
</style>
