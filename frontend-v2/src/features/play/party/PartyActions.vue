<script setup lang="ts">
import { computed, ref } from 'vue'
import type { GameDetail, Player } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import { hasRulesetRestCenter } from '@/features/rulesets/registry'
import ManualRollsPanel from '@/features/play/manual-rolls/ManualRollsPanel.vue'

const props = defineProps<{
  gameKey: string; detail: GameDetail; players: Player[]; player?: Player
  actorId: string; isGm: boolean; preview?: boolean; delegate?: boolean
}>()
const emit = defineEmits<{ rest: [] }>()
const { t } = useLocale()
const rollsAvailable = ref(false)
const restAvailable = computed(() => Boolean(
  props.player && props.player.user_id === props.actorId
  && (!props.preview || props.delegate)
  && props.detail.ruleset_runtime?.capabilities.character_lifecycle === 'rules_aware'
  && hasRulesetRestCenter(props.detail.ruleset_runtime.id),
))
const rest = computed(() => props.detail.rest_session)
const restSubmitted = computed(() => rest.value?.participants.some(row => row.user_id === props.actorId && row.status === 'submitted'))
</script>

<template>
  <section v-show="restAvailable || rollsAvailable" class="party-actions" data-testid="party-actions" :aria-label="t('partyActions')">
    <h3>{{ t('partyActions') }}</h3>
    <div v-if="restAvailable" class="party-actions__rest">
      <p v-if="rest?.active" class="party-actions__progress" role="status">
        <strong>{{ rest.rest === 'long' ? t('partyLongRest') : t('partyShortRest') }}</strong>
        <span>{{ t('partyRestProgress', { ready: rest.ready_count, total: rest.active_count }) }}</span>
      </p>
      <button type="button" data-testid="party-rest" @click="emit('rest')">{{ rest?.active ? restSubmitted ? t('viewPartyRest') : t('joinPartyRest') : t('partyRest') }}</button>
    </div>
    <ManualRollsPanel
      :game-key="gameKey" :run-id="String(detail.run_id || '')" :actor-id="actorId" :is-gm="isGm"
      :preview="preview" :delegate="delegate" :players="players"
      :last-activity="typeof detail.last_activity === 'string' ? detail.last_activity : undefined"
      @availability="rollsAvailable = $event"
    />
  </section>
</template>

<style scoped>
.party-actions { display: grid; min-width: 0; gap: 8px; padding: 12px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-md); background: color-mix(in srgb, var(--df-surface-1) 88%, transparent); }
.party-actions h3 { margin: 0; font: 700 13px var(--df-font-title); color: var(--df-text); }
.party-actions__rest { display: grid; min-width: 0; gap: 7px; }
.party-actions button { width: 100%; min-height: 34px; padding: 7px 9px; font-size: 12px; }
.party-actions__progress { display: grid; gap: 3px; margin: 0; color: var(--df-text-secondary); font-size: 11px; }
.party-actions__progress strong { color: var(--df-accent-strong); }
</style>
