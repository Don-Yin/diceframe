<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NInput, NSelect } from 'naive-ui'
import { getAssistantAgentCapabilities, type AgentAuthorization, type AgentAuthorizationMode, type AgentCapability, type AgentTask } from '@/api/assistant'
import { assistantAuthorizationCopy } from '@/features/assistant/authorizationCopy'

const props = withDefaults(defineProps<{
  locale: string
  authorization?: AgentAuthorization | null
  task?: AgentTask | null
  pendingApproval?: boolean
  busy?: boolean
  error?: string
  disabled?: boolean
  context?: Record<string, string>
  onAuthorize?: (mode: AgentAuthorizationMode, scope?: Record<string, string>, domains?: string[], maxSteps?: number) => void | Promise<void>
  onContinue?: () => void | Promise<void>
  onReview?: () => void
}>(), { authorization: null, task: null, pendingApproval: false, busy: false, error: '', disabled: false, context: () => ({}) })
const copy = computed(() => assistantAuthorizationCopy(props.locale))
const expanded = ref(false)
const scopeMode = ref<'current' | 'all'>('current')
const maxSteps = ref(32)
const capabilityQuery = ref('')
const capabilityDomain = ref('')
const capabilities = ref<AgentCapability[]>([])
const capabilitiesBusy = ref(false)
const capabilitiesError = ref('')
let capabilityRequestId = 0
const hasContext = computed(() => Object.keys(props.context).length > 0)
const stepOptions = [8, 16, 32, 48, 64].map(value => ({ label: String(value), value }))
const domainOptions = [{ label: 'All', value: '' }, ...['application', 'lorebook', 'worlds', 'games', 'adventures', 'recovery', 'ruleset', 'settings', 'plugins'].map(value => ({ label: value, value }))]
const scope = computed(() => scopeMode.value === 'all' ? {} : props.context)
const scopeLabel = computed(() => scopeMode.value === 'all' || !hasContext.value ? copy.value.all : copy.value.current)
function toggleAuthorization() {
  expanded.value = !expanded.value
  if (props.pendingApproval) props.onReview?.()
}
const progress = computed(() => {
  if (!props.task) return ''
  const total = props.task.total_steps ? `/${props.task.total_steps}` : ''
  const tokens = typeof props.task.used_tokens === 'number' && typeof props.task.token_budget === 'number'
    ? ` · ${props.task.used_tokens}/${props.task.token_budget} tokens`
    : ''
  return `${props.task.completed_steps}${total}${tokens}`
})
async function choose(mode: AgentAuthorizationMode) {
  await props.onAuthorize?.(mode, scope.value, undefined, maxSteps.value)
  expanded.value = true
}
async function loadCapabilities() {
  const requestId = ++capabilityRequestId
  capabilitiesBusy.value = true; capabilitiesError.value = ''
  try {
    const result = await getAssistantAgentCapabilities({ q: capabilityQuery.value, domain: capabilityDomain.value })
    if (requestId === capabilityRequestId) capabilities.value = result.capabilities
  }
  catch (error: unknown) { if (requestId === capabilityRequestId) capabilitiesError.value = error instanceof Error ? error.message : copy.value.disabled }
  finally { if (requestId === capabilityRequestId) capabilitiesBusy.value = false }
}
watch(expanded, value => { if (value && !capabilities.value.length && !capabilitiesError.value) void loadCapabilities() })
watch([capabilityQuery, capabilityDomain], () => { if (expanded.value) void loadCapabilities() })
</script>

<template>
  <section class="agent-authorization" data-testid="agent-authorization">
    <button type="button" class="agent-authorization-toggle" :aria-expanded="expanded" :title="pendingApproval ? copy.reviewPending : undefined" @click="toggleAuthorization">
      <strong>{{ copy.title }}</strong>
      <span v-if="pendingApproval" class="agent-authorization-badge" :aria-label="copy.reviewPending">1</span>
      <span v-if="authorization" class="agent-authorization-state">{{ copy.active }} · {{ copy.mode(authorization.mode) }}</span>
      <span v-else class="agent-authorization-state">{{ copy.suggest }}</span>
      <span v-if="task" class="agent-authorization-state">{{ copy.taskStatus(task.status) }}</span>
      <span aria-hidden="true">{{ expanded ? '⌃' : '⌄' }}</span>
    </button>
    <div v-show="expanded" class="agent-authorization-body">
      <p>{{ copy.hint }}</p>
      <div v-if="disabled" class="agent-authorization-disabled" role="status">{{ copy.disabled }}</div>
      <template v-else>
        <div class="agent-authorization-scope">
          <label><input v-model="scopeMode" type="radio" value="current" :disabled="busy" /> {{ copy.current }} <small>{{ scopeLabel }}</small></label>
          <label><input v-model="scopeMode" type="radio" value="all" :disabled="busy" /> {{ copy.all }}</label>
        </div>
        <label class="agent-authorization-steps">{{ copy.steps }}
          <NSelect v-model:value="maxSteps" size="small" :options="stepOptions" :disabled="busy" />
        </label>
        <p class="agent-authorization-effect">{{ copy.effect(authorization?.mode || 'suggest') }}</p>
        <p v-if="authorization" class="agent-authorization-effect">
          {{ locale.startsWith('zh') ? '剩余操作' : 'Actions remaining' }} {{ authorization.remaining_steps }}/{{ authorization.max_steps }}
          · {{ locale.startsWith('zh') ? '有效至' : 'Expires' }} {{ new Date(authorization.expires_at * 1000).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) }}
        </p>
        <details class="agent-authorization-capabilities">
          <summary>{{ locale.startsWith('zh') ? '可用能力' : 'Available capabilities' }}</summary>
          <div class="agent-capability-filters">
            <NInput v-model:value="capabilityQuery" size="small" :placeholder="locale.startsWith('zh') ? '搜索能力' : 'Search capabilities'" />
            <NSelect v-model:value="capabilityDomain" size="small" :options="domainOptions" />
          </div>
          <p v-if="capabilitiesBusy">{{ locale.startsWith('zh') ? '加载中…' : 'Loading…' }}</p>
          <p v-else-if="capabilitiesError" class="agent-authorization-error" role="alert">{{ capabilitiesError }}</p>
          <ul v-else class="agent-capability-list">
            <li v-for="capability in capabilities" :key="`${capability.name}:${capability.version}`">
              <strong>{{ capability.label || capability.name }}</strong><small>{{ capability.domain }} · {{ capability.effect }}<span v-if="capability.requires_confirmation"> · {{ locale.startsWith('zh') ? '需确认' : 'confirmation required' }}</span></small>
              <span>{{ capability.description }}</span>
            </li>
            <li v-if="!capabilities.length">{{ locale.startsWith('zh') ? '没有匹配能力' : 'No matching capabilities' }}</li>
          </ul>
        </details>
        <div class="agent-authorization-actions">
          <NButton size="small" :disabled="busy" @click="choose('suggest')">{{ copy.suggest }}</NButton>
          <NButton size="small" :disabled="busy" @click="choose('routine')">{{ copy.routine }}</NButton>
          <NButton size="small" type="primary" :disabled="busy" @click="choose('task')">{{ copy.task }}</NButton>
          <NButton v-if="authorization && authorization.mode !== 'suggest'" size="small" quaternary :disabled="busy" @click="choose('suggest')">{{ copy.revoke }}</NButton>
        </div>
        <p v-if="task" class="agent-authorization-task" role="status">{{ copy.taskStatus(task.status) }} · {{ progress }}<span v-if="task.error"> · {{ task.error }}</span></p>
        <p v-if="task?.status === 'budget_reached'" class="agent-authorization-effect">{{ copy.continueHint }}</p>
        <NButton v-if="task?.status === 'budget_reached'" size="small" :disabled="busy" @click="props.onContinue?.()">{{ copy.continueTask }}</NButton>
        <p v-if="error" class="agent-authorization-error" role="alert">{{ copy.error }}: {{ error }}</p>
      </template>
    </div>
  </section>
</template>

<style scoped>
.agent-authorization { border-bottom: 1px solid var(--df-border-soft); background: var(--df-surface-1); }
.agent-authorization-toggle { display: flex; align-items: center; gap: 8px; width: 100%; min-height: 38px; padding: 7px 15px; border: 0; color: var(--df-accent-strong); background: var(--df-surface-2); text-align: start; cursor: pointer; }
.agent-authorization-toggle strong { margin-right: auto; font-size: 12px; }
.agent-authorization-badge { display: inline-grid; place-items: center; min-width: 17px; height: 17px; padding: 0 4px; border-radius: 999px; color: var(--df-on-accent); background: var(--df-danger-strong, #c94b55); font-size: 10px; font-weight: 800; }
.agent-authorization-state { color: var(--df-text-muted); font-size: 11px; }
.agent-authorization-body { display: grid; gap: 8px; max-height: min(38dvh, 300px); overflow-y: auto; overscroll-behavior: contain; padding: 9px 15px 11px; color: var(--df-text-secondary); font-size: 11px; }
.agent-authorization-body p { margin: 0; line-height: 1.45; }
.agent-authorization-scope { display: flex; flex-wrap: wrap; gap: 10px; }
.agent-authorization-scope label { display: inline-flex; align-items: center; gap: 4px; }
.agent-authorization-scope small { color: var(--df-text-muted); }
.agent-authorization-steps { display: flex; align-items: center; gap: 8px; }
.agent-authorization-steps .n-select { width: 70px; }
.agent-authorization-effect { color: var(--df-text-muted); }
.agent-authorization-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.agent-authorization-task { color: var(--df-interactive-strong); }
.agent-authorization-error, .agent-authorization-disabled { color: var(--df-danger-strong); }
.agent-authorization-capabilities { border-top: 1px solid var(--df-border-soft); padding-top: 7px; }
.agent-authorization-capabilities summary { cursor: pointer; color: var(--df-interactive-strong); }
.agent-capability-filters { display: flex; gap: 6px; margin: 7px 0; }
.agent-capability-filters .n-input { min-width: 0; flex: 1; }
.agent-capability-filters .n-select { width: 125px; }
.agent-capability-list { display: grid; gap: 5px; max-height: 150px; overflow: auto; margin: 0; padding: 0; list-style: none; }
.agent-capability-list li { display: grid; gap: 1px; padding: 5px 7px; border-radius: var(--df-radius-sm); background: color-mix(in srgb, var(--df-control-bg) 80%, transparent); }
.agent-capability-list small { color: var(--df-text-muted); }
</style>
