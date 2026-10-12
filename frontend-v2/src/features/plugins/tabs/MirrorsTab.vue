<script setup lang="ts">
import { NButton, NIcon, NInput, NInputNumber, NSpin, NSwitch, NTag } from 'naive-ui'
import {
  AddOutline, ChevronDown, ChevronUp, CreateOutline, RefreshOutline, TrashOutline,
} from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'
import type { PluginMirror } from '@/api/types'

const { t } = useLocale()

defineProps<{
  mirrors: PluginMirror[]
  mirrorTests: Record<string, string>
  mirrorLoading: boolean
  newMirror: PluginMirror
  busy: string
  loadMirrors: () => Promise<void> | void
  addMirror: () => Promise<void> | void
  saveMirror: (mirror: PluginMirror, patch: Partial<PluginMirror>) => Promise<void> | void
  deleteMirror: (mirror: PluginMirror) => Promise<void> | void
  testMirror: (mirror?: PluginMirror) => Promise<void> | void
}>()

const emit = defineEmits<{
  updateNewMirror: [patch: Partial<PluginMirror>]
}>()

function updateNewMirror(patch: Partial<PluginMirror>) {
  emit('updateNewMirror', patch)
}
</script>

<template>
  <section class="toolbar-row">
    <NButton :loading="mirrorLoading" @click="loadMirrors">
      <template #icon><NIcon :component="RefreshOutline" /></template>
      {{ t('refresh') }}
    </NButton>
    <NButton :loading="busy === 'mirror-test:all'" @click="testMirror()">
      {{ t('testAll') }}
    </NButton>
  </section>

  <div class="mirror-form">
    <NInput :value="newMirror.id" class="mirror-field-id" :placeholder="t('mirrorIdPlaceholder')" @update:value="updateNewMirror({ id: $event })" />
    <NInput :value="newMirror.name" class="mirror-field-name" :placeholder="t('name')" @update:value="updateNewMirror({ name: $event })" />
    <NInput :value="newMirror.raw_prefix" class="mirror-url-input mirror-field-raw" :placeholder="t('rawPrefix')" @update:value="updateNewMirror({ raw_prefix: $event })" />
    <NInput :value="newMirror.clone_prefix" class="mirror-url-input mirror-field-clone" :placeholder="t('clonePrefix')" @update:value="updateNewMirror({ clone_prefix: $event })" />
    <NInputNumber :value="newMirror.priority" :min="1" class="mirror-field-priority" :placeholder="t('priority')" @update:value="updateNewMirror({ priority: $event || 1 })" />
    <NSwitch :value="newMirror.enabled" class="mirror-field-switch" @update:value="updateNewMirror({ enabled: $event })" />
    <NButton type="primary" class="mirror-field-add" :loading="busy === 'mirror:add'" @click="addMirror">
      <template #icon><NIcon :component="AddOutline" /></template>
      {{ t('add') }}
    </NButton>
  </div>

  <NSpin :show="mirrorLoading">
    <div class="mirror-list">
      <article v-for="mirror in mirrors" :key="mirror.id" class="mirror-row">
        <div class="mirror-main">
          <div class="mirror-heading">
            <NSwitch :value="mirror.enabled" @update:value="saveMirror(mirror, { enabled: $event })" />
            <strong>{{ mirror.name }}</strong>
            <NTag size="small">{{ mirror.id }}</NTag>
            <NTag size="small">{{ t('priority') }} {{ mirror.priority }}</NTag>
          </div>
          <p class="muted">Raw：{{ mirror.raw_prefix }}</p>
          <div class="mirror-edit-grid">
            <NInput v-model:value="mirror.name" :placeholder="t('name')" />
            <NInput v-model:value="mirror.raw_prefix" class="mirror-url-input" :placeholder="t('rawPrefix')" />
            <NInput v-model:value="mirror.clone_prefix" class="mirror-url-input" :placeholder="t('downloadPrefix')" />
            <NInputNumber v-model:value="mirror.priority" :min="1" />
          </div>
          <p v-if="mirrorTests[mirror.id]" class="mirror-test">{{ mirrorTests[mirror.id] }}</p>
        </div>
        <div class="mirror-actions">
          <NButton size="small" :loading="busy === `mirror-test:${mirror.id}`" @click="testMirror(mirror)">{{ t('test') }}</NButton>
          <NButton size="small" @click="saveMirror(mirror, { priority: Math.max(1, mirror.priority - 1) })">
            <template #icon><NIcon :component="ChevronUp" /></template>
          </NButton>
          <NButton size="small" @click="saveMirror(mirror, { priority: mirror.priority + 1 })">
            <template #icon><NIcon :component="ChevronDown" /></template>
          </NButton>
          <NButton size="small" @click="saveMirror(mirror, mirror)">
            <template #icon><NIcon :component="CreateOutline" /></template>
            {{ t('saveAction') }}
          </NButton>
          <NButton size="small" type="error" tertiary @click="deleteMirror(mirror)">
            <template #icon><NIcon :component="TrashOutline" /></template>
          </NButton>
        </div>
      </article>
    </div>
  </NSpin>
</template>

<style scoped>
.mirror-form {
  display: grid;
  grid-template-columns: 1fr 1fr 96px auto auto;
  grid-template-areas:
    "id name priority switch btn"
    "raw raw clone clone .";
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
  padding: 14px;
  max-width: 100%;
  overflow: hidden;
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
  background: linear-gradient(180deg, var(--df-surface-1), var(--df-surface-2));
}

.mirror-form .mirror-field-id { grid-area: id; }
.mirror-form .mirror-field-name { grid-area: name; }
.mirror-form .mirror-field-raw { grid-area: raw; }
.mirror-form .mirror-field-clone { grid-area: clone; }
.mirror-form .mirror-field-priority { grid-area: priority; }
.mirror-form .mirror-field-switch { grid-area: switch; }
.mirror-form .mirror-field-add { grid-area: btn; }

.mirror-list {
  display: grid;
  gap: 12px;
}

.mirror-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: flex-start;
  padding: 14px;
  max-width: 100%;
  overflow: hidden;
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
  background: linear-gradient(180deg, var(--df-surface-1), var(--df-surface-2));
}

.mirror-main {
  min-width: 0;
}

.mirror-main p {
  margin: 6px 0 0;
  word-break: break-all;
}

.mirror-heading,
.mirror-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.mirror-actions {
  justify-content: flex-end;
  max-width: 100%;
}

.mirror-edit-grid {
  display: grid;
  grid-template-columns: minmax(120px, .8fr) minmax(160px, 1.2fr) minmax(160px, 1.2fr) minmax(90px, .5fr);
  gap: 8px;
  margin-top: 10px;
  min-width: 0;
}

.mirror-test {
  color: var(--df-accent-strong);
}

.mirror-form :deep(.n-input),
.mirror-form :deep(.n-input-number),
.mirror-edit-grid :deep(.n-input),
.mirror-edit-grid :deep(.n-input-number) {
  min-width: 0;
  width: 100%;
}

@media (max-width: 1180px) {
  .mirror-form {
    grid-template-columns: 1fr 1fr auto auto;
    grid-template-areas:
      "id name priority btn"
      "raw raw clone clone";
  }

  .mirror-form .mirror-field-switch {
    display: none;
  }

  .mirror-edit-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .mirror-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 980px) {
  .mirror-form {
    grid-template-columns: 1fr;
    grid-template-areas:
      "id"
      "name"
      "raw"
      "clone"
      "priority"
      "btn";
  }

  .mirror-form .mirror-field-switch {
    display: none;
  }

  .mirror-edit-grid {
    grid-template-columns: 1fr;
  }

  .mirror-actions {
    justify-content: flex-start;
  }
}
</style>
