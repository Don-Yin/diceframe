import { expect, test } from './fixtures'
import { PLAY_READY_TIMEOUT } from './support'

for (const mode of ['dark', 'light']) test(`character and party toggles share their appearance in ${mode} mode`, async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop')
  test.setTimeout(60_000)
  await page.addInitScript(mode => localStorage.setItem('diceframe_mode_v2', mode), mode)
  await page.goto('/#/play?game=web%7Ce2e-room%7Cweb_bot')
  if (mode === 'light') await expect(page.locator('body')).toHaveClass(/light/)
  const character = page.locator('.game-sidebar .sidebar-toggle')
  const party = page.locator('.party-rail__toggle')
  const appearance = (control: typeof character) => control.evaluate(element => {
    const style = getComputedStyle(element)
    const box = element.getBoundingClientRect()
    return {
      // Translated drawers can introduce sub-millipixel DOMRect rounding noise.
      width: Number(box.width.toFixed(3)), height: Number(box.height.toFixed(3)), padding: style.padding,
      background: style.backgroundColor, color: style.color,
      border: style.border, radius: style.borderRadius, shadow: style.boxShadow,
      iconSize: getComputedStyle(element.querySelector('.n-icon')!).fontSize,
    }
  })
  for (const width of [801, 980, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    await expect(character).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
    await expect(party).toBeVisible()
    for (const collapsed of [false, true]) {
      await page.mouse.move(450, 450)
      expect(await appearance(character), `${width}px, collapsed=${collapsed}`).toEqual(await appearance(party))
      for (const control of [character, party]) await expect(control).toHaveAttribute('aria-expanded', String(!collapsed))
      if (width === 1280) await page.screenshot({ path: info.outputPath(`sidebars-${mode}-${collapsed ? 'collapsed' : 'expanded'}.png`) })
      if (!collapsed) {
        await character.click()
        await party.click()
        await expect(page.locator('.game-sidebar')).toHaveClass(/collapsed/)
        await expect(page.getByTestId('play-party-rail')).toHaveClass(/party-rail--collapsed/)
      }
    }
    await character.click()
    await party.click()
  }
  await character.hover()
  await character.evaluate(element => Promise.all(element.getAnimations().map(animation => animation.finished)))
  const characterHover = await appearance(character)
  await party.hover()
  await expect.poll(() => appearance(party)).toEqual(characterHover)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByTestId('play-character-toggle').click()
  await page.mouse.move(389, 800)
  const characterClose = await appearance(character)
  await page.screenshot({ path: info.outputPath(`character-drawer-${mode}.png`) })
  await character.click()
  await page.getByTestId('play-tools-toggle').click()
  await page.getByTestId('play-tools-panel').getByRole('button', { name: '队伍', exact: true }).click()
  await expect(party).toBeVisible()
  await page.mouse.move(389, 800)
  expect(await appearance(party)).toEqual(characterClose)
  await expect(party).toHaveAttribute('aria-label', '关闭')
  await page.screenshot({ path: info.outputPath(`party-drawer-${mode}.png`) })
  await party.click()
  await expect(page.getByTestId('play-party-rail')).not.toBeVisible()
})

test('desktop navigation keeps visible labels through intermediate widths', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop')
  await page.goto('/#/overview')
  const links = page.locator('.desktop-nav-link')
  await expect(links).toHaveCount(5)
  for (const language of ['zh-CN', 'en']) {
    await page.locator('.header-locale select').selectOption(language)
    for (const width of [801, 900, 980, 981, 1100, 1280]) {
      await page.setViewportSize({ width, height: 900 })
      for (const link of await links.all()) await expect(link.locator('span')).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth), `${language} at ${width}px`).toBeLessThanOrEqual(1)
      const lastLabel = (await links.last().locator('span').boundingBox())!
      const actions = (await page.locator('.app-header-actions').boundingBox())!
      expect(lastLabel.x + lastLabel.width).toBeLessThanOrEqual(actions.x)
    }
  }
})

for (const mode of ['dark', 'light']) test(`play edge controls share mirrored frames and retain their meaning on resize in ${mode} mode`, async ({ page }, info) => {
  await page.addInitScript(mode => localStorage.setItem('diceframe_mode_v2', mode), mode)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/play?game=web%7Ce2e-dnd2024%7Cweb_bot')
  const left = page.getByTestId('play-character-toggle')
  const right = page.locator('.ruleset-context-tools button:visible')
  await expect(left).toBeVisible({ timeout: PLAY_READY_TIMEOUT })
  await expect(right.first()).toBeVisible()
  const mirroredFrames = () => page.locator('[data-testid="play-character-toggle"], .ruleset-context-tools button:visible').evaluateAll(elements => elements.map(element => {
    const style = getComputedStyle(element)
    const isLeft = element.matches('.mobile-drawer-trigger-left')
    const box = element.getBoundingClientRect()
    return {
      width: box.width, height: box.height, padding: style.padding,
      background: style.backgroundColor, color: style.color, opacity: style.opacity,
      borderTop: style.borderTop, borderBottom: style.borderBottom,
      outerBorder: isLeft ? style.borderLeft : style.borderRight,
      innerBorder: isLeft ? style.borderRight : style.borderLeft,
      outerTopRadius: isLeft ? style.borderTopLeftRadius : style.borderTopRightRadius,
      outerBottomRadius: isLeft ? style.borderBottomLeftRadius : style.borderBottomRightRadius,
      innerTopRadius: isLeft ? style.borderTopRightRadius : style.borderTopLeftRadius,
      innerBottomRadius: isLeft ? style.borderBottomRightRadius : style.borderBottomLeftRadius,
      shadow: style.boxShadow, backdrop: style.backdropFilter,
      iconSize: getComputedStyle(element.querySelector('.n-icon')!).fontSize,
    }
  }))
  for (const width of [320, 390, 740, 800]) {
    await page.setViewportSize({ width, height: 844 })
    const bounds = (await left.boundingBox())!
    const tools = await right.evaluateAll(elements => elements.map(element => {
      const rect = element.getBoundingClientRect()
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    }))
    expect(bounds.x).toBe(0)
    expect(tools.length).toBeGreaterThanOrEqual(1)
    expect(Math.abs(tools[0]!.y - bounds.y)).toBeLessThanOrEqual(1)
    for (const tool of tools) {
      expect(tool.height).toBe(bounds.height)
      expect(tool.width).toBe(bounds.width)
      expect(Math.abs(tool.x + tool.width - width)).toBeLessThanOrEqual(1)
    }
    const frames = await mirroredFrames()
    for (const frame of frames.slice(1)) expect(frames[0], `${width}px mirrored frame`).toEqual(frame)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: info.outputPath('play-edge-controls.png') })
  await left.click()
  const close = page.locator('.game-sidebar .sidebar-toggle')
  await expect(close).toHaveAttribute('aria-label', '关闭')
  await close.click()
  await expect(left).toBeVisible()
  if (info.project.name === 'desktop') {
    for (const width of [801, 980, 1280]) {
      await page.setViewportSize({ width, height: 900 })
      await expect(close).toBeVisible()
      await expect(close).toHaveAttribute('aria-label', '收起侧栏')
      await close.click()
      await expect(page.locator('.game-sidebar')).toHaveClass(/collapsed/)
      await close.click()
      await expect(page.locator('.game-sidebar')).not.toHaveClass(/collapsed/)
    }
  }
})
