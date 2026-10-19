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
  fontBody: '"Aptos", "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif',
  canvas: '#0d1520',
  surface1: '#121c26',
  surface2: '#182532',
  surface3: '#223447',
  surfaceRaised: '#2d4251',
  control: '#0b141e',
  border: '#806b46',
  borderSoft: 'rgba(210, 178, 112, .24)',
  accent: '#c7a362',
  accentStrong: '#f0d8a0',
  interactive: '#4d9bc9',
  interactiveStrong: '#89cbed',
  success: '#4f9c7d',
  warning: '#d39b4d',
  danger: '#a95750',
  info: '#7395a0',
  text: '#f0eee5',
  textSecondary: '#d0d3c9',
  textMuted: '#929d98',
  onAccent: '#17140e',
  hover: 'rgba(77, 155, 201, .13)',
  focus: 'rgba(91, 171, 220, .44)',
  radiusSmall: '6px',
  radius: '8px',
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
      color: palette.surface2,
      colorHover: palette.surface3,
      colorPressed: palette.surface1,
      colorFocus: palette.surface3,
      colorDisabled: palette.surface2,
      textColor: palette.textSecondary,
      textColorHover: palette.text,
      textColorPressed: palette.text,
      textColorFocus: palette.text,
      textColorDisabled: palette.textMuted,
      border: `1px solid ${palette.borderSoft}`,
      borderHover: `1px solid ${palette.interactive}`,
      borderPressed: `1px solid ${palette.interactiveStrong}`,
      borderFocus: `1px solid ${palette.interactiveStrong}`,
      borderDisabled: `1px solid ${palette.borderSoft}`,
      colorPrimary: `color-mix(in srgb, ${palette.interactive} 18%, ${palette.surfaceRaised})`,
      colorHoverPrimary: `color-mix(in srgb, ${palette.interactive} 25%, ${palette.surfaceRaised})`,
      colorPressedPrimary: `color-mix(in srgb, ${palette.interactive} 13%, ${palette.surface2})`,
      colorFocusPrimary: `color-mix(in srgb, ${palette.interactive} 22%, ${palette.surfaceRaised})`,
      colorDisabledPrimary: `color-mix(in srgb, ${palette.interactive} 10%, ${palette.surface2})`,
      textColorPrimary: palette.text,
      textColorHoverPrimary: palette.text,
      textColorPressedPrimary: palette.text,
      textColorFocusPrimary: palette.text,
      textColorDisabledPrimary: `color-mix(in srgb, ${palette.text} 78%, transparent)`,
      borderPrimary: `1px solid ${palette.interactive}`,
      borderHoverPrimary: `1px solid ${palette.interactiveStrong}`,
      borderPressedPrimary: `1px solid ${palette.interactiveStrong}`,
      borderFocusPrimary: `1px solid ${palette.interactiveStrong}`,
      borderDisabledPrimary: `1px solid color-mix(in srgb, ${palette.interactive} 30%, ${palette.borderSoft})`,
      colorSuccess: `color-mix(in srgb, ${palette.success} 18%, ${palette.surfaceRaised})`,
      colorHoverSuccess: `color-mix(in srgb, ${palette.success} 25%, ${palette.surfaceRaised})`,
      colorPressedSuccess: `color-mix(in srgb, ${palette.success} 13%, ${palette.surface2})`,
      colorFocusSuccess: `color-mix(in srgb, ${palette.success} 22%, ${palette.surfaceRaised})`,
      colorDisabledSuccess: `color-mix(in srgb, ${palette.success} 10%, ${palette.surface2})`,
      textColorSuccess: palette.text,
      textColorHoverSuccess: palette.text,
      textColorPressedSuccess: palette.text,
      textColorFocusSuccess: palette.text,
      textColorDisabledSuccess: `color-mix(in srgb, ${palette.text} 78%, transparent)`,
      borderSuccess: `1px solid color-mix(in srgb, ${palette.success} 62%, ${palette.borderSoft})`,
      borderHoverSuccess: `1px solid ${palette.success}`,
      borderPressedSuccess: `1px solid ${palette.success}`,
      borderFocusSuccess: `1px solid ${palette.success}`,
      borderDisabledSuccess: `1px solid color-mix(in srgb, ${palette.success} 30%, ${palette.borderSoft})`,
      colorWarning: `color-mix(in srgb, ${palette.warning} 18%, ${palette.surfaceRaised})`,
      colorHoverWarning: `color-mix(in srgb, ${palette.warning} 25%, ${palette.surfaceRaised})`,
      colorPressedWarning: `color-mix(in srgb, ${palette.warning} 13%, ${palette.surface2})`,
      colorFocusWarning: `color-mix(in srgb, ${palette.warning} 22%, ${palette.surfaceRaised})`,
      colorDisabledWarning: `color-mix(in srgb, ${palette.warning} 10%, ${palette.surface2})`,
      textColorWarning: palette.text,
      textColorHoverWarning: palette.text,
      textColorPressedWarning: palette.text,
      textColorFocusWarning: palette.text,
      textColorDisabledWarning: `color-mix(in srgb, ${palette.text} 78%, transparent)`,
      borderWarning: `1px solid color-mix(in srgb, ${palette.warning} 58%, ${palette.borderSoft})`,
      borderHoverWarning: `1px solid ${palette.warning}`,
      borderPressedWarning: `1px solid ${palette.warning}`,
      borderFocusWarning: `1px solid ${palette.warning}`,
      borderDisabledWarning: `1px solid color-mix(in srgb, ${palette.warning} 30%, ${palette.borderSoft})`,
      colorError: `color-mix(in srgb, ${palette.danger} 18%, ${palette.surfaceRaised})`,
      colorHoverError: `color-mix(in srgb, ${palette.danger} 25%, ${palette.surfaceRaised})`,
      colorPressedError: `color-mix(in srgb, ${palette.danger} 13%, ${palette.surface2})`,
      colorFocusError: `color-mix(in srgb, ${palette.danger} 22%, ${palette.surfaceRaised})`,
      colorDisabledError: `color-mix(in srgb, ${palette.danger} 10%, ${palette.surface2})`,
      textColorError: palette.text,
      textColorHoverError: palette.text,
      textColorPressedError: palette.text,
      textColorFocusError: palette.text,
      textColorDisabledError: `color-mix(in srgb, ${palette.text} 78%, transparent)`,
      borderError: `1px solid color-mix(in srgb, ${palette.danger} 62%, ${palette.borderSoft})`,
      borderHoverError: `1px solid ${palette.danger}`,
      borderPressedError: `1px solid ${palette.danger}`,
      borderFocusError: `1px solid ${palette.danger}`,
      borderDisabledError: `1px solid color-mix(in srgb, ${palette.danger} 30%, ${palette.borderSoft})`,
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
