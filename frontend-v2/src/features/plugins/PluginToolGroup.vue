<script setup lang="ts">
import type { Component } from 'vue'
import { NButton, NIcon, NInput, NTag } from 'naive-ui'
import { ExtensionPuzzleOutline } from '@vicons/ionicons5'
import type { PluginInfo, PluginToolDescriptor } from '@/api/types'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{
  plugin: PluginInfo
  tools: PluginToolDescriptor[]
  renderer: Component | null
  toolInputs: Record<string, string>
  toolResults: Record<string, string>
  busy: string
}>()

const emit = defineEmits<{
  'update-tool-input': [tool: PluginToolDescriptor, value: string]
  invoke: [tool: PluginToolDescriptor]
}>()

const { t } = useLocale()
const toolKey = (tool: PluginToolDescriptor) => `${tool.plugin_id}:${tool.name}`
</script>

<template>
  <article class="plugin-tool-group" :data-plugin-id="plugin.id">
    <header class="plugin-tool-group-head">
      <span class="plugin-tool-group-icon" aria-hidden="true">
        <NIcon :component="ExtensionPuzzleOutline" size="22" />
      </span>
      <div class="plugin-tool-group-title">
        <div class="plugin-tool-group-name">
          <h3>{{ plugin.name || plugin.id }}</h3>
          <NTag size="small" :bordered="false">{{ plugin.id }}</NTag>
        </div>
        <p>{{ plugin.description || t('noDescription') }}</p>
      </div>
      <div class="plugin-tool-group-status">
        <NTag :type="plugin.enabled ? 'success' : 'default'" size="small">
          {{ plugin.enabled ? t('enabled') : t('disabled') }}
        </NTag>
        <NTag :type="plugin.running ? 'success' : 'warning'" size="small">
          {{ plugin.running ? t('pluginToolRunning') : t('pluginToolStopped') }}
        </NTag>
        <NTag v-if="plugin.version" size="small">v{{ plugin.version }}</NTag>
      </div>
    </header>

    <div class="plugin-tool-group-body">
      <component
        :is="renderer"
        v-if="renderer"
        :plugin="plugin"
        :tools="tools"
      />

      <div v-else class="plugin-tool-list">
        <article v-for="tool in tools" :key="toolKey(tool)" class="plugin-tool-item">
          <div class="plugin-tool-item-head">
            <div>
              <h4>{{ tool.title || tool.name }}</h4>
              <p class="muted">{{ tool.name }}</p>
            </div>
          </div>
          <p>{{ tool.description || t('noDescription') }}</p>
          <details>
            <summary>{{ t('pluginToolInputSchema') }}</summary>
            <pre>{{ JSON.stringify(tool.input_schema, null, 2) }}</pre>
          </details>
          <label class="input-label">
            <span class="field-title">{{ t('pluginToolArguments') }}</span>
            <NInput
              type="textarea"
              :rows="5"
              :value="props.toolInputs[toolKey(tool)] || '{}'"
              :placeholder="t('pluginToolArgumentsPlaceholder')"
              @update:value="emit('update-tool-input', tool, $event)"
            />
          </label>
          <NButton
            type="primary"
            :loading="busy === `tool:${toolKey(tool)}`"
            @click="emit('invoke', tool)"
          >
            {{ t('pluginToolInvoke') }}
          </NButton>
          <pre v-if="props.toolResults[toolKey(tool)]" class="plugin-tool-result">{{ props.toolResults[toolKey(tool)] }}</pre>
        </article>
        <p v-if="!tools.length" class="muted plugin-tool-empty">{{ t('pluginDedicatedUiEmpty') }}</p>
      </div>
    </div>
  </article>
</template>

<style scoped>
.plugin-tool-group {
  min-width: 0;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--df-accent) 28%, var(--df-border-soft));
  border-radius: var(--df-radius-lg);
  background:
    radial-gradient(circle at 95% 0, color-mix(in srgb, var(--df-interactive) 9%, transparent), transparent 28%),
    linear-gradient(150deg, var(--df-surface-2), var(--df-surface-1));
  box-shadow: var(--df-shadow);
}

.plugin-tool-group-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
  padding: 16px;
  border-bottom: 1px solid var(--df-border-soft);
  background: color-mix(in srgb, var(--df-surface-raised) 78%, transparent);
}

.plugin-tool-group-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border: 1px solid color-mix(in srgb, var(--df-interactive) 34%, var(--df-border-soft));
  border-radius: var(--df-radius-md);
  color: var(--df-interactive-strong);
  background: color-mix(in srgb, var(--df-interactive) 10%, var(--df-control-bg));
}

.plugin-tool-group-title,
.plugin-tool-group-title p {
  min-width: 0;
  margin: 0;
}

.plugin-tool-group-name {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.plugin-tool-group-name h3 {
  margin: 0;
  font-size: 17px;
}

.plugin-tool-group-title p {
  margin-top: 5px;
  color: var(--df-text-secondary);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.plugin-tool-group-status {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
  max-width: 190px;
}

.plugin-tool-group-body {
  padding: 16px;
}

.plugin-tool-list {
  display: grid;
  gap: 12px;
}

.plugin-tool-item {
  display: grid;
  min-width: 0;
  gap: 10px;
  padding: 13px;
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-md);
  background: color-mix(in srgb, var(--df-control-bg) 82%, transparent);
}

.plugin-tool-item h4,
.plugin-tool-item p,
.plugin-tool-item-head p {
  margin: 0;
}

.plugin-tool-item details summary {
  cursor: pointer;
  color: var(--df-accent-strong);
}

.plugin-tool-item pre {
  max-height: 220px;
  overflow: auto;
  margin: 8px 0 0;
  padding: 10px;
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-sm);
  background: var(--df-surface-3);
  color: var(--df-text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.plugin-tool-result {
  border-color: var(--df-interactive) !important;
}

.plugin-tool-empty {
  margin: 0;
}

@media (max-width: 640px) {
  .plugin-tool-group-head {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .plugin-tool-group-status {
    grid-column: 1 / -1;
    justify-content: flex-start;
    max-width: none;
  }

  .plugin-tool-group-body {
    padding: 12px;
  }
}
</style>
