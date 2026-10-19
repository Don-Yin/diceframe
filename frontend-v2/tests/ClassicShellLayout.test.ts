import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = (path: string) => readFileSync(path, 'utf8')

describe('familiar navigation layout', () => {
  it('keeps desktop navigation in the header without an additional task rail', () => {
    const app = source('src/App.vue')
    expect(app.includes('<nav class="desktop-nav"')).toBe(true)
    expect(app.includes('<ExperienceNavigation')).toBe(false)
    expect(app.includes('experience-menu-toggle')).toBe(false)
    expect(source('src/styles/index.css').includes("@import './v2/experience.css'")).toBe(false)
  })

  // Direct settings navigation is exercised through the mounted SettingsView
  // tests and final-construction browser journey, rather than a template loop.
})
