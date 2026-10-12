import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

const css = source('../src/styles/v2/lorebook2.css')

describe('lorebook perspective layout contract', () => {
  it('places the inspector on the right and dropped the character rail', () => {
    expect(css).toMatch(/\.lorebook-shell\.inspector-open\s*\{[\s\S]*?minmax\(0, 1fr\) 280px/)
    expect(css).not.toContain('.lorebook-character-rail')
    expect(css).not.toContain('.no-rail')
  })

  it('degrades the inspector to a fixed drawer below 1100px', () => {
    expect(css).toContain('@media (max-width: 1100px)')
    expect(css).toMatch(/\.lore-perspective-inspector\s*\{[\s\S]*?position: fixed/)
  })

  it('styles audience badges for all three audiences', () => {
    expect(css).toContain('.lore-visibility-badge.audience-public')
    expect(css).toContain('.lore-visibility-badge.audience-character')
    expect(css).toContain('.lore-visibility-badge.audience-gm')
  })
})
