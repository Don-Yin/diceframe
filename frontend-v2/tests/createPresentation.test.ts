import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const createView = readFileSync(
  join(process.cwd(), 'src/features/create/CreateView.vue'),
  'utf8',
)
const createCss = readFileSync(
  join(process.cwd(), 'src/styles/pages/create.css'),
  'utf8',
)

describe('CreateView presentation contract', () => {
  it('exposes the active wizard step to assistive technology', () => {
    expect(createView).toContain(':aria-current="item.state === \'current\' ? \'step\' : undefined"')
    expect(createView).toContain('create-step-guidance')
  })

  it('keeps launch context compact while retaining source semantics', () => {
    expect(createView).toContain('create-setup-summary')
    expect(createView).not.toContain('create-source-relationship')
    expect(createView).toContain('create-selected-adventure')
    expect(createCss).toContain('.create-setup-summary')
  })

  it('exposes the four-step rail and named advanced entry', () => {
    expect(createView).toContain('create-step-rail')
    expect(createView).toContain('create-launch-advanced')
    expect(createView).toContain('语言、种子与补充背景')
    expect(createView).toContain(':open="Boolean(seed.trim())"')
  })

  it('keeps confirmation grouped around the selected launch context', () => {
    expect(createView).toContain('create-confirm-context')
    expect(createView).toContain('create-confirm-settings')
    expect(createView).toContain('create-confirm-party')
    expect(createView).toContain('controlLabel(controlOf(i))')
    expect(createView).toContain('以下摘要会随角色一并进入本局')
  })

  it('keeps game copy available for Japanese and Russian game locales', () => {
    expect(createView).toContain("ja: ja || en")
    expect(createView).toContain("ru: ru || en")
    expect(createView).toContain('このゲームのテンポ')
    expect(createView).toContain('Настройте темп')
  })

  it('keeps navigation usable on narrow screens', () => {
    expect(createCss).toContain('.create-actions')
    expect(createCss).toContain('position: sticky')
    expect(createCss).toContain('env(safe-area-inset-bottom)')
    expect(createCss).toContain('.create-step-rail')
    expect(createCss).toContain('font-size: 16px')
  })
})
