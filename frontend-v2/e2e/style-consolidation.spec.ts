import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test } from './fixtures'
import { seatTakeoverPath } from './support'

// An opt-in comparison against a private pre-refactor baseline. Ordinary E2E
// runs still verify that every sampled surface loads.
const baselineDirectory = process.env.DICEFRAME_STYLE_BASELINE
const recordBaseline = process.env.DICEFRAME_RECORD_STYLES === '1'
const referenceStyles = process.env.DICEFRAME_STYLE_REFERENCE
  ? readFileSync(process.env.DICEFRAME_STYLE_REFERENCE, 'utf8') : ''
const pages = [
  ['overview', '.overview-page'], ['library', '.content-library-page'],
  ['characters', '.characters-page'], ['worlds', '.worlds-page'],
  ['lorebook', '.lorebook-page'], ['adventures', '.adventures-page'],
  ['modules', '.modules-page'], ['modules/e2e-module', '.module-detail-page'],
  ['create', '.create-page'], ['creator', '.creator-page'],
  ['rules', '.rules-page'], ['logs', '.logs-page'], ['memory', '.memory-page'],
  ['plugins', '.plugins-page'], ['peer', '.peer-page'], ['map', '.map-page'],
  ...['general', 'appearance', 'models', 'voice', 'agent', 'system', 'about', 'security']
    .map(section => [`settings?section=${section}`, '.settings-page']),
  ['play?game=web%7Ce2e-room%7Cweb_bot', '.play-page'],
  ['join?game=web%7Ce2e-room%7Cweb_bot&share=1', '.join-page'],
] as const

for (const light of [false, true]) test(`page appearance survives stylesheet consolidation (${light ? 'light' : 'dark'})`, async ({ page }, info) => {
  test.setTimeout(240_000)
  const differences: string[] = []
  const pending = new Set<import('@playwright/test').Request>()
  page.on('request', request => { if (request.method() === 'GET' && !/\/sse(?:\?|$)/.test(request.url())) pending.add(request) })
  page.on('requestfinished', request => pending.delete(request))
  page.on('requestfailed', request => pending.delete(request))
  // Release lookups are external and can finish long after local UI data;
  // keep this diagnostic deterministic while comparing stylesheet behavior.
  await page.route('**/api/system/update-check', route => route.fulfill({ json: { ok: true, current_version: 'e2e', update_available: false, no_release: true } }))
  await page.addInitScript(light => {
    localStorage.setItem('currentGame', 'web|e2e-room|web_bot')
    localStorage.setItem('diceframe_mode_v2', light ? 'light' : 'dark')
  }, light)
  for (const [route, selector] of pages) {
    await page.goto(`/#/${route}`)
    // Some feature roots use their own names; the route's rendered main
    // surface is sufficient here and gets captured in full below.
    await expect(page.locator(selector).or(page.locator('.view, .join-page, .play-page').first()).first()).toBeVisible()
    await expect.poll(() => [...pending].filter(request => new URL(request.url()).pathname.startsWith('/api/')).map(request => request.url()), { timeout: 25_000 }).toEqual([])
    if (route === 'plugins') await expect(page.locator('.type-filter-row button')).toHaveCount(7)
    await page.evaluate(() => document.fonts.ready)
    await expect(page.locator('.n-spin-content--spinning')).toHaveCount(0)
    await expect(page.locator('.fade-in-width-expand-transition-leave-active')).toHaveCount(0)
    // Wait for public data and font layout to settle, ignoring persistent SSE.
    let previous = '', stable = 0
    await expect.poll(async () => {
      const signature = await page.evaluate(() => document.body.innerText + ':' + document.documentElement.scrollHeight)
      stable = signature === previous ? stable + 1 : 0
      previous = signature
      return stable
    }, { intervals: [150], timeout: 15_000 }).toBeGreaterThanOrEqual(3)
    const capture = () => page.evaluate(() => {
      const properties = ['display', 'position', 'gridTemplateColumns', 'gridTemplateRows', 'gridTemplateAreas', 'flexDirection', 'flexWrap', 'gap', 'alignItems', 'justifyContent', 'overflowX', 'overflowY', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'marginTop', 'marginRight', 'marginBottom', 'marginLeft', 'minWidth', 'maxWidth', 'minHeight', 'maxHeight', 'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth', 'borderRadius', 'fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'textAlign', 'color', 'backgroundColor', 'backgroundImage', 'boxShadow', 'transform'] as const
      return [...document.querySelectorAll<HTMLElement>('#app *')].filter(element => {
        const box = element.getBoundingClientRect()
        return box.width > 0 && box.height > 0 && !element.closest('.assistant-launcher, .n-loading-bar-container, .n-message-container')
      }).map(element => {
        const style = getComputedStyle(element), box = element.getBoundingClientRect()
        return {
          tag: element.tagName, classes: [...element.classList].filter(name => !/^__[a-z0-9]+$/.test(name)).join(' '),
          box: [box.x, box.y, box.width, box.height].map(value => Math.round(value * 10) / 10),
          styles: Object.fromEntries(properties.map(property => [property, style[property].replace(/blob:[^"')]+/g, 'blob:<asset>')])),
        }
      })
    })
    const snapshot = await capture()
    expect(snapshot.length, route).toBeGreaterThan(5)
    if (referenceStyles) {
      // Reapply the previous global cascade immediately after the entry link,
      // before lazy feature styles. It restores every original declaration at
      // the same specificity, against this exact DOM/data/font state, avoiding
      // false differences from generated IDs or asynchronous plugin startup.
      await page.evaluate(css => {
        const entry = document.querySelector('link[rel="stylesheet"][href*="/assets/index-"]')
        if (!entry) throw new Error('global stylesheet entry is missing')
        const style = document.createElement('style')
        style.dataset.styleReference = ''
        style.textContent = css
        entry.after(style)
      }, referenceStyles)
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
      const reference = await capture()
      if (JSON.stringify(snapshot) !== JSON.stringify(reference)) {
        differences.push(route)
        const directory = info.outputPath('appearance-differences')
        mkdirSync(directory, { recursive: true })
        writeFileSync(resolve(directory, `${route.replace(/[^a-z0-9]+/gi, '-')}.json`), JSON.stringify({ before: reference, after: snapshot }, null, 2))
      }
      continue
    }
    if (!baselineDirectory) continue
    mkdirSync(baselineDirectory, { recursive: true })
    const path = resolve(baselineDirectory, `${info.project.name}-${light ? 'light' : 'dark'}-${route.replace(/[^a-z0-9]+/gi, '-')}.json`)
    if (recordBaseline) writeFileSync(path, JSON.stringify(snapshot, null, 2))
    else {
      const baseline = JSON.parse(readFileSync(path, 'utf8')) as typeof snapshot
      if (JSON.stringify(snapshot) !== JSON.stringify(baseline)) {
        const actualDirectory = resolve(baselineDirectory, '../after')
        mkdirSync(actualDirectory, { recursive: true })
        writeFileSync(resolve(actualDirectory, path.split(/[\\/]/).pop()!), JSON.stringify(snapshot, null, 2))
        differences.push(route)
      }
    }
  }
  expect(differences, 'Geometry and computed appearance must match the pre-cleanup baseline').toEqual([])
})

test('invited player keeps the same layout after stylesheet consolidation', async ({ browser, request }, info) => {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.setViewportSize(info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 900 })
  await page.goto(await seatTakeoverPath(request, 'web|e2e-room|web_bot', 'e2e-player'))
  await expect(page.getByTestId('timeline')).toBeVisible()
  await expect(page.getByTestId('play-tools-toggle')).toBeInViewport()
  await page.getByTestId('play-tools-toggle').click()
  await expect(page.getByTestId('play-tools-panel')).toBeInViewport()
  await context.close()
})
