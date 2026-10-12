import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { isPublicRoute } from '../src/router'

/**
 * 顶栏二维码入口是 owner-only：App.vue 的顶栏只在非 publicRoute 的 app-shell
 * 分支里渲染。这里按仓库既有的源码契约测试（见 GmToolbarLayout.test.ts）锁住
 * 顺序、可见性与「设置页不再内嵌完整配对面板」三件事，避免以后又被塞回公共入口。
 */
function source(path: string): string {
  return readFileSync(join(process.cwd(), path), 'utf8')
}

const appSource = source('src/App.vue')
const settingsSource = source('src/features/admin/SettingsView.vue')
const navigationStyles = source('src/styles/v2/navigation.css')

const headerActionsStart = appSource.indexOf('<div class="app-header-actions">')
const headerActions = appSource.slice(headerActionsStart, appSource.indexOf('</header>'))
const publicBranch = appSource.slice(
  appSource.indexOf('<RouterView v-if="fullscreen"'),
  appSource.indexOf('<div v-else class="app-shell"'),
)

describe('owner-only pairing entry in the app shell', () => {
  it('orders 公告 / 二维码 / 主题 in the desktop header actions', () => {
    expect(headerActionsStart).toBeGreaterThan(-1)
    const announcement = headerActions.indexOf('<AnnouncementButton')
    const pairing = headerActions.indexOf('<DevicePairingButton')
    const theme = headerActions.indexOf('<ThemeToggle')
    expect(announcement).toBeGreaterThan(-1)
    expect(pairing).toBeGreaterThan(announcement)
    expect(theme).toBeGreaterThan(pairing)
  })

  it('renders the pairing button only outside public routes', () => {
    expect(headerActions).toContain('<DevicePairingButton v-if="!publicRoute"')
    // 弹窗挂在 header 之外、同样受 owner-only 约束，且只在点击后才挂载。
    expect(appSource).toContain('<DevicePairingModal v-if="pairingOpen && !publicRoute"')
    // fullscreen（publicRoute）分支只有主题按钮，没有任何配对入口。
    expect(publicBranch).not.toBe('')
    expect(publicBranch).not.toContain('DevicePairing')
    expect(appSource).toContain('const fullscreen = publicRoute')
  })

  it('treats join and shared play links as public routes', () => {
    expect(isPublicRoute({ name: 'join', query: {} })).toBe(true)
    expect(isPublicRoute({ name: 'play', query: { user: 'u1' } })).toBe(true)
    expect(isPublicRoute({ name: 'play', query: {} })).toBe(false)
    expect(isPublicRoute({ name: 'settings', query: {} })).toBe(false)
  })

  it('keeps the header actions group reachable on mobile widths', () => {
    // 二维码按钮与公告/主题同属 .app-header-actions：该组在窄屏不被隐藏，
    // 因此不需要为移动端另做入口，也没有改导航。
    expect(navigationStyles).toMatch(/\.app-header-actions\s*\{[^}]*display:\s*flex/)
    expect(navigationStyles).not.toMatch(/\.app-header-actions\s*\{[^}]*display:\s*none/)
    expect(navigationStyles).toContain('.mobile-bottom-nav')
  })

  it('no longer renders the full DevicePairingPanel inside the access-control settings page', () => {
    expect(settingsSource).not.toContain('DevicePairingPanel')
    expect(settingsSource).not.toContain('devicePairing')
  })
})

describe('pairing button visual contract', () => {
  const buttonSource = source('src/components/DevicePairingButton.vue')

  it('matches AnnouncementButton / ThemeToggle: circular quaternary icon button', () => {
    for (const file of [
      'src/components/AnnouncementButton.vue',
      'src/components/ThemeToggle.vue',
      'src/components/DevicePairingButton.vue',
    ]) {
      const text = source(file)
      expect(text).toContain('circle')
      expect(text).toContain('quaternary')
      expect(text).toContain('class="theme-toggle"')
    }
    expect(buttonSource).toContain('QrCodeOutline')
    expect(buttonSource).toContain("t('pairingTitle')")
  })
})
