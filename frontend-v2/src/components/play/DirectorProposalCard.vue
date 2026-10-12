<script setup lang="ts">
import { computed } from 'vue'
import type { RulesetDirectorProposal } from '@/api/types'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{
  proposal: RulesetDirectorProposal
  isGm: boolean
}>()

const emit = defineEmits<{
  openCampaign: []
  openCombat: []
}>()

const { locale } = useLocale()
const chinese = computed(() => locale.value.startsWith('zh'))
const copy = computed(() => chinese.value ? {
  label: 'AI GM 建议',
  confidence: '判断置信度',
  gmReview: '等待 GM 确认',
  automatic: '将按当前自动化档位处理',
  campaign: '查看冒险与战役',
  combat: '打开战斗工具',
  kinds: {
    check: '需要一次检定',
    party_decision: '需要队伍共同决定',
    adventure_choice: '冒险节点有可用方向',
    combat: '剧情可能进入战斗',
    narrative: '继续叙事',
  },
} : {
  label: 'AI GM suggestion',
  confidence: 'Confidence',
  gmReview: 'Waiting for GM confirmation',
  automatic: 'Handled according to the current automation mode',
  campaign: 'Open adventure & campaign',
  combat: 'Open combat tools',
  kinds: {
    check: 'A check may be needed',
    party_decision: 'The party needs to decide together',
    adventure_choice: 'The adventure node has available directions',
    combat: 'The scene may enter combat',
    narrative: 'Continue the narrative',
  },
})

const kind = computed(() => String(props.proposal.kind || 'narrative'))
const title = computed(() => copy.value.kinds[kind.value as keyof typeof copy.value.kinds] || kind.value)
const confidence = computed(() => {
  const value = Number(props.proposal.confidence)
  return Number.isFinite(value) ? `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` : ''
})
const requiresGmReview = computed(() => props.proposal.requires_gm_confirmation !== false)
const showCampaignAction = computed(() => kind.value === 'party_decision' || kind.value === 'adventure_choice')
const showCombatAction = computed(() => kind.value === 'combat')
</script>

<template>
  <section class="director-proposal" aria-live="polite">
    <div class="director-proposal-main">
      <div class="director-proposal-heading">
        <span class="director-proposal-label">{{ copy.label }}</span>
        <strong>{{ title }}</strong>
      </div>
      <div class="director-proposal-meta">
        <span v-if="confidence">{{ copy.confidence }} {{ confidence }}</span>
        <span v-if="requiresGmReview && isGm">{{ copy.gmReview }}</span>
        <span v-else-if="proposal.mode === 'auto'">{{ copy.automatic }}</span>
      </div>
    </div>
    <div v-if="showCampaignAction || showCombatAction" class="director-proposal-actions">
      <button v-if="showCampaignAction" type="button" @click="emit('openCampaign')">{{ copy.campaign }}</button>
      <button v-if="showCombatAction" type="button" @click="emit('openCombat')">{{ copy.combat }}</button>
    </div>
  </section>
</template>

<style scoped>
.director-proposal {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin: 0 0 12px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--df-interactive) 42%, var(--df-border-soft));
  border-radius: var(--df-radius-md);
  background: color-mix(in srgb, var(--df-interactive) 9%, var(--df-surface));
}

.director-proposal-main { min-width: 0; }
.director-proposal-heading { display: flex; align-items: baseline; gap: 9px; flex-wrap: wrap; }
.director-proposal-label { color: var(--df-interactive); font-size: 11px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.director-proposal-heading strong { color: var(--df-text); font-size: 14px; }
.director-proposal-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; color: var(--df-text-tertiary); font-size: 11px; }
.director-proposal-actions { display: flex; flex: 0 0 auto; gap: 8px; }
.director-proposal-actions button { min-height: 38px; padding: 7px 11px; border: 1px solid var(--df-border); border-radius: var(--df-radius-sm); color: var(--df-text); background: var(--df-control-bg); }
.director-proposal-actions button:hover { border-color: var(--df-interactive); }

@media (max-width: 680px) {
  .director-proposal { align-items: stretch; flex-direction: column; }
  .director-proposal-actions { flex-wrap: wrap; }
  .director-proposal-actions button { flex: 1 1 180px; }
}
</style>
