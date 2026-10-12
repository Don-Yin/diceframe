<script setup lang="ts">
import { NButton, NSelect } from 'naive-ui'
import { useLocale } from '@/composables/useLocale'
import type { BuiltinSkin, SkinName } from '@/composables/useTheme'
import type { PluginTheme } from '@/api/types'

defineProps<{
  builtinSkins: readonly BuiltinSkin[]
  skin: SkinName
  pluginThemeId: string
  pluginThemes: PluginTheme[]
  themeOptions: { label: string; value: string }[]
  skinNameKeys: Record<SkinName, string>
  skinDescriptionKeys: Record<SkinName, string>
  loadPluginThemes: () => Promise<void> | void
  selectBuiltinSkin: (id: SkinName) => void
  selectPluginTheme: (value: string | null) => void
  clearPluginTheme: () => void
  selectedThemeDescription: () => string
}>()

const { t } = useLocale()
</script>

<template>
  <section class="theme-plugin-panel builtin-theme-panel">
    <div>
      <h3>{{ t('builtinThemes') }}</h3>
      <p class="muted">{{ t('builtinThemesHelp') }}</p>
    </div>
    <div class="builtin-theme-grid">
      <button
        v-for="item in builtinSkins"
        :key="item.id"
        type="button"
        class="builtin-theme-card"
        :class="{ active: skin === item.id && !pluginThemeId }"
        :aria-pressed="skin === item.id && !pluginThemeId"
        @click="selectBuiltinSkin(item.id)"
      >
        <span class="theme-swatches" aria-hidden="true">
          <i v-for="color in item.swatches" :key="color" :style="{ backgroundColor: color }" />
        </span>
        <strong>{{ t(skinNameKeys[item.id] as never) }}</strong>
        <small>{{ t(skinDescriptionKeys[item.id] as never) }}</small>
      </button>
    </div>
  </section>
  <section class="theme-plugin-panel">
    <div>
      <h3>{{ t('pluginThemes') }}</h3>
      <p class="muted">{{ t('pluginThemesHelp') }}</p>
    </div>
    <div class="theme-plugin-controls">
      <NSelect
        :value="pluginThemeId || null"
        :options="themeOptions"
        :placeholder="t('selectEnabledThemePlugin')"
        clearable
        @update:value="selectPluginTheme"
      />
      <NButton :disabled="!pluginThemeId" @click="clearPluginTheme">{{ t('clear') }}</NButton>
      <NButton @click="loadPluginThemes">{{ t('refresh') }}</NButton>
    </div>
    <p v-if="selectedThemeDescription()" class="muted">{{ selectedThemeDescription() }}</p>
    <p v-if="!pluginThemes.length" class="muted">{{ t('noEnabledThemePlugins') }}</p>
  </section>
</template>

<style scoped>
.theme-plugin-panel {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
  background: linear-gradient(180deg, var(--df-surface-1), var(--df-surface-2));
}

.builtin-theme-panel {
  margin-bottom: 14px;
}

.builtin-theme-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.builtin-theme-card {
  display: grid;
  gap: 7px;
  min-width: 0;
  padding: 11px;
  text-align: left;
  background: var(--df-control-bg);
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-md);
  color: var(--df-text);
}

.builtin-theme-card:hover,
.builtin-theme-card.active {
  border-color: var(--df-interactive);
  box-shadow: 0 0 0 2px var(--df-focus);
}

.builtin-theme-card strong {
  color: var(--df-accent-strong);
}

.builtin-theme-card small {
  color: var(--df-text-muted);
  line-height: 1.45;
}

.theme-swatches {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  height: 34px;
  overflow: hidden;
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-sm);
}

.theme-swatches i {
  display: block;
}

.theme-plugin-panel h3 {
  margin: 0;
  color: var(--df-accent-strong);
}

.theme-plugin-panel p {
  margin: 4px 0 0;
}

.theme-plugin-controls {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) auto auto;
  gap: 10px;
  align-items: center;
}

@media (max-width: 980px) {
  .builtin-theme-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .theme-plugin-controls {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .builtin-theme-grid {
    grid-template-columns: 1fr;
  }
}
</style>
