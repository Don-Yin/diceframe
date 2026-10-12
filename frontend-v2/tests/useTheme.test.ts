import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
}))

vi.mock('../src/api/client', () => ({ api: mocks.api }))

describe('useTheme v2', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.api.mockReset()
    localStorage.clear()
    document.documentElement.removeAttribute('data-mode')
    document.documentElement.removeAttribute('data-skin')
    document.documentElement.removeAttribute('style')
    document.body.className = ''
  })

  it('initializes the v2 mode and built-in skin attributes', async () => {
    const { DEFAULT_THEME_MODE, DEFAULT_THEME_SKIN, useTheme } = await import('../src/composables/useTheme')
    const theme = useTheme()

    expect(DEFAULT_THEME_MODE).toBe('dark')
    expect(DEFAULT_THEME_SKIN).toBe('midnight')
    expect(theme.current.value).toBe(DEFAULT_THEME_MODE)
    expect(theme.skin.value).toBe(DEFAULT_THEME_SKIN)
    expect(document.documentElement.dataset.mode).toBe('dark')
    expect(document.documentElement.dataset.skin).toBe('midnight')

    theme.applySkin('jade')
    theme.apply('light')

    expect(document.documentElement.dataset.skin).toBe('jade')
    expect(document.documentElement.dataset.mode).toBe('light')
    expect(document.body.classList.contains('light')).toBe(true)
    expect(localStorage.getItem('diceframe_skin_v2')).toBe('jade')
  })

  it('loads only v2 plugin themes and reapplies mode-specific tokens', async () => {
    mocks.api.mockResolvedValue({
      ok: true,
      themes: [
        {
          schema_version: 2,
          id: 'v2-theme',
          name: 'V2',
          plugin_id: 'theme-pack',
          tokens: {
            base: {
              '--df-accent': '#abcdef',
              '--df-bg-scene-image': 'url(https://example.com/unsafe.jpg)',
            },
            dark: { '--df-canvas': '#010203' },
            light: { '--df-canvas': '#fafafa' },
          },
        },
        {
          schema_version: 1,
          id: 'legacy-theme',
          name: 'Legacy',
          plugin_id: 'old-pack',
          tokens: { base: { '--gold': '#fff' } },
        },
      ],
    })

    const { useTheme } = await import('../src/composables/useTheme')
    const theme = useTheme()
    await theme.loadPluginThemes()
    theme.applyPluginTheme('v2-theme')

    expect(theme.pluginThemes.value.map(item => item.id)).toEqual(['v2-theme'])
    expect(document.documentElement.style.getPropertyValue('--df-accent')).toBe('#abcdef')
    expect(document.documentElement.style.getPropertyValue('--df-canvas')).toBe('#010203')
    expect(document.documentElement.style.getPropertyValue('--df-bg-scene-image')).toBe('')

    theme.apply('light')
    expect(document.documentElement.style.getPropertyValue('--df-canvas')).toBe('#fafafa')

    theme.suspendPluginTheme()
    expect(document.documentElement.style.getPropertyValue('--df-accent')).toBe('')
    expect(document.documentElement.style.getPropertyValue('--df-canvas')).toBe('')

    theme.restorePluginTheme()
    expect(document.documentElement.style.getPropertyValue('--df-accent')).toBe('#abcdef')
    expect(document.documentElement.style.getPropertyValue('--df-canvas')).toBe('#fafafa')

    theme.clearPluginTheme()
    expect(document.documentElement.style.getPropertyValue('--df-accent')).toBe('')
    expect(document.documentElement.style.getPropertyValue('--df-canvas')).toBe('')
  })
})
