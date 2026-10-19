<script setup lang="ts">
import type { CharacterCard } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import { characterCardNeedsConversion, characterCardRuleName } from '@/utils/characterCards'
import PortraitImage from '@/components/PortraitImage.vue'
import Modal from '@/components/ui/Modal.vue'

defineProps<{ cards: CharacterCard[]; targetRuleId?: string }>()
const emit = defineEmits<{ pick: [card: CharacterCard]; close: [] }>()
const { t } = useLocale()
</script>

<template>
  <Modal :title="t('chooseCharacterCard')" dialog-class="character-card-picker-dialog" close-on-backdrop @close="emit('close')">
    <p class="character-card-picker-intro">{{ t('chooseCharacterCardHelp') }}</p>
    <div class="character-card-picker-list">
      <button
        v-for="c in cards"
        :key="c.card_id || c.character_name"
        type="button"
        class="card-choice"
        :class="{ 'rule-mismatch': characterCardNeedsConversion(c, targetRuleId) }"
        @click="emit('pick', c)"
      >
        <PortraitImage :portrait="c.portrait" :rule-id="c.rule_id || targetRuleId" :seed="String(c.card_id || c.id || c.character_name)" :name="c.character_name" :size="48" />
        <span class="card-choice-copy">
          <strong>{{ c.character_name }}</strong>
          <span>{{ [characterCardRuleName(c, t('unboundRule')), c.race, c.class].filter(Boolean).join(' · ') }}</span>
          <small v-if="characterCardNeedsConversion(c, targetRuleId)">{{ t('cardNeedsRuleConversion') }}</small>
        </span>
      </button>
      <p v-if="!cards.length" class="muted">{{ t('characterLibraryEmpty') }}</p>
    </div>
  </Modal>
</template>

<style scoped>
:global(.dialog.character-card-picker-dialog) {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: min(760px, calc(100dvh - 32px));
  overflow: hidden;
}
:global(.character-card-picker-dialog > header) { flex: 0 0 auto; }
.character-card-picker-intro { flex: 0 0 auto; margin: 0; color: var(--df-text-muted); line-height: 1.5; }
.character-card-picker-list {
  display: grid;
  grid-auto-rows: min-content;
  align-content: start;
  gap: 8px;
  min-height: 0;
  padding: 2px 4px 2px 2px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.card-choice {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  align-items: center;
  justify-content: stretch;
  gap: 12px;
  width: 100%;
  min-width: 0;
  min-height: 82px;
  margin: 0;
  padding: 10px 12px;
  text-align: left;
}
.card-choice-copy { display: grid; gap: 2px; min-width: 0; line-height: 1.5; overflow-wrap: anywhere; }
.card-choice-copy strong { font-size: 14px; }
.card-choice-copy > span, .card-choice-copy small { font-size: 12px; }
</style>
