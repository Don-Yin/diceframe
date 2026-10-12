import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PluginToolGroup from '../src/features/plugins/PluginToolGroup.vue'
import { i18n } from '../src/i18n'
import type { PluginInfo, PluginToolDescriptor } from '../src/api/types'

const plugin: PluginInfo = {
  id: 'echo-tool',
  name: 'Echo Tool',
  version: '1.0.0',
  plugin_type: 'tool',
  description: 'Echoes text',
  enabled: true,
  running: true,
  status: 'running',
}

const tools: PluginToolDescriptor[] = [
  {
    plugin_id: 'echo-tool',
    plugin_name: 'Echo Tool',
    name: 'echo',
    title: 'Echo',
    description: 'Echo text',
    input_schema: { type: 'object' },
  },
  {
    plugin_id: 'echo-tool',
    plugin_name: 'Echo Tool',
    name: 'upper',
    title: 'Uppercase',
    description: 'Uppercase text',
    input_schema: { type: 'object' },
  },
]

describe('PluginToolGroup', () => {
  it('keeps multiple tools inside one plugin module', () => {
    const wrapper = mount(PluginToolGroup, {
      props: {
        plugin,
        tools,
        renderer: null,
        toolInputs: {},
        toolResults: {},
        busy: '',
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.attributes('data-plugin-id')).toBe('echo-tool')
    expect(wrapper.findAll('.plugin-tool-item')).toHaveLength(2)
    expect(wrapper.text()).toContain('Echo Tool')
  })

  it('passes only the current plugin and tools to a dedicated renderer', () => {
    const Renderer = defineComponent({
      props: ['plugin', 'tools'],
      template: '<div class="dedicated">{{ plugin.id }}:{{ tools.length }}</div>',
    })
    const wrapper = mount(PluginToolGroup, {
      props: {
        plugin,
        tools,
        renderer: Renderer,
        toolInputs: {},
        toolResults: {},
        busy: '',
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.get('.dedicated').text()).toBe('echo-tool:2')
    expect(wrapper.find('.plugin-tool-item').exists()).toBe(false)
  })
})
