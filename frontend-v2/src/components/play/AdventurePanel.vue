<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import { submitRulesetIntent } from '@/api/rulesets'
import { useLocale } from '@/composables/useLocale'
import { X } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import AdventureNodeActions from '@/features/adventures/AdventureNodeActions.vue'

type AdventureNode = {
  id: string
  type: string
  chapter_id?: string | null
  name?: string
  description?: string
  optional?: boolean
  scene_ref?: string | null
  encounter_ref?: string | null
  npc_refs?: string[]
  choice_mode?: string
  transitions?: Array<{ to: string; choice_id?: string; choice_label?: string }>
}
type AdventureGraph = {
  chapters: Array<{ id: string; name?: string }>
  nodes: AdventureNode[]
  objectives: Array<{ id: string; name?: string; node_ids?: string[] }>
  milestones: Array<{ id: string; name?: string; node_ids?: string[] }>
  progress?: {
    active_nodes?: string[]
    selected_choices?: Record<string, string>
    choice_requests?: Array<{ node_id: string; choice_id: string; actor_uid: string }>
    completion_suggestions?: AdventureCompletionSuggestion[]
  }
}
type AdventureCompletionSuggestion = {
  proposal_id: string
  node_id: string
  reason: string
  evidence_rounds?: number[]
}
type AdventureResponse = {
  adventure: null | {
    binding?: {
      adventure_id?: string
      version?: string
      format?: string
      content_digest?: string
      source_kind?: string
      source_id?: string
    }
    available: boolean
    reason?: string
    format?: string
    projection?: AdventureGraph | null
  }
}

const props = defineProps<{ gameKey: string; isGm: boolean; refreshKey?: string | number }>()
const emit = defineEmits<{ completed: [] }>()
const { t } = useLocale()
const router = useRouter()
const loading = ref(false)
const error = ref('')
const adventure = ref<AdventureResponse['adventure']>(null)
const completingNodeId = ref('')
const open = ref(false)
const ignoringSuggestionId = ref('')
const activeToastProposalId = ref('')
const dismissedToastIds = new Set<string>()
const seenToastIds = new Set<string>()
let loadSequence = 0

const graph = computed(() => adventure.value?.projection || null)
const chapters = computed(() => graph.value?.chapters || [])
const pendingSuggestions = computed(() => (
  props.isGm ? graph.value?.progress?.completion_suggestions || [] : []
))
const activeToastSuggestion = computed(() => pendingSuggestions.value.find(
  suggestion => suggestion.proposal_id === activeToastProposalId.value,
) || null)
const activeNodeIds = computed(() => new Set(
  (graph.value?.progress?.active_nodes || []).filter(nodeId => typeof nodeId === 'string'),
))
const ungroupedNodes = computed(() => (
  graph.value?.nodes.filter(node => !node.chapter_id) || []
))
function nodesFor(chapterId: string): AdventureNode[] {
  return graph.value?.nodes.filter(node => node.chapter_id === chapterId) || []
}
function nodeLabel(node: AdventureNode): string {
  return node.name || node.id
}
function nodeKindLabel(type: string): string {
  const labels: Record<string, string> = {
    scene: t('adventureNode_scene'), objective: t('adventureNode_objective'),
    encounter: t('adventureNode_encounter'), decision: t('adventureNode_decision'),
    milestone: t('adventureNode_milestone'), reference: t('adventureNode_reference'),
  }
  return labels[type] || type
}
const unavailableReason = computed(() => (
  adventure.value?.reason === 'binding_changed'
    ? t('adventurePanelReason_binding_changed')
    : adventure.value?.reason === 'package_invalid'
      ? t('adventurePanelReason_package_invalid')
      : t('adventurePanelReason_package_unavailable')
))
function linkedNames(ids: string[] | undefined): string {
  if (!ids?.length) return t('adventureNoLinkedNodes')
  const labels = new Map((graph.value?.nodes || []).map(node => [node.id, nodeLabel(node)]))
  return ids.map(id => labels.get(id) || id).join(' · ')
}
function isActiveNode(nodeId: string): boolean {
  return activeNodeIds.value.has(nodeId)
}
async function completeNode(nodeId: string, choiceId?: string): Promise<void> {
  if ((!props.isGm && !choiceId) || !isActiveNode(nodeId) || completingNodeId.value) return
  completingNodeId.value = nodeId
  error.value = ''
  try {
    await submitRulesetIntent(props.gameKey, {
      type: props.isGm ? 'adventure.node.complete' : 'adventure.choice.request',
      node_id: nodeId,
      ...(choiceId ? { choice_id: choiceId } : {}),
    })
    await load()
    emit('completed')
  } catch (caught: unknown) {
    error.value = caught instanceof Error ? caught.message : String(caught || t('operationFailed'))
  } finally {
    completingNodeId.value = ''
  }
}
function nodeLabelForSuggestion(nodeId: string): string {
  return graph.value?.nodes.find(node => node.id === nodeId)?.name || nodeId
}
function showNextSuggestionToast(): void {
  if (activeToastProposalId.value) return
  const next = pendingSuggestions.value.find(item => (
    !seenToastIds.has(item.proposal_id) && !dismissedToastIds.has(item.proposal_id)
  ))
  if (!next) return
  seenToastIds.add(next.proposal_id)
  activeToastProposalId.value = next.proposal_id
}
function closeSuggestionToast(showNext = true): void {
  if (activeToastProposalId.value) dismissedToastIds.add(activeToastProposalId.value)
  activeToastProposalId.value = ''
  if (showNext && !open.value) showNextSuggestionToast()
}
function openSuggestionFromToast(): void {
  closeSuggestionToast(false)
  open.value = true
}
async function ignoreSuggestion(proposalId: string): Promise<void> {
  if (!props.isGm || !proposalId || ignoringSuggestionId.value) return
  ignoringSuggestionId.value = proposalId
  error.value = ''
  try {
    await submitRulesetIntent(props.gameKey, {
      type: 'adventure.completion_suggestion.dismiss',
      proposal_id: proposalId,
    })
    dismissedToastIds.add(proposalId)
    if (activeToastProposalId.value === proposalId) activeToastProposalId.value = ''
    await load()
  } catch (caught: unknown) {
    error.value = caught instanceof Error ? caught.message : String(caught || t('operationFailed'))
  } finally {
    ignoringSuggestionId.value = ''
  }
}
function openModuleRecovery(): void {
  const binding = adventure.value?.binding || {}
  // §8 Recovery：把**存档里的绑定身份**（版本 / 内容指纹 / 来源）与对局一起交给
  // 模组库，恢复页才能校验"同 id 但不同 package"并回到本局。
  void router.push({
    name: 'modules',
    query: {
      adventure: binding.adventure_id || '',
      version: binding.version || '',
      digest: binding.content_digest || '',
      source_kind: binding.source_kind || '',
      source_id: binding.source_id || '',
      game: props.gameKey || '',
    },
  })
}

async function load(): Promise<void> {
  if (!props.gameKey) return
  const sequence = ++loadSequence
  const gameKey = props.gameKey
  loading.value = true
  error.value = ''
  try {
    const response = await api<AdventureResponse>(`/games/${encodeURIComponent(gameKey)}/adventure`)
    if (sequence === loadSequence) adventure.value = response.adventure || null
  } catch (caught: unknown) {
    if (sequence === loadSequence) {
      adventure.value = null
      error.value = caught instanceof Error ? caught.message : String(caught || t('operationFailed'))
    }
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

watch(
  () => [props.gameKey, props.refreshKey] as const,
  ([gameKey], [previousGameKey]) => {
    if (gameKey !== previousGameKey) {
      open.value = false
      activeToastProposalId.value = ''
      dismissedToastIds.clear()
      seenToastIds.clear()
    }
    void load()
  },
)
watch(() => pendingSuggestions.value.map(item => item.proposal_id), proposalIds => {
  if (activeToastProposalId.value && !proposalIds.includes(activeToastProposalId.value)) {
    activeToastProposalId.value = ''
  }
  showNextSuggestionToast()
})
onMounted(() => { void load() })
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="isGm && activeToastSuggestion"
      class="adventure-suggestion-toast"
      data-testid="adventure-suggestion-toast"
      :data-proposal-id="activeToastProposalId"
      role="status"
      aria-live="polite"
    >
      <div class="adventure-suggestion-toast-copy">
        <strong>{{ t('adventureSuggestionToastTitle') }}</strong>
        <span>{{ t('adventureSuggestionToastBody', { node: nodeLabelForSuggestion(activeToastSuggestion.node_id) }) }}</span>
      </div>
      <button class="adventure-suggestion-toast-view" type="button" @click="openSuggestionFromToast">{{ t('adventureSuggestionView') }}</button>
      <button class="adventure-suggestion-toast-close" type="button" :aria-label="t('adventureSuggestionCloseToast')" :title="t('adventureSuggestionCloseToast')" data-testid="adventure-suggestion-toast-close" @click="closeSuggestionToast()"><X :size="16" aria-hidden="true" /></button>
    </aside>
  </Teleport>
  <button
    class="adventure-panel-trigger"
    data-testid="adventure-panel-toggle"
    type="button"
    aria-haspopup="dialog"
    :aria-expanded="open"
    :aria-label="pendingSuggestions.length ? t('adventureSuggestionBadgeLabel', { count: pendingSuggestions.length }) : undefined"
    @click="open = true"
  >
    {{ t('adventurePanelTitle') }}
    <span v-if="pendingSuggestions.length" class="adventure-suggestion-badge" data-testid="adventure-suggestion-badge" aria-hidden="true">{{ pendingSuggestions.length }}</span>
  </button>
  <Modal v-if="open" :title="t('adventurePanelTitle')" dialog-class="adventure-panel-dialog" close-test-id="adventure-panel-close" close-on-backdrop @close="open = false">
    <div class="adventure-panel-tools">
      <span class="eyebrow">{{ isGm ? t('adventureGmEyebrow') : t('adventurePlayerEyebrow') }}</span>
      <button class="text-button" type="button" :disabled="loading" @click="load">{{ t('refresh') }}</button>
    </div>
    <section class="adventure-panel-body" data-testid="game-adventure-panel" :aria-busy="loading">
      <p v-if="loading" class="muted">{{ t('adventurePanelLoading') }}</p>
      <p v-else-if="error" class="error-copy">{{ error }}</p>
      <template v-else-if="!adventure">
        <p class="muted">{{ t('adventurePanelNone') }}</p>
        <p class="muted">{{ t('adventurePanelFreeformHint') }}</p>
      </template>
      <template v-else-if="!adventure.available">
        <p class="error-copy">{{ t('adventurePanelUnavailable') }}</p>
        <p class="muted">{{ unavailableReason }}</p>
        <p class="muted adventure-binding">{{ t('adventureRecoveryRequired', { adventure: adventure.binding?.adventure_id || '', version: adventure.binding?.version || '' }) }}</p>
        <button class="primary recovery-button" type="button" @click="openModuleRecovery">{{ t('adventureRecoveryOpenModules') }}</button>
      </template>
      <template v-else-if="!graph">
        <p class="muted">{{ t('adventurePanelLegacy') }}</p>
      </template>
      <template v-else>
        <p class="muted adventure-binding">
          {{ adventure.binding?.adventure_id }} · {{ adventure.binding?.version }}
        </p>
        <section v-if="isGm && pendingSuggestions.length" class="adventure-suggestions" data-testid="adventure-completion-suggestions" aria-labelledby="adventure-suggestions-title">
          <h4 id="adventure-suggestions-title">{{ t('adventureSuggestionsTitle', { count: pendingSuggestions.length }) }}</h4>
          <article v-for="suggestion in pendingSuggestions" :key="suggestion.proposal_id" class="adventure-suggestion">
            <div class="adventure-suggestion-heading">
              <strong>{{ nodeLabelForSuggestion(suggestion.node_id) }}</strong>
              <span>{{ t('adventureSuggestionNeedsReview') }}</span>
            </div>
            <p>{{ suggestion.reason }}</p>
            <p v-if="suggestion.evidence_rounds?.length" class="muted adventure-suggestion-evidence">
              {{ t('adventureSuggestionEvidence', { rounds: suggestion.evidence_rounds.map(round => t('roundLabel', { round })).join(' · ') }) }}
            </p>
            <button class="text-button adventure-suggestion-ignore" type="button" :disabled="Boolean(ignoringSuggestionId) || loading" :data-testid="suggestion.proposal_id === pendingSuggestions[0]?.proposal_id ? 'adventure-suggestion-ignore' : undefined" @click="ignoreSuggestion(suggestion.proposal_id)">
              {{ ignoringSuggestionId === suggestion.proposal_id ? t('adventureSuggestionIgnoring') : t('adventureSuggestionIgnore') }}
            </button>
          </article>
        </section>
        <section v-for="chapter in chapters" :key="chapter.id" class="adventure-chapter">
          <h4>{{ chapter.name || chapter.id }}</h4>
          <article v-for="node in nodesFor(chapter.id)" :key="node.id" class="adventure-node">
            <div class="adventure-node-heading">
              <strong>{{ nodeLabel(node) }}</strong>
              <span>{{ nodeKindLabel(node.type) }}</span>
            </div>
            <p v-if="node.description">{{ node.description }}</p>
            <p v-if="node.scene_ref" class="muted">{{ t('adventureSceneRef', { ref: node.scene_ref }) }}</p>
            <p v-if="node.encounter_ref" class="muted">{{ t('adventureEncounterRef', { ref: node.encounter_ref }) }}</p>
            <p v-if="node.transitions?.length" class="muted">{{ t('adventureNextNodes', { nodes: linkedNames(node.transitions.map(item => item.to)) }) }}</p>
            <AdventureNodeActions :node="node" :is-gm="isGm" :active="isActiveNode(node.id)" :busy="loading || Boolean(completingNodeId)" :requests="graph.progress?.choice_requests" :selected="graph.progress?.selected_choices?.[node.id]" @submit="completeNode(node.id, $event)" />
          </article>
        </section>
        <section v-if="ungroupedNodes.length" class="adventure-chapter">
          <h4>{{ t('adventureUnsortedNodes') }}</h4>
          <article v-for="node in ungroupedNodes" :key="node.id" class="adventure-node">
            <div class="adventure-node-heading"><strong>{{ nodeLabel(node) }}</strong><span>{{ nodeKindLabel(node.type) }}</span></div>
            <p v-if="node.description">{{ node.description }}</p>
            <AdventureNodeActions :node="node" :is-gm="isGm" :active="isActiveNode(node.id)" :busy="loading || Boolean(completingNodeId)" :requests="graph.progress?.choice_requests" :selected="graph.progress?.selected_choices?.[node.id]" @submit="completeNode(node.id, $event)" />
          </article>
        </section>
        <section v-if="graph.objectives.length || graph.milestones.length" class="adventure-goals">
          <h4>{{ t('adventureGoals') }}</h4>
          <p v-for="objective in graph.objectives" :key="objective.id"><strong>{{ objective.name || objective.id }}</strong> — {{ linkedNames(objective.node_ids) }}</p>
          <p v-for="milestone in graph.milestones" :key="milestone.id"><strong>{{ milestone.name || milestone.id }}</strong> — {{ linkedNames(milestone.node_ids) }}</p>
        </section>
      </template>
    </section>
  </Modal>
</template>

<style scoped>
.adventure-panel-trigger { white-space: nowrap; display: inline-flex; align-items: center; gap: 7px; }
.adventure-suggestion-badge { display: inline-grid; place-items: center; min-width: 18px; height: 18px; padding: 0 4px; box-sizing: border-box; border-radius: 999px; background: var(--df-danger); color: var(--df-on-danger, #fff); font-size: .7rem; line-height: 1; font-weight: 700; }
.adventure-suggestion-toast { position: fixed; z-index: 1200; top: max(16px, env(safe-area-inset-top)); right: max(16px, env(safe-area-inset-right)); display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 10px; width: min(410px, calc(100vw - 32px)); box-sizing: border-box; padding: 12px 10px 12px 14px; border: 1px solid var(--df-border-strong, var(--df-border)); border-left: 3px solid var(--df-accent-strong); border-radius: 6px; background: var(--df-surface-raised, var(--df-surface)); color: var(--df-text); box-shadow: 0 8px 28px rgb(0 0 0 / 22%); }
.adventure-suggestion-toast-copy { min-width: 0; display: grid; gap: 3px; }
.adventure-suggestion-toast-copy strong { font-size: .84rem; }
.adventure-suggestion-toast-copy span { color: var(--df-text-secondary); font-size: .78rem; line-height: 1.35; overflow-wrap: anywhere; }
.adventure-suggestion-toast-view, .adventure-suggestion-toast-close { min-height: 32px; border: 0; cursor: pointer; }
.adventure-suggestion-toast-view { padding: 0 8px; background: transparent; color: var(--df-interactive-strong); font-size: .78rem; font-weight: 650; white-space: nowrap; }
.adventure-suggestion-toast-close { width: 32px; padding: 0; background: transparent; color: var(--df-text-muted); font-size: 1.25rem; line-height: 1; }
:global(.dialog.adventure-panel-dialog) { display: flex; flex-direction: column; gap: 12px; box-sizing: border-box; width: min(680px, 100%); max-height: calc(100dvh - 32px); overflow: hidden; }
:global(.dialog.adventure-panel-dialog > header) { flex-shrink: 0; }
.adventure-panel-tools { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-shrink: 0; }
.adventure-panel-body { display: grid; gap: 12px; flex: 1 1 auto; min-height: 0; overflow: auto; overscroll-behavior: contain; padding-right: 4px; }
.adventure-panel-body h4, .adventure-panel-body p { margin: 0; }
.adventure-panel-body h4 { font-size: .86rem; color: var(--df-text-secondary); }
.eyebrow { color: var(--df-accent-strong); font-size: .72rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.text-button { border: 0; background: transparent; color: var(--df-interactive-strong); cursor: pointer; }
.adventure-binding { font-size: .78rem; overflow-wrap: anywhere; }
.adventure-chapter, .adventure-goals, .adventure-suggestions { display: grid; gap: 8px; }
.adventure-suggestions { padding-bottom: 10px; border-bottom: 1px solid var(--df-border); }
.adventure-suggestion { display: grid; gap: 6px; padding: 10px; border: 1px solid var(--df-border); border-radius: 4px; background: var(--df-surface); }
.adventure-suggestion-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.adventure-suggestion-heading span { color: var(--df-text-muted); font-size: .72rem; }
.adventure-suggestion p { font-size: .82rem; line-height: 1.45; overflow-wrap: anywhere; }
.adventure-suggestion .adventure-suggestion-evidence { font-size: .76rem; }
.adventure-suggestion-ignore { justify-self: end; padding: 4px 2px; }
.adventure-node { border-left: 2px solid var(--df-accent); padding-left: 10px; display: grid; gap: 5px; }
.adventure-node-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.adventure-node-heading span { color: var(--df-text-muted); font-size: .75rem; }
.adventure-node p, .adventure-goals p { font-size: .82rem; line-height: 1.45; overflow-wrap: anywhere; }
.error-copy { color: var(--df-danger); }
@media (max-width: 480px) {
  .adventure-suggestion-toast { top: max(10px, env(safe-area-inset-top)); right: max(10px, env(safe-area-inset-right)); width: min(410px, calc(100vw - 20px)); gap: 6px; padding: 10px 6px 10px 10px; }
  .adventure-suggestion-toast-view { padding: 0 4px; font-size: .74rem; }
  .adventure-suggestion-toast-close { width: 28px; }
  :global(.dialog.adventure-panel-dialog) { padding: 14px; }
  .adventure-node { padding-left: 8px; }
  .adventure-node-heading { align-items: flex-start; flex-direction: column; gap: 2px; }
  .recovery-button { width: 100%; min-height: 40px; }
}
</style>
