<script setup lang="ts">
import { computed, toRef } from 'vue'
import Modal from '@/components/ui/Modal.vue'
import { useLocale } from '@/composables/useLocale'
import type { RestActivity } from '@/api/types'
import { useRestNotices } from './useRestNotices'

const props = defineProps<{ gameKey: string; runId: string; actorId: string; activity: RestActivity[] }>()
const emit = defineEmits<{ 'open-rest': [kind: RestActivity['kind']] }>()
const { locale } = useLocale()
const zh = computed(() => locale.value.startsWith('zh'))
const copy = computed(() => zh.value ? {
  title: '休息动态', open: '休息动态', enabled: '显示休息提醒（仅自己）',
  empty: '暂无休息动态', view: '查看', mute: '不再提醒', close: '关闭通知',
  more: (count: number) => `还有 ${count} 条`, team: '队伍',
} : {
  title: 'Rest activity', open: 'Rest activity', enabled: 'Show rest reminders (only me)',
  empty: 'No rest activity yet', view: 'View', mute: 'Mute reminders', close: 'Dismiss notification',
  more: (count: number) => `${count} more`, team: 'Party',
})
const state = useRestNotices(toRef(props, 'gameKey'), toRef(props, 'runId'), toRef(props, 'actorId'), toRef(props, 'activity'))
const { enabled, unread, toast, dialogOpen } = state

const actors = computed(() => {
  const names = new Map<string, string>()
  for (const row of props.activity) for (const actor of row.actors) names.set(actor.uid, actor.name || actor.uid)
  return [...names.values()]
})

function kindText(kind: RestActivity['kind']) {
  const names = zh.value
    ? { overnight: '过夜休息', therapy: '治疗', short: '短休息', long: '长休息' }
    : { overnight: 'overnight rest', therapy: 'therapy', short: 'short rest', long: 'long rest' }
  return names[kind]
}

function statusText(status: RestActivity['status']) {
  const names = zh.value
    ? { requested: '申请', settled: '结算完成', rejected: '申请已结束', error: '申请出错' }
    : { requested: 'requested', settled: 'settled', rejected: 'ended', error: 'error' }
  return names[status]
}

function actorText(row: RestActivity) {
  return row.actors.map(actor => actor.name || actor.uid).join(zh.value ? '、' : ', ')
}

function activityText(row: RestActivity) {
  return `${actorText(row)} · ${kindText(row.kind)} · ${statusText(row.status)}`
}

function view(kind: RestActivity['kind']) {
  state.dismissToast()
  state.closeHistory()
  emit('open-rest', kind)
}
</script>

<template>
  <section class="rest-notices" :aria-label="copy.title">
    <button type="button" class="rest-notices-open" data-testid="rest-notices-open" @click="state.openHistory">
      <span>{{ copy.open }}</span>
      <span v-if="actors.length" class="rest-notices-actors">{{ actors.join(zh ? '、' : ', ') }}</span>
      <span v-else class="rest-notices-actors">{{ copy.team }}</span>
      <span v-if="unread" class="rest-notices-badge" aria-label="unread">{{ unread }}</span>
    </button>
  </section>

  <Teleport to="body">
    <div class="rest-notice-toast-layer">
      <aside v-if="toast" class="rest-notice-toast" data-testid="rest-notice-toast" role="status" aria-live="polite">
        <p>{{ activityText(toast.latest) }}<template v-if="toast.count > 1"> · {{ copy.more(toast.count - 1) }}</template></p>
        <div class="rest-notice-toast-actions">
          <button type="button" data-testid="rest-notice-view" @click="view(toast.latest.kind)">{{ copy.view }}</button>
          <button type="button" data-testid="rest-notice-mute" @click="state.setEnabled(false)">{{ copy.mute }}</button>
          <button type="button" data-testid="rest-notice-dismiss" :aria-label="copy.close" @click="state.dismissToast">×</button>
        </div>
      </aside>
    </div>
  </Teleport>

  <Modal v-if="dialogOpen" :title="copy.title" close-test-id="rest-notices-close" @close="state.closeHistory">
    <div class="rest-notices-dialog" data-testid="rest-notices-dialog">
      <label class="rest-notices-setting">
        <input type="checkbox" data-testid="rest-notices-enabled" :checked="enabled" @change="state.setEnabled(($event.target as HTMLInputElement).checked)" />
        <span>{{ copy.enabled }}</span>
      </label>
      <div class="rest-notices-list" data-testid="rest-notices-list">
        <p v-if="!props.activity.length" class="rest-notices-empty">{{ copy.empty }}</p>
        <article v-for="row in props.activity" :key="row.id" class="rest-notices-entry">
          <p>{{ activityText(row) }}</p>
          <button type="button" data-testid="rest-notice-view" @click="view(row.kind)">{{ copy.view }}</button>
        </article>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.rest-notices { display: grid; min-width: 0; }
.rest-notices-open { display: flex; align-items: center; gap: 6px; width: 100%; min-width: 0; min-height: 32px; padding: 6px 8px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); background: var(--df-surface-2); color: var(--df-text); font-size: 12px; text-align: left; }
.rest-notices-open > span:first-child { flex: 0 0 auto; font-weight: 700; }
.rest-notices-actors { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--df-text-muted); }
.rest-notices-badge { flex: 0 0 auto; min-width: 18px; padding: 1px 5px; border-radius: 999px; background: var(--df-accent-strong); color: var(--df-on-accent, #fff); font-size: 11px; text-align: center; }
.rest-notice-toast-layer { position: fixed; z-index: 1100; top: 12px; right: 12px; width: min(380px, calc(100vw - 24px)); pointer-events: none; }
.rest-notice-toast { display: grid; gap: 8px; max-width: calc(100vw - 24px); padding: 12px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-md); background: var(--df-surface-1); box-shadow: var(--df-shadow-lg, 0 8px 30px rgb(0 0 0 / 18%)); pointer-events: auto; overflow-wrap: anywhere; }
.rest-notice-toast p { margin: 0; color: var(--df-text); line-height: 1.45; }
.rest-notice-toast-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.rest-notice-toast-actions button { min-height: 28px; padding: 4px 8px; }
.rest-notice-toast-actions button:last-child { margin-left: auto; border: 0; background: transparent; color: var(--df-text-muted); font-size: 18px; line-height: 1; }
.rest-notices-dialog { display: grid; min-width: 0; gap: 12px; }
.rest-notices-setting { display: flex; align-items: flex-start; gap: 8px; overflow-wrap: anywhere; }
.rest-notices-setting input { flex: 0 0 auto; width: 16px; height: 16px; }
.rest-notices-list { display: grid; min-width: 0; gap: 8px; max-height: min(55vh, 480px); overflow: auto; }
.rest-notices-empty { margin: 0; color: var(--df-text-muted); }
.rest-notices-entry { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; min-width: 0; padding: 10px; border: 1px solid var(--df-border-soft); border-radius: var(--df-radius-sm); background: var(--df-surface-2); overflow-wrap: anywhere; }
.rest-notices-entry p { min-width: 0; margin: 0; line-height: 1.45; }
.rest-notices-entry button { flex: 0 0 auto; min-height: 28px; padding: 4px 8px; }
@media (max-width: 560px) {
  .rest-notices-entry { display: grid; }
  .rest-notices-entry button { justify-self: start; }
}
</style>
