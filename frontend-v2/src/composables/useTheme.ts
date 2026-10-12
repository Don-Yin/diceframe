import { computed, ref } from 'vue'
import { darkTheme, type GlobalTheme } from 'naive-ui'
import { api } from '@/api/client'
import type { PluginTheme, PluginThemesResponse } from '@/api/types'
import { createThemeOverrides, readThemePalette } from '@/styles/theme'

export type ThemeName = 'dark' | 'light'
export type SkinName = 'midnight' | 'royal' | 'jade' | 'crimson'

export const DEFAULT_THEME_MODE: ThemeName = 'dark'
export const DEFAULT_THEME_SKIN: SkinName = 'midnight'

export interface BuiltinSkin {
  id: SkinName
  name: string
  description: string
  swatches: readonly [string, string, string]
}

export const builtinSkins: readonly BuiltinSkin[] = [
  {
    id: 'midnight',
    name: '星海秘典',
    description: '深海蓝、旧金与青色交互光。',
    swatches: ['#070b11', '#caa65f', '#55b9bd'],
  },
  {
    id: 'royal',
    name: '王廷鎏金',
    description: '炭黑与纯金，适合古典史诗。',
    swatches: ['#090908', '#c99a43', '#f1c96d'],
  },
  {
    id: 'jade',
    name: '翡翠远境',
    description: '幽绿与柔金，适合自然与秘境。',
    swatches: ['#07100f', '#83b99c', '#55c5a2'],
  },
  {
    id: 'crimson',
    name: '绯红余烬',
    description: '暗红与铜金，适合阴谋和战争。',
    swatches: ['#10090c', '#c78d5b', '#d46359'],
  },
] as const

const MODE_STORAGE_KEY = 'diceframe_mode_v2'
const SKIN_STORAGE_KEY = 'diceframe_skin_v2'
const PLUGIN_THEME_KEY = 'diceframe_plugin_theme_v2'
const PLUGIN_THEME_TOKEN_NAMES = new Set([
  '--df-font-title', '--df-font-body', '--df-font-mono',
  '--df-canvas', '--df-canvas-glow',
  '--df-surface-1', '--df-surface-2', '--df-surface-3', '--df-surface-raised', '--df-control-bg',
  '--df-border', '--df-border-soft', '--df-focus',
  '--df-accent', '--df-accent-strong', '--df-interactive', '--df-interactive-strong',
  '--df-success', '--df-success-strong', '--df-warning', '--df-danger', '--df-danger-strong', '--df-info',
  '--df-text', '--df-text-secondary', '--df-text-muted', '--df-on-accent', '--df-hover',
  '--df-shadow', '--df-shadow-strong', '--df-radius-sm', '--df-radius-md', '--df-radius-lg',
])

function readMode(): ThemeName {
  if (typeof localStorage === 'undefined') return DEFAULT_THEME_MODE
  return localStorage.getItem(MODE_STORAGE_KEY) === 'light' ? 'light' : DEFAULT_THEME_MODE
}

function isSkinName(value: string | null): value is SkinName {
  return builtinSkins.some(skin => skin.id === value)
}

function readSkin(): SkinName {
  if (typeof localStorage === 'undefined') return DEFAULT_THEME_SKIN
  const stored = localStorage.getItem(SKIN_STORAGE_KEY)
  return isSkinName(stored) ? stored : DEFAULT_THEME_SKIN
}

const current = ref<ThemeName>(readMode())
const skin = ref<SkinName>(readSkin())
const pluginThemes = ref<PluginTheme[]>([])
const pluginThemeId = ref(
  typeof localStorage === 'undefined' ? '' : localStorage.getItem(PLUGIN_THEME_KEY) || '',
)
const appliedPluginVars = new Set<string>()
const themeRevision = ref(0)

function applyThemeAttributes() {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.mode = current.value
  document.documentElement.dataset.skin = skin.value
  document.body.classList.toggle('light', current.value === 'light')
}

applyThemeAttributes()

function clearPluginVars() {
  if (typeof document === 'undefined') return
  const style = document.documentElement.style
  for (const key of appliedPluginVars) style.removeProperty(key)
  appliedPluginVars.clear()
  themeRevision.value += 1
}

function applyPluginVars(theme: PluginTheme | undefined) {
  clearPluginVars()
  if (theme?.schema_version !== 2 || !theme.tokens || typeof document === 'undefined') return
  const values = {
    ...(theme.tokens.base || {}),
    ...(current.value === 'dark' ? theme.tokens.dark || {} : theme.tokens.light || {}),
  }
  const style = document.documentElement.style
  for (const [key, value] of Object.entries(values)) {
    if (!PLUGIN_THEME_TOKEN_NAMES.has(key) || typeof value !== 'string') continue
    style.setProperty(key, value)
    appliedPluginVars.add(key)
  }
  themeRevision.value += 1
}

function selectedPluginTheme() {
  return pluginThemes.value.find(theme => theme.id === pluginThemeId.value)
}

export function useTheme() {
  const naiveTheme = computed<GlobalTheme | null>(() => (current.value === 'dark' ? darkTheme : null))
  const overrides = computed(() => {
    void themeRevision.value
    return createThemeOverrides(readThemePalette())
  })

  function apply(name: ThemeName) {
    current.value = name
    applyThemeAttributes()
    localStorage.setItem(MODE_STORAGE_KEY, name)
    applyPluginVars(selectedPluginTheme())
  }

  function toggle() {
    apply(current.value === 'dark' ? 'light' : 'dark')
  }

  function applySkin(name: SkinName) {
    skin.value = name
    applyThemeAttributes()
    localStorage.setItem(SKIN_STORAGE_KEY, name)
    applyPluginVars(selectedPluginTheme())
  }

  async function loadPluginThemes() {
    const response = await api<PluginThemesResponse>('/plugins/themes')
    pluginThemes.value = (response.themes || []).filter(theme => theme.schema_version === 2)
    const selected = selectedPluginTheme()
    if (selected) {
      applyPluginVars(selected)
    } else if (pluginThemeId.value) {
      clearPluginTheme()
    }
  }

  function applyPluginTheme(id: string | null) {
    const next = id || ''
    pluginThemeId.value = next
    if (next) localStorage.setItem(PLUGIN_THEME_KEY, next)
    else localStorage.removeItem(PLUGIN_THEME_KEY)
    applyPluginVars(selectedPluginTheme())
  }

  function clearPluginTheme() {
    pluginThemeId.value = ''
    localStorage.removeItem(PLUGIN_THEME_KEY)
    clearPluginVars()
  }

  function suspendPluginTheme() {
    clearPluginVars()
  }

  function restorePluginTheme() {
    applyPluginVars(selectedPluginTheme())
  }

  return {
    current,
    skin,
    builtinSkins,
    naiveTheme,
    overrides,
    pluginThemes,
    pluginThemeId,
    apply,
    toggle,
    applySkin,
    loadPluginThemes,
    applyPluginTheme,
    clearPluginTheme,
    suspendPluginTheme,
    restorePluginTheme,
  }
}
