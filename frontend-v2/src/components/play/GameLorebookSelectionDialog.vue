<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import Modal from "@/components/ui/Modal.vue";
import { api, errorMessage } from "@/api/client";
import { useLocale } from "@/composables/useLocale";
import { useToast } from "@/composables/useToast";
import { gameLorebookCopy } from "./gameLorebookCopy";
type Book = {
  id: string;
  name: string;
  enabled: boolean;
  entry_count: number;
  selected: boolean;
  locked?: boolean;
};
type State = {
  game_key: string;
  world_id: string;
  world_name: string;
  mode: "auto" | "explicit";
  max_books: number;
  books: Book[];
};
type Approval = {
  session_id: string;
  approval_id: string;
  plan_digest: string;
  label: string;
  preview: {
    target_name: string;
    target_count?: number;
    affected_games?: string[];
    recovery_hint?: string;
    books?: { id: string; name: string }[];
  };
};
const props = withDefaults(defineProps<{ open: boolean; gameKey: string }>(), {
  open: false,
  gameKey: "",
});
const emit = defineEmits<{ close: []; changed: [] }>();
const { locale } = useLocale();
const copy = computed(() => gameLorebookCopy(locale.value));
const toast = useToast();
const state = ref<State | null>(null);
const selected = ref<string[]>([]);
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const approval = ref<Approval | null>(null);
let epoch = 0;
function post() {
  return { method: "POST", headers: { "Content-Type": "application/json" } };
}
async function load() {
  const token = ++epoch;
  loading.value = true;
  busy.value = false;
  error.value = "";
  state.value = null;
  selected.value = [];
  approval.value = null;
  try {
    const result = await api<State & { ok: boolean; error?: string }>(
      `/games/${encodeURIComponent(props.gameKey)}/lorebooks`,
    );
    if (token !== epoch || !props.open) return;
    if (!result.ok) throw new Error(result.error || "lorebook-load-failed");
    if (props.gameKey !== result.game_key)
      throw new Error("Game identity changed");
    state.value = result;
    selected.value = result.books
      .filter((book) => book.selected && !book.locked && book.enabled)
      .map((book) => book.id);
  } catch (cause) {
    if (token === epoch && props.open) error.value = errorMessage(cause);
  } finally {
    if (token === epoch) loading.value = false;
  }
}
function toggle(book: Book) {
  if (book.locked || !book.enabled || busy.value) return;
  const next = new Set(selected.value);
  if (next.has(book.id)) next.delete(book.id);
  else if (next.size < (state.value?.max_books || 16)) next.add(book.id);
  selected.value = [...next];
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
    ...post(),
    body: JSON.stringify({
      session_id: result.session_id,
      approval_id: p.approval_id,
      plan_digest: p.plan_digest,
      approved: false,
    }),
  }).catch(() => undefined);
}
async function plan() {
  if (
    !state.value ||
    busy.value ||
    selected.value.length > state.value.max_books
  )
    return;
  const token = ++epoch;
  const identity = props.gameKey;
  busy.value = true;
  error.value = "";
  try {
    const result = await api<PlanResult>("/assistant/agent/plan", {
      ...post(),
      body: JSON.stringify({
        tool: "set_game_lorebooks",
        arguments: { game_key: identity, book_ids: selected.value },
      }),
    });
    if (token !== epoch || !props.open || props.gameKey !== identity) {
      if (result.ok) await cancelReturnedPlan(result);
      return;
    }
    if (!result.ok) throw new Error(result.error || "lorebook-plan-failed");
    approval.value = { ...result.approval, session_id: result.session_id };
  } catch (cause) {
    if (token === epoch && props.open && props.gameKey === identity)
      error.value = errorMessage(cause);
  } finally {
    if (token === epoch) busy.value = false;
  }
}
async function confirm(approved: boolean) {
  if (!approval.value || busy.value) return;
  const token = epoch;
  const identity = props.gameKey;
  busy.value = true;
  const current = approval.value;
  try {
    const result = await api<{
      ok: boolean;
      result?: { ok: boolean; error?: string };
    }>("/assistant/agent/confirm", {
      ...post(),
      body: JSON.stringify({
        session_id: current.session_id,
        approval_id: current.approval_id,
        plan_digest: current.plan_digest,
        approved,
      }),
    });
    if (token !== epoch || !props.open || props.gameKey !== identity) return;
    if (!result.ok || result.result?.ok === false)
      throw new Error(result.result?.error || "lorebook-confirm-failed");
    if (approved) {
      toast.success(copy.value.done);
      emit("changed");
      emit("close");
    } else {
      approval.value = null;
      emit("close");
    }
  } catch (cause) {
    if (token === epoch && props.open && props.gameKey === identity)
      error.value = errorMessage(cause);
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
  () => [props.open, props.gameKey] as const,
  ([open]) => {
    if (open && props.gameKey) {
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
  <Modal v-if="open" :title="copy.title" @close="close"
    ><div class="game-lorebook-dialog" aria-live="polite">
      <p v-if="loading" class="muted">{{ copy.loading }}</p>
      <div v-else-if="approval" class="selection-preview">
        <h3>{{ copy.preview }}</h3>
        <p v-if="error" class="notice">{{ copy.failed }}: {{ error }}</p>
        <p>
          <strong>{{ state?.world_name }}</strong> · {{ copy.only }}
        </p>
        <p v-if="approval.preview.books?.length">
          {{ approval.preview.books.map((book) => book.name).join("、") }}
        </p>
        <p v-else class="muted">{{ copy.emptySelection }}</p>
        <div class="actions">
          <button
            data-testid="lorebook-cancel"
            :disabled="busy"
            @click="confirm(false)"
          >
            {{ copy.cancel }}</button
          ><button
            class="primary"
            data-testid="lorebook-confirm"
            :disabled="busy"
            @click="confirm(true)"
          >
            {{ copy.confirm }}
          </button>
        </div>
      </div>
      <template v-else-if="error"
        ><p class="notice">{{ copy.failed }}: {{ error }}</p>
        <button :disabled="busy" @click="load">
          {{ copy.retry }}
        </button></template
      >
      <template v-else-if="state"
        ><p class="muted">
          {{ state.world_name }} · {{ copy.max }} ({{ selected.length }}/{{
            state.max_books
          }})
        </p>
        <ul class="book-list">
          <li v-for="book in state.books" :key="book.id">
            <label
              ><input
                type="checkbox"
                :checked="
                  selected.includes(book.id) ||
                  Boolean(book.locked && book.selected)
                "
                :disabled="!book.enabled || book.locked || busy"
                @change="toggle(book)"
              /><span>{{ book.name }}</span
              ><small
                >{{ book.entry_count }} {{ copy.entries
                }}<template v-if="book.locked || !book.enabled">
                  · {{ book.locked ? copy.locked : copy.disabled }}</template
                ></small
              ></label
            >
          </li>
        </ul>
        <div class="actions">
          <button :disabled="busy" @click="close">{{ copy.cancel }}</button
          ><button
            class="primary"
            data-testid="lorebook-save"
            :disabled="busy || selected.length > state.max_books"
            @click="plan"
          >
            {{ copy.save }}
          </button>
        </div></template
      >
    </div></Modal
  >
</template>
<style scoped>
.game-lorebook-dialog {
  min-width: min(560px, 80vw);
}
.book-list {
  display: grid;
  gap: 8px;
  max-height: calc(100dvh - 300px);
  overflow-y: auto;
  padding: 0;
  list-style: none;
}
.book-list label {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.book-list label span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.book-list small {
  margin-left: auto;
  flex: 0 0 auto;
  color: var(--df-text-muted);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.notice {
  color: var(--df-danger);
}
button.primary {
  background: var(--df-accent);
  color: white;
}
</style>
