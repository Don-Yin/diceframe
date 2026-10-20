<script setup lang="ts">
import { computed } from 'vue'
import type { AgentApproval } from '@/api/assistant'

type RecordValue = Record<string, unknown>
type ExecutionStatus = 'succeeded' | 'failed' | 'not_executed' | string

interface Props {
  approval?: AgentApproval | null
  result?: unknown
  locale?: string
}

const props = withDefaults(defineProps<Props>(), { approval: null, result: undefined, locale: 'en' })

function record(value: unknown): RecordValue {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {}
}

function count(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (Array.isArray(value)) return value.length
  return undefined
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function sourceResult(value: unknown): RecordValue {
  const outer = record(value)
  const nested = record(outer.result)
  return Object.keys(nested).length ? nested : outer
}

const preview = computed(() => record(props.approval?.preview))
const previewSummary = computed(() => {
  const nested = record(preview.value.summary)
  return Object.keys(nested).length ? nested : preview.value
})
const response = computed(() => sourceResult(props.result))
const executionState = computed(() => record(props.approval?.execution_state))
const report = computed(() => {
  const stateReport = record(executionState.value.report)
  if (Object.keys(stateReport).length) return stateReport
  const responseReport = record(response.value.report)
  if (Object.keys(responseReport).length) return responseReport
  return response.value
})

function targetId(value: unknown): string {
  const item = record(value)
  return text(item.id) || text(item.target_id) || text(item.book_id) || text(item.key)
}

function targetLabel(value: unknown): string {
  const item = record(value)
  return text(item.label) || text(item.name) || targetId(item) || (props.locale.startsWith('zh') ? '未命名目标' : 'Unnamed target')
}

const targets = computed(() => {
  const rows = new Map<string, RecordValue>()
  const previewTargets = Array.isArray(preview.value.targets) ? preview.value.targets : []
  for (const raw of previewTargets) {
    const item = record(raw)
    const id = targetId(item) || `target-${rows.size}`
    rows.set(id, { ...item, id, label: targetLabel(item), __execution: false })
  }
  const reportTargets = Array.isArray(report.value.targets) ? report.value.targets : []
  for (const raw of reportTargets) {
    const item = record(raw)
    const id = targetId(item) || `target-${rows.size}`
    rows.set(id, { ...(rows.get(id) || {}), ...item, id, label: targetLabel({ ...(rows.get(id) || {}), ...item }), __execution: true })
  }
  return [...rows.values()]
})

const summary = computed(() => {
  const source = Object.keys(report.value).length ? report.value : previewSummary.value
  return {
    total: count(source.total) ?? count(previewSummary.value.total),
    changed: count(source.changed_count) ?? count(previewSummary.value.changed_count),
    books: count(source.book_count) ?? count(previewSummary.value.book_count) ?? (targets.value.length || undefined),
    games: count(source.affected_games) ?? count(previewSummary.value.affected_games),
    succeeded: count(source.success_count),
    failed: count(source.failed_count),
    notExecuted: count(source.not_executed_count),
    unconfirmed: count(source.unconfirmed_count),
  }
})

const status = computed(() => text(report.value.status) || text(props.approval?.execution_status))
const audience = computed(() => {
  const value = text(preview.value.audience)
  const zh = props.locale.startsWith('zh')
  return ({ gm: zh ? '主持人' : 'GM', public: zh ? '公开' : 'Public', characters: zh ? '角色' : 'Characters' } as Record<string, string>)[value] || value
})
const isBatch = computed(() => targets.value.length > 0)
const hasExecution = computed(() => targets.value.some(item => item.__execution))

function statusLabel(value: ExecutionStatus): string {
  const zh = props.locale.startsWith('zh')
  return ({
    succeeded: zh ? '已完成' : 'Completed',
    failed: zh ? '失败' : 'Failed',
    not_executed: zh ? '未执行' : 'Not executed',
    unconfirmed: zh ? '待回执核对' : 'Awaiting receipt',
    completed: zh ? '已完成' : 'Completed',
    partial: zh ? '部分完成' : 'Partially completed',
    cancelled: zh ? '已取消' : 'Cancelled',
    pending: zh ? '等待中' : 'Pending',
    running: zh ? '执行中' : 'Running',
    interrupted: zh ? '已中断' : 'Interrupted',
    failed_plan: zh ? '失败' : 'Failed',
  } as Record<string, string>)[value] || value
}

function targetStatus(item: RecordValue): string {
  return statusLabel(text(item.status) || 'pending')
}

function countLabel(value: number | undefined, label: string): string {
  return value === undefined ? '' : `${label} ${value}`
}
</script>

<template>
  <section v-if="isBatch" class="agent-execution-summary" data-testid="agent-execution-summary">
    <div class="agent-execution-heading">
      <strong>{{ locale.startsWith('zh') ? '执行计划' : 'Execution plan' }}</strong>
      <span v-if="status" class="agent-execution-status" :class="`status-${status}`">{{ statusLabel(status) }}</span>
      <span v-if="audience" class="agent-execution-audience">{{ audience }}</span>
    </div>
    <div class="agent-execution-counts" aria-label="execution counts">
      <span v-if="summary.total !== undefined">{{ countLabel(summary.total, locale.startsWith('zh') ? '目标总数' : 'Total') }}</span>
      <span v-if="summary.changed !== undefined">{{ countLabel(summary.changed, locale.startsWith('zh') ? (hasExecution ? '已变更' : '计划修改') : (hasExecution ? 'Changed' : 'Planned changes')) }}</span>
      <span v-if="summary.books !== undefined">{{ countLabel(summary.books, locale.startsWith('zh') ? '资料册' : 'Books') }}</span>
      <span v-if="summary.games !== undefined">{{ countLabel(summary.games, locale.startsWith('zh') ? '影响游戏' : 'Games') }}</span>
      <span v-if="summary.succeeded !== undefined">{{ countLabel(summary.succeeded, locale.startsWith('zh') ? '成功' : 'Succeeded') }}</span>
      <span v-if="summary.failed !== undefined">{{ countLabel(summary.failed, locale.startsWith('zh') ? '失败' : 'Failed') }}</span>
      <span v-if="summary.notExecuted !== undefined">{{ countLabel(summary.notExecuted, locale.startsWith('zh') ? '未执行' : 'Not executed') }}</span>
      <span v-if="summary.unconfirmed">{{ countLabel(summary.unconfirmed, locale.startsWith('zh') ? '待回执核对' : 'Awaiting receipt') }}</span>
    </div>
    <details v-if="targets.length" class="agent-execution-targets" open>
      <summary>{{ locale.startsWith('zh') ? `目标（${targets.length}）` : `Targets (${targets.length})` }}</summary>
      <ul>
        <li v-for="item in targets" :key="String(item.id)" :data-testid="`agent-execution-target-${String(item.id)}`" :class="`target-${String(item.status || '')}`">
          <span class="agent-execution-target-label">{{ String(item.label) }}</span>
          <span class="agent-execution-target-meta">
            <span v-if="item.total !== undefined">{{ locale.startsWith('zh') ? `共 ${String(item.total)}` : `Total ${String(item.total)}` }}</span>
            <span v-if="item.changed_count !== undefined">{{ locale.startsWith('zh') ? `${item.__execution ? '变更' : '计划修改'} ${String(item.changed_count)}` : `${item.__execution ? 'Changed' : 'Planned changes'} ${String(item.changed_count)}` }}</span>
            <span v-if="item.affected_games !== undefined">{{ locale.startsWith('zh') ? `影响游戏 ${String(count(item.affected_games))}` : `Games ${String(count(item.affected_games))}` }}</span>
            <strong v-if="item.__execution">{{ targetStatus(item) }}</strong>
          </span>
          <span v-if="item.error" class="agent-execution-target-error">{{ String(item.error) }}</span>
        </li>
      </ul>
    </details>
  </section>
</template>

<style scoped>
.agent-execution-summary { display: grid; gap: 7px; padding: 8px 9px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); background: color-mix(in srgb, var(--df-surface-raised) 76%, transparent); font-size: 11px; }
.agent-execution-heading, .agent-execution-counts, .agent-execution-target-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.agent-execution-heading strong { color: var(--df-text); }
.agent-execution-status { color: var(--df-text-muted); }
.status-partial, .status-cancelled, .status-interrupted, .target-unconfirmed { color: var(--df-warning-strong, #d6a14c); }
.status-failed, .target-failed { color: var(--df-danger-strong, #e57373); }
.status-completed, .target-succeeded { color: var(--df-success-strong, #6fbf8a); }
.agent-execution-audience { color: var(--df-text-muted); }
.agent-execution-counts span { padding: 2px 6px; border-radius: 999px; color: var(--df-text-secondary); background: color-mix(in srgb, var(--df-control-bg) 76%, transparent); }
.agent-execution-targets { min-width: 0; }
.agent-execution-targets summary { color: var(--df-text-muted); cursor: pointer; }
.agent-execution-targets ul { display: grid; gap: 5px; max-height: 168px; margin: 6px 0 0; padding: 0 3px 0 17px; overflow-y: auto; }
.agent-execution-targets li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 8px; color: var(--df-text-secondary); }
.agent-execution-target-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.agent-execution-target-meta { justify-content: flex-end; color: var(--df-text-muted); }
.agent-execution-target-meta strong { font-weight: 600; }
.agent-execution-target-error { grid-column: 1 / -1; color: var(--df-danger-strong, #e57373); overflow-wrap: anywhere; }
</style>
