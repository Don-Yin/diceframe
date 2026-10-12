import type { GlobalThemeOverrides } from 'naive-ui'

interface ThemePalette {
  fontBody: string
  canvas: string
  surface1: string
  surface2: string
  surface3: string
  surfaceRaised: string
  control: string
  border: string
  borderSoft: string
  accent: string
  accentStrong: string
  interactive: string
  interactiveStrong: string
  success: string
  warning: string
  danger: string
  info: string
  text: string
  textSecondary: string
  textMuted: string
  onAccent: string
  hover: string
  focus: string
  radiusSmall: string
  radius: string
}

const FALLBACK: ThemePalette = {
  fontBody: '"Trebuchet MS", "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif',
  canvas: '#070b11',
  surface1: '#0e1720',
  surface2: '#121f2b',
  surface3: '#182936',
  surfaceRaised: '#1d303e',
  control: '#091119',
  border: '#7a6744',
  borderSoft: 'rgba(203, 169, 94, .27)',
  accent: '#caa65f',
  accentStrong: '#f0d38b',
  interactive: '#55b9bd',
  interactiveStrong: '#8ce1df',
  success: '#4d9169',
  warning: '#d39a4c',
  danger: '#a94f4d',
  info: '#548fad',
  text: '#eef2ec',
  textSecondary: '#c8d1ca',
  textMuted: '#8f9d98',
  onAccent: '#14110b',
  hover: 'rgba(85, 185, 189, .10)',
  focus: 'rgba(83, 193, 198, .42)',
  radiusSmall: '5px',
  radius: '9px',
}

function cssValue(styles: CSSStyleDeclaration, name: string, fallback: string): string {
  return styles.getPropertyValue(name).trim() || fallback
}

function cssColor(styles: CSSStyleDeclaration, name: string, fallback: string): string {
  const value = cssValue(styles, name, fallback)
  if (typeof CSS === 'undefined' || typeof CSS.supports !== 'function') return fallback
  return CSS.supports('color', value) ? value : fallback
}

export function readThemePalette(): ThemePalette {
  if (typeof document === 'undefined') return FALLBACK
  const styles = getComputedStyle(document.documentElement)
  return {
    fontBody: cssValue(styles, '--df-font-body', FALLBACK.fontBody),
    canvas: cssColor(styles, '--df-canvas', FALLBACK.canvas),
    surface1: cssColor(styles, '--df-surface-1', FALLBACK.surface1),
    surface2: cssColor(styles, '--df-surface-2', FALLBACK.surface2),
    surface3: cssColor(styles, '--df-surface-3', FALLBACK.surface3),
    surfaceRaised: cssColor(styles, '--df-surface-raised', FALLBACK.surfaceRaised),
    control: cssColor(styles, '--df-control-bg', FALLBACK.control),
    border: cssColor(styles, '--df-border', FALLBACK.border),
    borderSoft: cssColor(styles, '--df-border-soft', FALLBACK.borderSoft),
    accent: cssColor(styles, '--df-accent', FALLBACK.accent),
    accentStrong: cssColor(styles, '--df-accent-strong', FALLBACK.accentStrong),
    interactive: cssColor(styles, '--df-interactive', FALLBACK.interactive),
    interactiveStrong: cssColor(styles, '--df-interactive-strong', FALLBACK.interactiveStrong),
    success: cssColor(styles, '--df-success', FALLBACK.success),
    warning: cssColor(styles, '--df-warning', FALLBACK.warning),
    danger: cssColor(styles, '--df-danger', FALLBACK.danger),
    info: cssColor(styles, '--df-info', FALLBACK.info),
    text: cssColor(styles, '--df-text', FALLBACK.text),
    textSecondary: cssColor(styles, '--df-text-secondary', FALLBACK.textSecondary),
    textMuted: cssColor(styles, '--df-text-muted', FALLBACK.textMuted),
    onAccent: cssColor(styles, '--df-on-accent', FALLBACK.onAccent),
    hover: cssColor(styles, '--df-hover', FALLBACK.hover),
    focus: cssColor(styles, '--df-focus', FALLBACK.focus),
    radiusSmall: cssValue(styles, '--df-radius-sm', FALLBACK.radiusSmall),
    radius: cssValue(styles, '--df-radius-md', FALLBACK.radius),
  }
}

export function createThemeOverrides(palette: ThemePalette): GlobalThemeOverrides {
  return {
    common: {
      fontFamily: palette.fontBody,
      bodyColor: palette.canvas,
      cardColor: palette.surface1,
      modalColor: palette.surface2,
      popoverColor: palette.surfaceRaised,
      borderColor: palette.border,
      primaryColor: palette.interactive,
      primaryColorHover: palette.interactiveStrong,
      primaryColorPressed: palette.interactive,
      primaryColorSuppl: palette.accent,
      successColor: palette.success,
      warningColor: palette.warning,
      errorColor: palette.danger,
      infoColor: palette.info,
      textColorBase: palette.text,
      textColor1: palette.text,
      textColor2: palette.textSecondary,
      textColor3: palette.textMuted,
      textColorDisabled: palette.textMuted,
      placeholderColor: palette.textMuted,
      iconColor: palette.accent,
      inputColor: palette.control,
      inputColorDisabled: palette.surface3,
      actionColor: palette.surface2,
      tableColor: palette.surface1,
      hoverColor: palette.hover,
      dividerColor: palette.borderSoft,
      borderRadius: palette.radius,
      borderRadiusSmall: palette.radiusSmall,
    },
    Button: {
      textColorPrimary: palette.onAccent,
      textColorHoverPrimary: palette.onAccent,
      borderPrimary: `1px solid ${palette.interactive}`,
      borderHoverPrimary: `1px solid ${palette.interactiveStrong}`,
    },
    Card: {
      color: palette.surface1,
      colorModal: palette.surface2,
      borderColor: palette.borderSoft,
    },
    Input: {
      color: palette.control,
      colorFocus: palette.control,
      border: `1px solid ${palette.border}`,
      borderHover: `1px solid ${palette.interactive}`,
      borderFocus: `1px solid ${palette.interactive}`,
      boxShadowFocus: `0 0 0 2px ${palette.focus}`,
      textColor: palette.text,
      placeholderColor: palette.textMuted,
    },
    Menu: {
      itemColorHover: palette.hover,
      itemColorActive: palette.hover,
      itemTextColorActive: palette.interactiveStrong,
      itemTextColorChildActive: palette.interactiveStrong,
    },
    Tag: {
      color: palette.surface3,
      textColor: palette.textSecondary,
    },
  }
}
