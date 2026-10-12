<script setup lang="ts">
import { computed, type Component } from 'vue'
import { NButton, NIcon, NSpin } from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'
import type { PluginInfo, PluginToolDescriptor } from '@/api/types'
import PluginToolGroup from '../PluginToolGroup.vue'
import TunnelCard from '../TunnelCard.vue'

interface PluginToolGroupState {
  plugin: PluginInfo
  tools: PluginToolDescriptor[]
  renderer: Component | null
}

const props = defineProps<{
  plugins: PluginInfo[]
  tools: PluginToolDescriptor[]
  toolInputs: Record<string, string>
  toolResults: Record<string, string>
  toolsLoading: boolean
  busy: string
  loadTools: () => Promise<void> | void
  setToolInput: (tool: PluginToolDescriptor, value: string) => void
  invokeTool: (tool: PluginToolDescriptor) => Promise<void> | void
}>()

const { t } = useLocale()

// 工具页专用 UI registry：tool_ui 值 -> 渲染组件。未来进程插件声明新的 tool_ui
// 值并在此注册组件即可获得专用卡，无需改工具页分发逻辑。
const toolUiRegistry: Record<string, Component> = {
  'tunnel-card': TunnelCard,
}

// 工具页统一按插件分组。专用 UI 和通用 JSON 工具共享同一层插件模块外壳，
// 避免未来新增插件时把多个插件的状态和操作混在一起。
const toolGroups = computed<PluginToolGroupState[]>(() => {
  const toolsByPlugin = new Map<string, PluginToolDescriptor[]>()
  for (const tool of props.tools) {
    const group = toolsByPlugin.get(tool.plugin_id) || []
    group.push(tool)
    toolsByPlugin.set(tool.plugin_id, group)
  }
  return props.plugins.flatMap((plugin) => {
    const pluginTools = toolsByPlugin.get(plugin.id) || []
    const toolUi = plugin.tool_ui || pluginTools.find(tool => tool.tool_ui)?.tool_ui || ''
    if (!pluginTools.length && !toolUi) return []
    return [{
      plugin,
      tools: pluginTools,
      renderer: toolUiRegistry[toolUi] || null,
    }]
  })
})
</script>

<template>
  <section class="toolbar-row">
    <div>
      <h3>{{ t('pluginToolsTitle') }}</h3>
      <p class="muted">{{ t('pluginToolsHelp') }}</p>
    </div>
    <NButton :loading="toolsLoading" @click="loadTools">
      <template #icon><NIcon :component="RefreshOutline" /></template>
      {{ t('refresh') }}
    </NButton>
  </section>
  <NSpin :show="toolsLoading">
    <div v-if="toolGroups.length" class="plugin-tool-groups">
      <PluginToolGroup
        v-for="group in toolGroups"
        :key="group.plugin.id"
        :plugin="group.plugin"
        :tools="group.tools"
        :renderer="group.renderer"
        :tool-inputs="toolInputs"
        :tool-results="toolResults"
        :busy="busy"
        @update-tool-input="setToolInput"
        @invoke="invokeTool"
      />
    </div>
    <p v-else class="muted">{{ t('noRunningPluginTools') }}</p>
  </NSpin>
</template>

<style scoped>
.plugin-tool-groups {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 410px), 1fr));
  gap: 16px;
  align-items: start;
}
</style>
