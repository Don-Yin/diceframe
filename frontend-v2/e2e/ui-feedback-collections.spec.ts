import { expect, test } from './fixtures'

function assertClose(actual: number, expected: number, tolerance = 1) {
  expect(Math.abs(actual - expected)).toBeLessThanOrEqual(tolerance)
}

test('overview reuses custom scene artwork when returning from another route', async ({ page }) => {
  const coverRequests: string[] = []
  let gamesRequests = 0
  let releaseSecondGames!: () => void
  const secondGamesReady = new Promise<void>(resolve => { releaseSecondGames = resolve })
  await page.route('**/api/games', async route => {
    gamesRequests += 1
    if (gamesRequests > 1) await secondGamesReady
    return route.fulfill({ json: {
    games: [{
      game_key: 'web|overview-cache|gm',
      world_name: '缓存冒险',
      scene: '测试场景',
      state: 'paused',
      rule_id: 'freeform_fantasy',
      scene_image: { kind: 'upload', asset_id: 'overview-cache-cover' },
      round_number: 14,
      player_count: 2,
      max_players: 6,
    }],
    } })
  })
  await page.route('**/api/scene-images/overview-cache-cover', route => {
    coverRequests.push(route.request().url())
    return route.fulfill({
      contentType: 'image/png',
      body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'),
    })
  })

  await page.goto('/#/overview')
  const featuredImage = page.locator('.overview-featured-art > img')
  await expect(featuredImage).toHaveJSProperty('complete', true)
  await expect.poll(() => featuredImage.getAttribute('src')).toMatch(/^blob:/)
  const firstSource = await featuredImage.getAttribute('src')
  expect(coverRequests).toHaveLength(1)

  await page.evaluate(() => { window.location.hash = '#/characters' })
  await expect(page).toHaveURL(/#\/characters$/)
  await page.evaluate(() => { window.location.hash = '#/overview' })
  await expect(page).toHaveURL(/#\/overview$/)
  const returnedImage = page.locator('.overview-featured-art > img')
  await expect(returnedImage).toBeVisible()
  await expect(returnedImage).toHaveAttribute('src', firstSource!)
  expect(coverRequests).toHaveLength(1)
  releaseSecondGames()
})

test('overview save tools stay anchored and recover keyboard focus', async ({ page }, info) => {
  await page.goto('/#/overview')
  await expect(page.locator('.game-card').nth(1)).toBeVisible()
  await expect(page.locator('.overview-hero .eyebrow')).toBeVisible()
  const heading = await page.locator('.overview-hero h1').boundingBox()
  const header = await page.locator('.app-header').boundingBox()
  expect(heading).not.toBeNull()
  expect(header).not.toBeNull()
  expect(heading!.y).toBeGreaterThanOrEqual(header!.y + header!.height)
  const featured = await page.locator('.overview-featured').boundingBox()
  const featuredArt = await page.locator('.overview-featured-art').boundingBox()
  const featuredDetails = await page.locator('.overview-featured-details').boundingBox()
  expect(featured).not.toBeNull()
  expect(featuredArt).not.toBeNull()
  expect(featuredDetails).not.toBeNull()
  expect(featuredDetails!.x + featuredDetails!.width).toBeGreaterThan(featured!.x + featured!.width * .5)
  const featuredEnter = await page.locator('.overview-featured-enter').boundingBox()
  expect(featuredEnter).not.toBeNull()
  expect(featuredEnter!.width).toBeGreaterThanOrEqual(featuredDetails!.width - 32)
  const leftAligned = page.viewportSize()!.width <= 800
  const featuredAlignment = await page.locator('.overview-featured-copy').evaluate((copy, leftAligned) => {
    const title = copy.querySelector<HTMLElement>('h2')?.getBoundingClientRect()
    const details = copy.querySelector<HTMLElement>('.overview-featured-details')?.getBoundingClientRect()
    const enter = copy.querySelector<HTMLElement>('.overview-featured-enter')?.getBoundingClientRect()
    return {
      textAlign: getComputedStyle(copy).textAlign,
      titleEdge: (leftAligned ? title?.left : title?.right) || 0,
      detailsEdge: (leftAligned ? details?.left : details?.right) || 0,
      enterEdge: (leftAligned ? enter?.left : enter?.right) || 0,
    }
  }, leftAligned)
  expect(featuredAlignment.textAlign).toBe(leftAligned ? 'left' : 'right')
  assertClose(featuredAlignment.titleEdge, featuredAlignment.detailsEdge)
  assertClose(featuredAlignment.detailsEdge, featuredAlignment.enterEdge)
  const featuredArtStyle = await page.locator('.overview-featured-art').evaluate(element => ({
    inline: element.getAttribute('style') || '',
    backgroundImage: getComputedStyle(element).backgroundImage,
  }))
  const featuredImage = page.locator('.overview-featured-art > img')
  await expect(featuredImage).toHaveJSProperty('complete', true)
  expect(await featuredImage.evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  expect(featuredArtStyle.inline).toContain('--df-bg-scene-image')
  expect(featuredArtStyle.backgroundImage).not.toBe('none')
  assertClose(featuredArt!.width, featured!.width - 2, 2)
  expect(featured!.x).toBeGreaterThanOrEqual(0)
  expect(featured!.x + featured!.width).toBeLessThanOrEqual(page.viewportSize()!.width)

  // List mode keeps the same scenic surface as the grid.  It must not regress
  // to the old split thumbnail + opaque body composition, and its primary CTA
  // stays the same readable height as the featured entry action.
  await page.locator('.library-view-toggle button').nth(1).click()
  const listCard = page.locator('.game-grid.is-list .game-card').first()
  await expect(listCard).toBeVisible()
  const listGeometry = await listCard.evaluate((card) => {
    const art = card.querySelector<HTMLElement>('.game-card-art')
    const body = card.querySelector<HTMLElement>('.game-card-body')
    const enter = card.querySelector<HTMLElement>('.game-card-enter')
    const enterLabel = enter?.querySelector<HTMLElement>('span')
    const enterIcon = enter?.querySelector<HTMLElement>('.n-icon')
    const cardBox = card.getBoundingClientRect()
    const artBox = art?.getBoundingClientRect()
    const labelBox = enterLabel?.getBoundingClientRect()
    const iconBox = enterIcon?.getBoundingClientRect()
    return {
      display: getComputedStyle(card).display,
      artPosition: art ? getComputedStyle(art).position : '',
      artWidth: artBox?.width || 0,
      cardWidth: cardBox.width,
      bodyPaddingLeft: body ? parseFloat(getComputedStyle(body).paddingLeft) : 0,
      enterHeight: enter?.getBoundingClientRect().height || 0,
      enterBackgroundImage: enter ? getComputedStyle(enter).backgroundImage : '',
      enterBackdropFilter: enter ? getComputedStyle(enter).backdropFilter : '',
      enterCursor: enter ? getComputedStyle(enter).cursor : '',
      enterRadius: enter ? getComputedStyle(enter).borderTopLeftRadius : '',
      toolsRadius: getComputedStyle(card.querySelector<HTMLElement>('.overview-game-tools > summary')!).borderTopLeftRadius,
      enterBoxShadow: enter ? getComputedStyle(enter).boxShadow : '',
      enterContentGap: labelBox && iconBox ? iconBox.left - labelBox.right : Number.POSITIVE_INFINITY,
    }
  })
  expect(listGeometry.display).toBe('block')
  expect(listGeometry.artPosition).toBe('absolute')
  expect(listGeometry.artWidth).toBeGreaterThanOrEqual(listGeometry.cardWidth - 2)
  expect(listGeometry.bodyPaddingLeft).toBeLessThan(48)
  const featuredEnterHeight = await page.locator('.overview-featured-enter').evaluate(element => element.getBoundingClientRect().height)
  expect(Math.abs(listGeometry.enterHeight - featuredEnterHeight)).toBeLessThanOrEqual(1)
  expect(listGeometry.enterBackgroundImage).toContain('linear-gradient')
  expect(listGeometry.enterBackdropFilter).toContain('blur(')
  expect(listGeometry.enterCursor).toBe('pointer')
  expect(listGeometry.enterRadius).toBe(listGeometry.toolsRadius)
  expect(listGeometry.enterBoxShadow).not.toBe('none')
  expect(listGeometry.enterContentGap).toBeGreaterThanOrEqual(6)
  expect(listGeometry.enterContentGap).toBeLessThanOrEqual(18)

  const toolbarHeights = await page.locator('.library-heading-actions > button, .library-heading-actions > .overview-archive-tools > summary').evaluateAll(elements => elements.map(element => element.getBoundingClientRect().height))
  expect(toolbarHeights.length).toBeGreaterThanOrEqual(3)
  expect(new Set(toolbarHeights.map(height => Math.round(height))).size).toBe(1)

  const enterButton = page.locator('.overview-featured-enter')
  const createButton = page.locator('[data-testid="overview-create-adventure"]')
  await page.evaluate(() => { document.documentElement.dataset.skin = 'midnight' })
  const midnightEnterColor = await enterButton.evaluate(element => getComputedStyle(element).backgroundImage)
  const midnightCreateColor = await createButton.evaluate(element => getComputedStyle(element).backgroundImage)
  await page.evaluate(() => { document.documentElement.dataset.skin = 'crimson' })
  const crimsonEnterColor = await enterButton.evaluate(element => getComputedStyle(element).backgroundImage)
  const crimsonCreateColor = await createButton.evaluate(element => getComputedStyle(element).backgroundImage)
  expect(crimsonEnterColor).not.toBe(midnightEnterColor)
  expect(crimsonCreateColor).not.toBe(midnightCreateColor)
  await page.evaluate(() => { document.documentElement.dataset.skin = 'midnight' })
  await page.locator('.library-view-toggle button').first().click()
  await page.screenshot({ path: info.outputPath(`ui-feedback-home-${info.project.name}.png`), scale: 'css' })
  const glassEnter = page.locator('.game-card-enter').first()
  await glassEnter.focus()
  await expect(glassEnter).toBeFocused()
  await page.locator('.game-card').first().screenshot({ path: info.outputPath('glass-enter-dark.png'), scale: 'css' })
  await page.evaluate(() => { document.documentElement.dataset.mode = 'light' })
  await page.locator('.game-card').first().screenshot({ path: info.outputPath('glass-enter-light.png'), scale: 'css' })
  await page.evaluate(() => { document.documentElement.dataset.mode = 'dark' })
  await page.locator('.game-card').first().locator('.overview-game-tools summary').scrollIntoViewIfNeeded()
  const first = page.locator('.game-card').nth(0)
  const second = page.locator('.game-card').nth(1)
  const documentBox = (element: HTMLElement) => {
    const rect = element.getBoundingClientRect()
    return { height: rect.height, y: rect.y + scrollY }
  }
  const firstBefore = await first.evaluate(documentBox)
  const secondBefore = await second.evaluate(documentBox)
  expect(firstBefore).not.toBeNull()
  expect(secondBefore).not.toBeNull()

  const firstTools = first.locator('.overview-game-tools')
  const secondTools = second.locator('.overview-game-tools')
  await firstTools.locator('summary').click()
  await expect(firstTools).toHaveAttribute('open', '')
  const firstAfter = await first.evaluate(documentBox)
  const secondAfter = await second.evaluate(documentBox)
  assertClose(firstAfter!.height, firstBefore!.height)
  assertClose(secondAfter!.y, secondBefore!.y)
  assertClose(secondAfter!.height, secondBefore!.height)

  await secondTools.locator('summary').click()
  await expect(secondTools).toHaveAttribute('open', '')
  await expect(firstTools).not.toHaveAttribute('open', '')
  await page.keyboard.press('Escape')
  await expect(secondTools).not.toHaveAttribute('open', '')
  await expect(secondTools.locator('summary')).toBeFocused()

  await firstTools.locator('summary').click()
  await page.locator('.overview-hero h1').click()
  await expect(firstTools).not.toHaveAttribute('open', '')

  const archive = page.locator('.overview-archive-tools')
  // Batch controls belong to the explicit selection mode.  The default
  // archive toolbar keeps the single entry point compact and predictable.
  await expect(page.locator('.overview-select-saves')).toBeVisible()
  await expect(page.locator('.overview-selection-count')).toHaveCount(0)
  await expect(page.locator('[data-testid="overview-exit-selection"]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /全选|Select all/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /反选|Invert selection/ })).toHaveCount(0)
  await archive.locator('summary').click()
  await expect(archive).toHaveAttribute('open', '')
  const archiveButtons = archive.locator('div > button')
  await expect(archiveButtons).toHaveCount(1)
  await expect(page.locator('.library-heading-actions .overview-import-saves')).toBeVisible()
  const archiveBoxes = await archiveButtons.evaluateAll(buttons => buttons.map(button => {
    const box = button.getBoundingClientRect()
    return { top: box.top, bottom: box.bottom, height: box.height }
  }))
  expect(archiveBoxes[0].height).toBeGreaterThan(0)
  await page.locator('.overview-hero h1').click()
  await expect(archive).not.toHaveAttribute('open', '')

  if (info.project.name === 'desktop') {
    await firstTools.locator('summary').click()
    await page.screenshot({ path: info.outputPath('ui-feedback-save-actions-desktop.png'), scale: 'css' })
  } else {
    await firstTools.locator('summary').click()
    const popup = firstTools.locator('div.game-card-tools')
    await expect(popup).toBeVisible()
    const box = await popup.boundingBox()
    const viewport = page.viewportSize()!
    expect(box).not.toBeNull()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.y).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width)
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height)
    expect(viewport.height - box!.y - box!.height).toBeGreaterThanOrEqual(70)
    expect(viewport.height - box!.y - box!.height).toBeLessThanOrEqual(100)
    await page.screenshot({ path: info.outputPath('ui-feedback-overview-mobile.png'), scale: 'css' })
  }
})

test('create keeps the four step rail, selected state, and guidance visible', async ({ page }, info) => {
  await page.goto('/#/create')
  await expect(page.locator('.create-config-surface select').nth(0)).not.toHaveValue('')
  await expect(page.locator('.create-config-surface select').nth(1)).not.toHaveValue('')
  const rail = page.locator('.create-step-rail')
  await expect(rail).toBeVisible()
  await expect(rail.locator('.create-step-rail__item')).toHaveCount(4)
  await expect(rail.locator('.create-step-rail__item.current')).toHaveCount(1)
  await expect(rail.locator('.create-step-rail__item.current')).toHaveAttribute('aria-current', 'step')
  await expect(rail.locator('.create-step-rail__item strong').first()).toBeVisible()
  await expect(rail.locator('.create-step-rail__item small').first()).toContainText(/\S+/)
  await expect(page.locator('.create-page-header__eyebrow')).toBeVisible()
  await expect(page.locator('.create-page-header__eyebrow')).toHaveText('NEW GAME')
  await expect(rail.locator('.create-rail-summary')).toBeVisible()
  await expect(page.locator('.create-page-header h1')).toBeVisible()
  await expect(page.locator('.create-page-header h1')).toContainText(/\S+/)
  const titleSize = await page.locator('.create-page-header h1').evaluate(element => parseFloat(getComputedStyle(element).fontSize))
  expect(titleSize).toBeGreaterThanOrEqual(info.project.name === 'desktop' ? 38 : 24)
  await page.screenshot({ path: info.outputPath(`ui-feedback-create-${info.project.name}.png`), scale: 'css' })
})

test('create explains world book inheritance and links to the selected source world', async ({ page }, info) => {
  const worlds: string[] = []
  await page.route('**/api/lorebooks?world_id=*', route => {
    const world = new URL(route.request().url()).searchParams.get('world_id') || ''
    worlds.push(world)
    return route.fulfill({ json: { books: [
      { id: `world:${world}`, name: '世界基础资料', enabled: true, entry_count: 4, bindings: [{ scope_kind: 'world', scope_id: world, role: 'primary' }] },
      { id: 'town-npc', name: '城镇人物资料', enabled: true, entry_count: 8, bindings: [{ scope_kind: 'world', scope_id: world }] },
      { id: 'disabled', name: '暂停使用的资料', enabled: false, bindings: [{ scope_kind: 'world', scope_id: world }] },
      { id: 'common', name: '通用术语', enabled: true, bindings: [{ scope_kind: 'global', scope_id: '' }] },
      { id: 'unbound', name: '未绑定资料', enabled: true, bindings: [] },
    ] } })
  })
  await page.goto('/#/create')
  const worldSelect = page.locator('.create-config-surface select').nth(0)
  await expect(worldSelect).not.toHaveValue('')
  const world = await worldSelect.inputValue()
  const summary = page.getByTestId('create-lorebook-summary')
  await summary.locator('summary').click()
  await expect(summary).toContainText('城镇人物资料')
  await expect(summary.locator('li[data-active=true]')).toHaveCount(3)
  await expect(summary.locator('li[data-active=false]')).toContainText('暂停使用的资料')
  await expect(summary).not.toContainText('未绑定资料')
  await expect(summary).toContainText('选择只影响本局')
  await expect(summary.locator('input[type=checkbox]')).toHaveCount(3)
  expect(worlds).toContain(world)
  const href = await summary.locator('a').getAttribute('href')
  expect(new URLSearchParams(href!.split('?')[1]).get('world')).toBe(world)
  const source = page.locator('.create-config-surface select').filter({ has: page.locator('option[value="__builtin__"]') })
  await source.selectOption('__blank__')
  await expect(summary).toContainText('空白的独立世界')
  await expect(summary.locator('li')).toHaveCount(1)
  await expect(summary).toContainText('通用术语')
  await expect(summary.locator('a')).toHaveCount(0)
  await source.selectOption('__builtin__')
  await expect(summary).toContainText('城镇人物资料')
  await page.screenshot({ path: info.outputPath(`create-world-books-${info.project.name}.png`), scale: 'css' })
  await summary.screenshot({ path: info.outputPath(`create-book-summary-${info.project.name}.png`), scale: 'css' })
})
