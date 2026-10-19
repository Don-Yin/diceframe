<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import Modal from "@/components/ui/Modal.vue";
import { api, errorMessage } from "@/api/client";
import { useLocale } from "@/composables/useLocale";
import { useToast } from "@/composables/useToast";
import { recoveryCopy } from "./recoveryCopy";

type Operation = {
  operation_id: string;
  kind: string;
  label: string;
  target_name: string;
  target_count: number;
  created_at: string;
  status: string;
  can_undo: boolean;
  can_restore: boolean;
};
type Approval = {
  session_id: string;
  approval_id: string;
  plan_digest: string;
  label: string;
  preview: {
    target_name: string;
    target_count?: number;
    recovery_hint?: string;
  };
};
const props = withDefaults(defineProps<{ open: boolean }>(), { open: false });
const emit = defineEmits<{ close: []; changed: [] }>();
const { locale } = useLocale();
const copy = computed(() => recoveryCopy(locale.value));
const toast = useToast();
const operations = ref<Operation[]>([]);
const loading = ref(false);
const error = ref("");
const busy = ref(false);
const approval = ref<Approval | null>(null);
let epoch = 0;
function headers() {
  return { method: "POST", headers: { "Content-Type": "application/json" } };
}
function statusLabel(status: string): string {
  if (status === "prepared") return copy.value.statusPrepared;
  if (status === "undone") return copy.value.statusUndone;
  if (status === "restored") return copy.value.statusRestored;
  if (status === "applied") return copy.value.statusApplied;
  return copy.value.statusUnknown;
}
async function load() {
  const token = ++epoch;
  loading.value = true;
  busy.value = false;
  error.value = "";
  approval.value = null;
  operations.value = [];
  try {
    const result = await api<{
      ok: boolean;
      operations?: Operation[];
      error?: string;
    }>("/assistant/agent/content-operations");
    if (token !== epoch || !props.open) return;
    if (!result.ok) throw new Error(result.error || "recovery-load-failed");
    operations.value = result.operations || [];
  } catch (cause) {
    if (token === epoch && props.open) error.value = errorMessage(cause);
  } finally {
    if (token === epoch) loading.value = false;
  }
}
type PlanResult = {
  ok: boolean;
  session_id: string;
  approval: Omit<Approval, "session_id">;
  error?: string;
};
async function cancelReturnedPlan(result: PlanResult) {
  const p = result.approval;
  if (!p || !result.session_id) return;
  await api("/assistant/agent/confirm", {
    ...headers(),
    body: JSON.stringify({
      session_id: result.session_id,
      approval_id: p.approval_id,
      plan_digest: p.plan_digest,
      approved: false,
    }),
  }).catch(() => undefined);
}
async function plan(
  operation: Operation,
  action: "undo_content_operation" | "restore_content_operation",
) {
  if (busy.value) return;
  const token = ++epoch;
  busy.value = true;
  error.value = "";
  try {
    const result = await api<PlanResult>("/assistant/agent/plan", {
      ...headers(),
      body: JSON.stringify({
        tool: action,
        arguments: { operation_id: operation.operation_id },
      }),
    });
    if (token !== epoch || !props.open) {
      if (result.ok) await cancelReturnedPlan(result);
      return;
    }
    if (!result.ok) throw new Error(result.error || "recovery-plan-failed");
    approval.value = { ...result.approval, session_id: result.session_id };
  } catch (cause) {
    if (token === epoch && props.open) error.value = errorMessage(cause);
  } finally {
    if (token === epoch) busy.value = false;
  }
}
async function confirm(approved: boolean) {
  if (!approval.value || busy.value) return;
  const token = epoch;
  busy.value = true;
  const current = approval.value;
  try {
    const result = await api<{
      ok: boolean;
      cancelled?: boolean;
      result?: { ok: boolean; error?: string };
    }>("/assistant/agent/confirm", {
      ...headers(),
      body: JSON.stringify({
        session_id: current.session_id,
        approval_id: current.approval_id,
        plan_digest: current.plan_digest,
        approved,
      }),
    });
    if (token !== epoch || !props.open) return;
    if (!result.ok || result.result?.ok === false)
      throw new Error(result.result?.error || "recovery-confirm-failed");
    if (approved) {
      toast.success(copy.value.done);
      emit("changed");
      emit("close");
    } else {
      approval.value = null;
      emit("close");
    }
  } catch (cause) {
    if (token === epoch && props.open) error.value = errorMessage(cause);
  } finally {
    if (token === epoch) busy.value = false;
  }
}
function close() {
  if (!busy.value) {
    if (approval.value) void confirm(false);
    else emit("close");
  }
}
watch(
  () => props.open,
  (value) => {
    if (value) {
      approval.value = null;
      void load();
    } else epoch += 1;
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  epoch += 1;
});
</script>
<template>
  <Modal v-if="open" :title="copy.title" @close="close">
    <div class="recovery-dialog" aria-live="polite">
      <p v-if="loading" class="muted">{{ copy.loading }}</p>
      <div v-else-if="approval" class="recovery-preview">
        <h3>{{ copy.preview }}</h3>
        <p v-if="error" class="notice">{{ copy.failed }}: {{ error }}</p>
        <p>
          <strong>{{ approval.preview.target_name }}</strong>
        </p>
        <p v-if="approval.preview.target_count !== undefined" class="muted">
          {{ copy.count }}: {{ approval.preview.target_count }}
        </p>
        <p v-if="approval.preview.recovery_hint" class="muted">
          {{ approval.preview.recovery_hint }}
        </p>
        <div class="actions">
          <button
            data-testid="recovery-cancel"
            :disabled="busy"
            @click="confirm(false)"
          >
            {{ copy.cancel }}</button
          ><button
            class="primary"
            data-testid="recovery-confirm"
            :disabled="busy"
            @click="confirm(true)"
          >
            {{ copy.confirm }}
          </button>
        </div>
      </div>
      <template v-else-if="error"
        ><p class="notice">{{ copy.loadFailed }}: {{ error }}</p>
        <button data-testid="recovery-retry" :disabled="busy" @click="load">
          {{ copy.retry }}
        </button></template
      >
      <p v-else-if="!operations.length" class="muted">{{ copy.empty }}</p>
      <ul v-else class="recovery-list">
        <li v-for="operation in operations" :key="operation.operation_id">
          <div>
            <strong>{{ operation.label }}</strong
            ><span
              >{{ operation.target_name }} · {{ operation.target_count }}
              {{ copy.count }} · {{ statusLabel(operation.status) }}</span
            >
            <p v-if="operation.status === 'prepared'" class="muted">
              {{ copy.preparedHint }}
            </p>
          </div>
          <div class="recovery-actions">
            <button
              v-if="operation.status !== 'prepared' && operation.can_undo"
              :data-testid="`recovery-undo-${operation.operation_id}`"
              :disabled="busy"
              @click="plan(operation, 'undo_content_operation')"
            >
              {{ copy.undo }}</button
            ><button
              v-if="operation.status !== 'prepared' && operation.can_restore"
              :data-testid="`recovery-restore-${operation.operation_id}`"
              :disabled="busy"
              @click="plan(operation, 'restore_content_operation')"
            >
              {{ copy.restore }}
            </button>
          </div>
        </li>
      </ul>
    </div>
  </Modal>
</template>
<style scoped>
.recovery-dialog {
  min-width: min(560px, 80vw);
}
.recovery-list {
  display: grid;
  gap: 10px;
  padding: 0;
  list-style: none;
}
.recovery-list li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px;
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
}
.recovery-list span {
  display: block;
  color: var(--df-text-muted);
  font-size: 12px;
}
.recovery-actions,
.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.recovery-preview {
  padding: 8px 0;
}
.notice {
  color: var(--df-danger);
}
button.primary {
  background: var(--df-accent);
  color: white;
}
</style>
